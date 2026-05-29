#!/usr/bin/env python3
"""Single entry point for all machine-checks before handoff.

Hard-gate tier dispatch (tiered acceptance refactor):
  - S-tier: 6 critical checks (criteria-frontmatter, whitelist, preflight,
    handoff-paths, danger-scan, verdict-canonical)
  - M-tier: 13 checks (S + handoff-sections, self-acceptance-thinness,
    iteration-counter, validator-outputs, size-drift, human-directive,
    director-verdict)
  - L-tier: 21 checks (all)

Tier is read from criteria.md frontmatter. Override via --all-checks (run
everything) or --override-checks NAME1,NAME2 (add to current tier set).

Lead runs this BEFORE submitting handoff. Director runs this FIRST during
acceptance sweep. Both must see exit 0 before proceeding.

Usage:
  python ~/.claude/scripts/handoff-precheck.py engagement/
  python ~/.claude/scripts/handoff-precheck.py engagement/ --json
  python ~/.claude/scripts/handoff-precheck.py engagement/ --all-checks
  python ~/.claude/scripts/handoff-precheck.py engagement/ --override-checks slot-language,trace-schema

Exit codes:
  0 — all checks passed; safe to submit / accept
  1 — at least one check failed; handoff INCOMPLETE
  2 — invocation error

Internal structure (modular refactor):
  Check implementations live in `lib/precheck/{criteria,handoff,iteration,
  validators,acceptance,danger}.py`; this file is the CLI dispatcher only
  (argparse + tier-set selection + parallel execution + ledger emit +
  output formatting + ready-mode skip-to-fail transformation).
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

# Topic-modularized checks
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.precheck import (  # noqa: E402
    read_criteria_meta,
    # criteria
    check_whitelist, check_criteria_frontmatter, check_preflight,
    check_size_drift, check_tasks_decomposition,
    # handoff
    check_handoff_paths, check_handoff_sections, check_cross_val_quotes,
    check_self_acceptance_thinness, check_slot_language,
    # iteration
    check_iteration_counter, check_executor_iteration_structure,
    check_validator_output_freshness, check_specialist_criteria_ack,
    # validators
    check_validator_outputs, check_trace_schema,
    # acceptance
    check_acceptance_log_paths, check_verdict_canonical,
    check_human_directive, check_director_verdict,
    # danger
    check_danger_scan,
)

# Append-only event ledger. Optional dependency; falls back to silent
# no-op when unavailable so handoff-precheck.py works unchanged on
# stripped installs / minimal envs.
try:
    from lib.ledger import EventLedger  # noqa: E402
    _LEDGER_AVAILABLE = True
except Exception:
    EventLedger = None  # type: ignore
    _LEDGER_AVAILABLE = False

_RUN_LEDGER = None  # set in main()


def _ledger_emit(payload_type: str, **kwargs):
    if _RUN_LEDGER is None:
        return None
    try:
        return _RUN_LEDGER.emit(payload_type, **kwargs)
    except Exception as e:
        print(f"WARN: ledger emit failed ({payload_type}): {e}", file=sys.stderr)
        return None


def _emit_check_result(name: str, result: dict) -> None:
    """Map a check's {name, status, detail, fix} dict to a precheck_passed /
    precheck_failed event. Skip→no event (would be noise). Detail/fix
    truncated to keep events.jsonl small."""
    status = (result or {}).get("status", "skip")
    detail = str((result or {}).get("detail") or "")[:200]
    fix = str((result or {}).get("fix") or "")[:200]
    if status == "pass":
        _ledger_emit("precheck_passed",
                     node=f"precheck:{name}",
                     payload={"check": name, "detail": detail})
    elif status == "fail":
        _ledger_emit("precheck_failed",
                     node=f"precheck:{name}",
                     payload={"check": name, "detail": detail, "fix": fix},
                     verdict="REJECT")
    elif status == "warn":
        # Warn isn't a payload_type; record as a passed event with warn detail.
        _ledger_emit("precheck_passed",
                     node=f"precheck:{name}",
                     payload={"check": name, "warn": True, "detail": detail})
    # skip → silent (a quiet ledger is the right signal: nothing to look at)


# Hard-gate tier-checks (tiered acceptance refactor):
# Each tier dispatches an explicit subset of checks. Checks not in tier set
# are NOT invoked at all (no soft-skip overhead). Use --override-checks for
# ad-hoc inclusion of additional checks on a per-run basis.
TIER_CHECKS = {
    "S": [
        # Minimum safety + integrity: 6 critical checks
        "criteria-frontmatter",  # tier itself depends on this
        "whitelist",
        "preflight",
        "handoff-paths",
        "danger-scan",
        "verdict-canonical",
    ],
    "M": [
        # S + 7 more = 13
        "criteria-frontmatter", "whitelist", "preflight", "handoff-paths",
        "danger-scan", "verdict-canonical",
        "handoff-sections",
        "self-acceptance-thinness",
        "iteration-counter",
        "validator-outputs",
        "size-drift",
        "human-directive",   # human reads consilium first, writes directive
        "director-verdict",  # adjudication completeness check
    ],
    "L": [
        # M + 8 more = 21 (all checks)
        "criteria-frontmatter", "whitelist", "preflight", "handoff-paths",
        "danger-scan", "verdict-canonical",
        "handoff-sections", "self-acceptance-thinness", "iteration-counter",
        "validator-outputs", "size-drift", "human-directive", "director-verdict",
        "acceptance-log-paths",
        "executor-iteration-structure",
        "specialist-criteria-ack",
        "validator-output-freshness",
        "cross-val-quotes",
        "trace-schema",
        "slot-language",
        "tasks-decomposition",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-handoff machine checks")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--explain", action="store_true", help="Verbose: show details for each failing check")
    parser.add_argument("--mode", choices=["progress", "ready"], default="progress",
                        help="progress (default): in-progress checks, skips trated as OK. "
                             "ready: pre-submit strict mode, skips for required artefacts (handoff/sections/paths) treated as fail.")
    parser.add_argument("--profile", action="store_true",
                        help="Print per-check ms timings (Tier 14 perf observability)")
    parser.add_argument("--override-checks", default="",
                        help="Comma-separated check names to add on top of tier set (ad-hoc rigour)")
    parser.add_argument("--all-checks", action="store_true",
                        help="Run every check regardless of tier (debug / migration aid)")
    parser.add_argument("--scripts-dir", default=str(Path.home() / ".claude" / "scripts"))
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    scripts_dir = Path(args.scripts_dir).resolve()

    if not eng.exists():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    meta = read_criteria_meta(eng)
    size = (meta.get("size") or "M").upper()
    if size not in {"S", "M", "L"}:
        size = "M"
    ux_heavy = (meta.get("ux_heavy") or "false").lower()
    if ux_heavy not in {"false", "minor", "true"}:
        ux_heavy = "false"

    # Initialize event ledger (no-op when lib.ledger import failed).
    global _RUN_LEDGER
    if _LEDGER_AVAILABLE:
        try:
            _RUN_LEDGER = EventLedger(eng, agent="handoff-precheck", tier=size)
            _RUN_LEDGER.emit(
                "precheck_started",
                node="handoff-precheck:main",
                payload={
                    "mode": args.mode,
                    "tier": size,
                    "ux_heavy": ux_heavy,
                    "all_checks": bool(args.all_checks),
                    "override_checks": args.override_checks or None,
                },
            )
        except Exception as e:
            print(f"WARN: ledger init failed (continuing without ledger): {e}",
                  file=sys.stderr)
            _RUN_LEDGER = None

    # Cheap in-process checks (no subprocess) — run synchronously first.
    # When --profile, wrap each call to record per-check elapsed ms.
    timings: dict[str, float] = {}

    def timed(name: str, fn, *fn_args):
        ts = time.time()
        result = fn(*fn_args)
        timings[name] = (time.time() - ts) * 1000.0
        return result

    # Hard-gate tier dispatch: select check set for current tier.
    # --all-checks overrides tier gating (debug / legacy compatibility).
    if args.all_checks:
        active_checks = set(TIER_CHECKS["L"])
    else:
        active_checks = set(TIER_CHECKS.get(size, TIER_CHECKS["M"]))
    if args.override_checks:
        active_checks |= {c.strip() for c in args.override_checks.split(",") if c.strip()}

    all_fast_specs = [
        ("whitelist",                    check_whitelist,                    (eng,)),
        ("criteria-frontmatter",         check_criteria_frontmatter,         (eng,)),
        ("handoff-sections",             check_handoff_sections,             (eng, size)),
        ("iteration-counter",            check_iteration_counter,            (eng,)),
        ("executor-iteration-structure", check_executor_iteration_structure, (eng,)),
        ("specialist-criteria-ack",      check_specialist_criteria_ack,      (eng,)),
        ("validator-outputs",            check_validator_outputs,            (eng,)),
        ("validator-output-freshness",   check_validator_output_freshness,   (eng,)),
        ("slot-language",                check_slot_language,                (eng,)),
        ("self-acceptance-thinness",     check_self_acceptance_thinness,     (eng, size)),
        ("verdict-canonical",            check_verdict_canonical,            (eng,)),
        ("tasks-decomposition",          check_tasks_decomposition,          (eng, size, ux_heavy)),
        ("human-directive",              check_human_directive,              (eng,)),
    ]
    fast_check_specs = [s for s in all_fast_specs if s[0] in active_checks]
    fast_checks = [timed(n, fn, *a) for n, fn, a in fast_check_specs]

    # Subprocess-bound checks — run concurrently to amortise Python startup cost.
    all_subprocess_jobs = [
        ("preflight",            check_preflight,            (eng, scripts_dir)),
        ("handoff-paths",        check_handoff_paths,        (eng, scripts_dir)),
        ("acceptance-log-paths", check_acceptance_log_paths, (eng, scripts_dir)),
        ("cross-val-quotes",     check_cross_val_quotes,     (eng, scripts_dir, size)),
        ("trace-schema",         check_trace_schema,         (eng, scripts_dir, ux_heavy)),
        ("danger-scan",          check_danger_scan,          (eng, scripts_dir)),
        ("size-drift",           check_size_drift,           (eng, scripts_dir)),
        ("director-verdict",     check_director_verdict,     (eng, scripts_dir)),
    ]
    subprocess_jobs = [j for j in all_subprocess_jobs if j[0] in active_checks]
    slow_checks: list[dict] = []
    parallel_elapsed = 0.0
    if subprocess_jobs:
        t0 = time.time()
        sub_starts = {name: None for name, _, _ in subprocess_jobs}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(subprocess_jobs))) as pool:
            future_to_name = {}
            for name, fn, fn_args in subprocess_jobs:
                sub_starts[name] = time.time()
                future_to_name[pool.submit(fn, *fn_args)] = name
            for fut in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[fut]
                timings[name] = (time.time() - sub_starts[name]) * 1000.0
                slow_checks.append(fut.result())
        parallel_elapsed = time.time() - t0

    # Re-order to canonical sequence; only include checks that actually ran.
    canonical_order = [
        "whitelist", "criteria-frontmatter", "preflight",
        "size-drift", "tasks-decomposition",
        "handoff-paths", "acceptance-log-paths", "handoff-sections",
        "iteration-counter", "executor-iteration-structure",
        "specialist-criteria-ack", "validator-outputs",
        "validator-output-freshness",
        "cross-val-quotes", "trace-schema", "slot-language",
        "danger-scan", "self-acceptance-thinness", "verdict-canonical",
        "human-directive", "director-verdict",
    ]
    by_name = {c["name"]: c for c in (fast_checks + slow_checks)}
    checks = [by_name[n] for n in canonical_order if n in by_name]
    tier_label = "all" if args.all_checks else size

    # Emit per-check results to ledger (silent skips).
    for c in checks:
        _emit_check_result(c.get("name", "?"), c)

    fail_count = sum(1 for c in checks if c["status"] == "fail")
    skip_count = sum(1 for c in checks if c["status"] == "skip")

    warn_count = sum(1 for c in checks if c["status"] == "warn")

    # --mode ready: skips for handoff-time-required checks become fail.
    # Only checks where "skip" can mean "lead didn't write artefact yet" qualify.
    # Checks like executor-iteration-structure skip legitimately on iter=1 (NOT-APPLICABLE),
    # those are excluded — their skip reasons are NA, not incompleteness.
    if args.mode == "ready":
        ready_required = {
            "handoff-paths",       # handoff.md must exist for submit
            "handoff-sections",    # same
            "specialist-criteria-ack",  # executor-reports must exist
            "validator-outputs",   # validators must have run
            "cross-val-quotes",    # if applicable; skip-because-S handled inside check
            "self-acceptance-thinness",  # §7 must exist
        }
        for c in checks:
            if c["status"] == "skip" and c["name"] in ready_required:
                # Distinguish "not applicable" skips (S-tier, iter=1, no traces required) from
                # "lead didn't write artefact" skips. Heuristic: if detail says "not yet written"
                # / "not present" / "no executor-reports yet" → fail. Otherwise let it stand.
                detail_lc = c["detail"].lower()
                lead_didnt_write = any(s in detail_lc for s in [
                    "not yet written", "not present", "no executor-reports yet",
                    "missing", "no validators logged",
                ])
                # ALSO: trace-schema skip when ux_heavy=true and no traces is a fail
                if not lead_didnt_write:
                    continue  # legitimate NA-skip, leave alone
                c["status"] = "fail"
                c["detail"] = f"REQUIRED in --mode ready: {c['detail']}"
                c["fix"] = "Engagement is being submitted but artefact is missing. Lead must complete this before handoff."
                fail_count += 1
                skip_count -= 1

    if args.json:
        out_payload = {
            "engagement": str(eng),
            "tier": tier_label,
            "checks_run": len(checks),
            "fail_count": fail_count,
            "warn_count": warn_count,
            "skip_count": skip_count,
            "status": "fail" if fail_count else ("warn" if warn_count else "pass"),
            "checks": checks,
        }
        if args.profile:
            out_payload["profile_ms"] = {
                k: round(v, 2) for k, v in sorted(timings.items(), key=lambda kv: -kv[1])
            }
            out_payload["profile_total_ms"] = round(sum(timings.values()), 2)
            out_payload["profile_subprocess_parallel_ms"] = round(parallel_elapsed * 1000.0, 2)
        print(json.dumps(out_payload, ensure_ascii=False, indent=2))
    else:
        # TL;DR header
        pass_count = len(checks) - fail_count - skip_count - warn_count
        tier_note = f"[tier={tier_label}, {len(checks)} checks]"
        if fail_count:
            failing = [c["name"] for c in checks if c["status"] == "fail"]
            print(f"Pre-check {tier_note}: {pass_count}/{len(checks)} pass, {warn_count} warn, {fail_count} FAIL ({', '.join(failing)}), {skip_count} skip")
        elif warn_count:
            warning = [c["name"] for c in checks if c["status"] == "warn"]
            print(f"Pre-check {tier_note}: {pass_count}/{len(checks)} pass, {warn_count} WARN ({', '.join(warning)}), {skip_count} skip — engagement {eng.name}")
        else:
            print(f"Pre-check {tier_note}: {pass_count}/{len(checks)} pass, 0 fail, {skip_count} skip — engagement {eng.name}")
        print()

        for c in checks:
            mark = {"pass": "[OK  ]", "fail": "[FAIL]", "warn": "[WARN]", "skip": "[SKIP]"}[c["status"]]
            print(f"{mark} {c['name']}: {c['detail']}")
            if c["status"] == "fail":
                if "fix" in c:
                    print(f"       Fix: {c['fix']}")
                if args.explain and c["name"] in {"handoff-paths", "acceptance-log-paths", "danger-scan", "cross-val-quotes", "trace-schema"}:
                    # Re-run sub-script in human mode for verbose details
                    sub = {
                        "handoff-paths": ["handoff-paths-check.py", str(eng / "handoff.md")],
                        "acceptance-log-paths": ["handoff-paths-check.py", str(eng / "acceptance-log.md")],
                        "danger-scan": ["danger-scan.py", "--engagement", str(eng)],
                        "cross-val-quotes": ["cross-val-check.py", str(eng / "handoff.md")],
                        "trace-schema": ["trace-schema-check.py", str(eng / "traces")],
                    }.get(c["name"])
                    if sub:
                        print(f"       --- {c['name']} verbose output ---")
                        # Defer to subprocess; using common.run() would require import,
                        # but this path is human-mode debug only — inline subprocess is fine.
                        import subprocess
                        try:
                            r = subprocess.run(
                                [sys.executable, str(scripts_dir / sub[0])] + sub[1:],
                                capture_output=True, text=True, timeout=30,
                            )
                            out = (r.stdout + r.stderr).strip()
                        except Exception as e:
                            out = f"error: {e}"
                        for line in out.splitlines()[:25]:
                            print(f"       {line}")
        print()
        if fail_count:
            print(f"VERDICT: FAIL — {fail_count} check(s) failed. Handoff is INCOMPLETE; do not submit / accept.")
            if not args.explain:
                print("       (Re-run with --explain for detailed sub-script output on failures.)")
        elif warn_count:
            print(f"VERDICT: PASS-WITH-WARN — {warn_count} non-blocking concern(s). Director reviews and decides; not auto-rejected.")
        else:
            print(f"VERDICT: PASS — all checks passed ({skip_count} skipped, e.g. handoff not yet written).")

        if args.profile:
            print()
            print("--- Profile (ms per check, slowest first) ---")
            for k, v in sorted(timings.items(), key=lambda kv: -kv[1]):
                print(f"  {v:7.1f}  {k}")
            print(f"  {sum(timings.values()):7.1f}  TOTAL (sum; subprocess wall-clock = "
                  f"{parallel_elapsed*1000:.1f} ms via thread pool)")

    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
