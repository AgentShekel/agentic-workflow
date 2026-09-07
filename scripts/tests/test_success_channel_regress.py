#!/usr/bin/env python3
"""Regression guard — Channel C (the success channel) in skillopt-ready.py.

Every other input this loop has ever had records a FAILURE: a manager's REJECT, a rework
round, an anti-pattern hit, a reflection about a gap. So every edit the loop authored made
the corpus more suspicious and nothing ever ratcheted back. The gate's false-positive floor
was added as the downstream brake; Channel C is the upstream counterweight, harvesting
`- worked:` bullets so a cycle has something to reinforce and not only something to forbid.

Two ways this can go wrong are silent, and both are pinned here:

  A. WORKED IS NOT A GAP      a `- worked:` bullet must never land in Channel B. If it did,
                              a well-run engagement would push its own domain toward a
                              corrective cycle — the exact inversion this channel exists to
                              prevent.
  B. SUCCESS NEVER TRIGGERS   `ready` stays false when the only material is success. A cycle
                              authors a bounded edit against a defect; opening one because
                              things went well leaves Codex with no failure to close. The
                              fixture carries THREE worked bullets on purpose: Channel B's
                              threshold is 3, so at two the section passed even with the
                              gap-filter deleted, for a reason that had nothing to do with
                              the feature.
  C. THRESHOLD IS 2           reinforcement fires a step earlier than correction (3), and a
                              single worked bullet is still noise.
  D. SKILL/AGENT ONLY         a success traced to a script is a note for the human, not
                              reinforcement fuel — same rule the other channels use.
  E. HISTORICAL FILES         a reflection file written before this channel existed has no
                              `- worked:` lines, so Channel C reads empty rather than
                              re-interpreting old gap bullets.
  F. PAYLOAD IS SCOPED        success_payload() emits only DUE clusters, and honours the
                              domain filter — the workflow hands this straight to Codex.
  G. EMITTER MATCHES CHECKER  reflect-emit.py --kind worked actually writes what the checker
                              harvests. Every fixture here hand-writes `- worked:`, so without
                              this round trip the emitter could keep writing `- target:` and
                              the suite would stay green while the channel stayed empty.

Run standalone or under pytest:
  python test_success_channel_regress.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_skillopt_ready", SCRIPTS_DIR / "skillopt-ready.py")
ready = importlib.util.module_from_spec(_spec)
sys.modules["_skillopt_ready"] = ready
_spec.loader.exec_module(ready)


def mkrefl(root: Path, name: str, body: str, domain: str = "dev") -> Path:
    eng = root / name / "engagement"
    eng.mkdir(parents=True)
    (eng / "criteria.md").write_text(f"---\ndomain: {domain}\nsize: M\n---\n", encoding="utf-8")
    (eng / "engagement-reflections.md").write_text(body, encoding="utf-8")
    return eng


def refl_block(eng: str, date: str, bullets: str, verdict: str = "ACCEPT") -> str:
    return f"## Reflection — {eng} — {date} — verdict: {verdict}\n\n{bullets}\n"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


# A reflection file carrying BOTH kinds, so the split is exercised on one input.
MIXED = refl_block("alpha", "2026-09-01", """- target: skill: validation-pipeline
  class: rule_missing
  observation: no rule required a file:line on a validator finding
  evidence: engagement/validation-outputs/code-reviewer.json
- worked: skill: validation-pipeline
  class: evidence-before-claims
  observation: every finding carried a file:line, so the manager judged on artefacts
  evidence: engagement/validation-outputs/security-auditor.json""")

MIXED2 = refl_block("beta", "2026-09-02", """- worked: skill: validation-pipeline
  class: evidence-before-claims
  observation: same shape held under a second engagement
  evidence: engagement/validation-outputs/skeptic.json""")

# Success traced at a script — recorded, but not reinforcement fuel (D).
SCRIPTY = refl_block("gamma", "2026-09-02", """- worked: scripts/metrics.py
  class: threshold-tuning
  observation: the drift pair caught the ratchet before the gate did
  evidence: engagement/acceptance-log.md
- worked: scripts/metrics.py
  class: threshold-tuning
  observation: held a second time
  evidence: engagement/acceptance-log.md""")

# Pre-Channel-C file: gap bullets only (E).
HISTORICAL = refl_block("delta", "2026-08-20", """- target: agents/dev-lead.md
  class: rule_ignored
  observation: wave plan ignored the disjoint-file rule
  evidence: engagement/plan.md""")


def main() -> int:
    results = []

    print("A. a `worked:` bullet is not a gap")
    recs = ready.parse_reflection_file(MIXED)
    kinds = [r.get("kind") for r in recs]
    results.append(check("both bullets parsed, tagged gap + worked",
                         kinds == ["gap", "worked"], f"got {kinds}"))
    sigs = [ready.reflection_to_signal(r, "dev") for r in recs]
    gap_live, _gap_buckets, _ = ready.analyze_reflections(sigs, set())
    results.append(check("Channel B sees exactly the 1 gap (worked excluded)",
                         len(gap_live) == 1 and gap_live[0]["class_key"] == "rule_missing",
                         f"got {[s['class_key'] for s in gap_live]}"))
    succ_live, _succ_buckets, succ_due = ready.analyze_success(sigs)
    results.append(check("Channel C sees exactly the 1 worked",
                         len(succ_live) == 1, f"got {len(succ_live)}"))

    print("\nC. threshold is 2 (one worked bullet is still noise)")
    results.append(check("1 worked -> not due", not succ_due, f"got {succ_due}"))
    two = [ready.reflection_to_signal(r, "dev")
           for r in ready.parse_reflection_file(MIXED) + ready.parse_reflection_file(MIXED2)]
    s_live, _, s_due = ready.analyze_success(two)
    results.append(check("2 worked on the same target/class -> due",
                         len(s_due) == 1 and s_due[0][3] == 2, f"got {s_due}"))
    results.append(check("SUCCESS_THRESHOLD is 2, THRESHOLD is 3",
                         ready.SUCCESS_THRESHOLD == 2 and ready.THRESHOLD == 3,
                         f"got {ready.SUCCESS_THRESHOLD}/{ready.THRESHOLD}"))

    print("\nD. script-targeted success is recorded but is not fuel")
    scripty = [ready.reflection_to_signal(r, "dev") for r in ready.parse_reflection_file(SCRIPTY)]
    sc_live, _, sc_due = ready.analyze_success(scripty)
    results.append(check("2 script-targeted worked bullets are live but not due",
                         len(sc_live) == 2 and not sc_due, f"live={len(sc_live)} due={sc_due}"))

    print("\nE. a pre-Channel-C reflection file yields an empty success channel")
    hist = [ready.reflection_to_signal(r, "dev") for r in ready.parse_reflection_file(HISTORICAL)]
    h_live, _, _ = ready.analyze_success(hist)
    hg_live, _, _ = ready.analyze_reflections(hist, set())
    results.append(check("no worked bullets -> Channel C empty, Channel B intact",
                         not h_live and len(hg_live) == 1, f"C={len(h_live)} B={len(hg_live)}"))

    print("\nF. payload carries only due clusters, and honours the domain filter")
    payload = ready.success_payload(s_live, s_due)
    results.append(check("both due records emitted", len(payload) == 2, f"got {len(payload)}"))
    results.append(check("records carry target + class + engagement",
                         all(p.get("primary_target") and p.get("class_key") and p.get("engagement")
                             for p in payload), f"got {payload}"))
    results.append(check("a non-matching domain filter emits nothing",
                         ready.success_payload(s_live, s_due, "marketing") == [],
                         f"got {ready.success_payload(s_live, s_due, 'marketing')}"))
    results.append(check("no-due -> empty payload",
                         ready.success_payload(succ_live, []) == []))

    print("\nB. success alone never makes a cycle due (live subprocess)")
    # THREE worked bullets, not two, and that number is the whole point of this section.
    # Channel B's threshold is 3. With a 2-bullet fixture, deleting the `kind == "gap"` filter
    # from analyze_reflections leaves ready=False anyway — the bullets simply sit under the
    # corrective threshold — so the section passed on a build with the feature removed. At 3,
    # a broken build flips to ready=True / rc=1 and this fails for the reason it claims.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, eng in enumerate(("alpha", "beta", "gamma")):
            mkrefl(root, eng, refl_block(eng, f"2026-09-0{i + 1}", f"""- worked: skill: validation-pipeline
  class: evidence-before-claims
  observation: clean run {i + 1}, findings carried file:line
  evidence: engagement/validation-outputs/skeptic.json"""))
        log = root / "skill-evolution-log.md"
        log.write_text("# Skill evolution log\n\n(no signals)\n", encoding="utf-8")
        # --reflection-window-days 0 disables the recency cut. Channel C inherits Channel B's
        # 90-day window, so dated fixtures would silently stop being harvested once they aged
        # past it and this section would fail on a calendar date rather than on a code change.
        base_argv = [sys.executable, str(SCRIPTS_DIR / "skillopt-ready.py"), "--json",
                     "--log", str(log), "--reflection-root", str(root),
                     "--reflection-window-days", "0"]

        def run_json(argv):
            proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", check=False)
            try:
                return proc, json.loads(proc.stdout)
            except Exception as e:  # noqa: BLE001
                results.append(check("script emitted parseable JSON", False,
                                     f"{e}\n         stdout={proc.stdout[:400]}"
                                     f"\n         stderr={proc.stderr[:400]}"))
                return proc, None

        proc, out = run_json(base_argv)
        # No `if out:` guard. A build that emits nothing must FAIL these invariants, not skip
        # them: silently unrun checks are what let a broken feature ship green.
        results.append(check("ready == false with success-only material",
                             bool(out) and out.get("ready") is False,
                             f"ready={out.get('ready') if out else '(no json)'}"))
        results.append(check("exit code 0 (nothing due)", proc.returncode == 0,
                             f"rc={proc.returncode}"))
        results.append(check("no Channel-B cluster was minted from worked bullets",
                             bool(out) and not (out.get("reflection_due") or []),
                             f"got {out.get('reflection_due') if out else '(no json)'}"))
        results.append(check("success_due is nevertheless reported",
                             bool(out) and len(out.get("success_due") or []) == 1,
                             f"got {out.get('success_due') if out else '(no json)'}"))
        results.append(check("success_signals ride along for the reflect step",
                             bool(out) and len(out.get("success_signals") or []) == 3,
                             f"got {out.get('success_signals') if out else '(no json)'}"))
        _, off = run_json(base_argv + ["--no-success"])
        results.append(check("--no-success is honoured",
                             bool(off) and off.get("success_count") == 0,
                             f"got {off.get('success_count') if off else '(no json)'}"))

    print("\nG. the emitter and the checker agree (live round trip)")
    # Nothing else pins this seam. Every fixture above hard-codes `- worked:` by hand, so
    # reflect-emit.py could go on writing `- target:` for --kind worked and this file would
    # still be green while the channel stayed empty in the field.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for eng in ("one", "two"):
            d = root / eng / "engagement"
            d.mkdir(parents=True)
            (d / "criteria.md").write_text("---\ndomain: dev\nsize: M\n---\n", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "reflect-emit.py"), str(d),
                 "--kind", "worked", "--target", "skill: validation-pipeline",
                 "--class", "evidence-before-claims",
                 "--observation", "findings carried file:line",
                 "--evidence", "engagement/validation-outputs/code-reviewer.json",
                 "--verdict", "ACCEPT", "--quiet"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        emitted = (root / "one" / "engagement" / "engagement-reflections.md").read_text(encoding="utf-8")
        results.append(check("emitter writes a `- worked:` bullet, not `- target:`",
                             "- worked:" in emitted and "- target:" not in emitted,
                             f"got {emitted[-200:]!r}"))
        log = root / "skill-evolution-log.md"
        log.write_text("# Skill evolution log\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "skillopt-ready.py"), "--json", "--log", str(log),
             "--reflection-root", str(root), "--reflection-window-days", "0"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        try:
            rt = json.loads(proc.stdout)
        except Exception:  # noqa: BLE001
            rt = None
        results.append(check("checker harvests what the emitter wrote as a due C cluster",
                             bool(rt) and len(rt.get("success_due") or []) == 1
                             and rt["success_due"][0]["count"] == 2,
                             f"got {rt.get('success_due') if rt else proc.stdout[:200]}"))
        results.append(check("and it still does not make a cycle due",
                             bool(rt) and rt.get("ready") is False,
                             f"ready={rt.get('ready') if rt else '(no json)'}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_success_channel_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
