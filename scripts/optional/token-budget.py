#!/usr/bin/env python3
"""Engagement token-budget guard.

Per `engagement-protocol` §"Token budget" (Tier 14): each tier has an empirical
budget envelope. Going over without a deliberate scope-sync = silent token bleed.

Tier baselines (lead + director combined; one full iteration):
  S  100,000 tokens — small fixes, no multi-specialist
  M  500,000 tokens — landing/dashboard/feature, 2-3 specialists, possibly minor ux_heavy
  L  1,500,000 tokens — rebrand / multi-wave / cross-domain

Inputs:
  - engagement/iteration  (current iter)
  - engagement/criteria.md frontmatter `size`
  - ~/.claude/projects/{project}/metrics.jsonl (cumulative tokens for the engagement, IF
    director writes the optional `tokens_used` field per iteration)

Output behaviour:
  - exit 0 if cumulative usage ≤ 80% of tier budget × current iter (linear).
  - exit 0 with WARN if 80% < usage ≤ 100%.
  - exit 1 if usage > 100% — engagement is over-budget. Lead must either:
      (a) auto-promote tier (S→M, M→L) via size-detect.py — natural growth,
      (b) escalate user with scope-sync proposal — pure scope creep, or
      (c) accept under-deliver and ship with `## Known deferrals` in handoff.

If `metrics.jsonl` has no `tokens_used` records, script estimates from
`duration_s` proxy (≈800 tokens / second director-time, empirical from real test).
This is a fallback — accuracy improves once director starts writing the field.

Usage:
  python ~/.claude/scripts/token-budget.py engagement/ --json
  python ~/.claude/scripts/token-budget.py engagement/ --project my-app
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import re
import sys
from pathlib import Path

TIER_BUDGET = {
    "S": 100_000,
    "M": 500_000,
    "L": 1_500_000,
}

# Empirical fallback — duration_s × 800 ≈ tokens (lead+director combined per iter)
DURATION_TO_TOKENS = 800

# Warning thresholds as fraction of (tier_budget × iter)
WARN_FRACTION = 0.8
HARD_FRACTION = 1.0


def read_size(eng: Path) -> str:
    crit = eng / "criteria.md"
    if not crit.exists():
        return "M"
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return "M"
    m = re.search(r"^size\s*:\s*(\S+)", fm.group(1), re.MULTILINE)
    if not m:
        return "M"
    s = m.group(1).strip().strip('"').strip("'").upper()
    return s if s in TIER_BUDGET else "M"


def read_engagement_name(eng: Path) -> str:
    crit = eng / "criteria.md"
    if not crit.exists():
        return eng.parent.name or "unknown"
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return eng.parent.name or "unknown"
    m = re.search(r"^engagement\s*:\s*(\S+)", fm.group(1), re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else (eng.parent.name or "unknown")


def read_iter(eng: Path) -> int:
    f = eng / "iteration"
    if not f.exists():
        return 1
    try:
        return max(1, int(f.read_text(encoding="utf-8").strip()))
    except Exception:
        return 1


def collect_records(project_root: Path, eng_name: str) -> list[dict]:
    log = project_root / "metrics.jsonl"
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("engagement") == eng_name:
            out.append(r)
    return out


def estimate_usage(records: list[dict]) -> tuple[int, str]:
    """Sum tokens across recorded iterations. Falls back to duration_s × DURATION_TO_TOKENS
    when a record has no `tokens_used`. Returns (total_tokens, source_note)."""
    direct_total = 0
    proxy_total = 0
    direct_count = 0
    proxy_count = 0
    for r in records:
        if isinstance(r.get("tokens_used"), (int, float)):
            direct_total += int(r["tokens_used"])
            direct_count += 1
        elif isinstance(r.get("duration_s"), (int, float)):
            proxy_total += int(r["duration_s"]) * DURATION_TO_TOKENS
            proxy_count += 1
    total = direct_total + proxy_total
    if direct_count and proxy_count:
        note = f"{direct_count} direct + {proxy_count} duration-proxy ({DURATION_TO_TOKENS}/sec)"
    elif direct_count:
        note = f"{direct_count} direct"
    elif proxy_count:
        note = f"{proxy_count} duration-proxy ({DURATION_TO_TOKENS}/sec, no tokens_used field yet)"
    else:
        note = "no metrics yet"
    return total, note


def project_root_for_engagement(eng: Path, projects_root: Path) -> Path | None:
    """Try to find the project's metrics directory by matching project name
    in the engagement path or via current working dir."""
    # Engagement is typically at <project>/engagement/ — go up one level
    project_path = eng.parent.resolve()
    project_name = project_path.name
    # ~/.claude/projects/ uses dash-encoded paths (e.g. C--work-projects-my-app)
    # so we try a few fallbacks
    candidates = [
        projects_root / project_name,  # exact name match
        projects_root / project_path.as_posix().replace("/", "-").replace(":", "-").lstrip("-"),  # path-encoded
    ]
    for c in candidates:
        if c.exists():
            return c
    # Last resort: scan all projects, pick the one with our engagement name in metrics
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Token-budget guard for engagement")
    p.add_argument("engagement", help="Path to engagement/ directory")
    p.add_argument("--project", help="Project name (folder under ~/.claude/projects); "
                                     "auto-detected if omitted")
    p.add_argument("--projects-root", default=str(Path.home() / ".claude" / "projects"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    size = read_size(eng)
    eng_name = read_engagement_name(eng)
    cur_iter = read_iter(eng)
    budget_per_iter = TIER_BUDGET[size]
    cumulative_budget = budget_per_iter * cur_iter

    projects_root = Path(args.projects_root)
    project_root: Path | None = None
    if args.project:
        project_root = projects_root / args.project
    else:
        project_root = project_root_for_engagement(eng, projects_root)
    records: list[dict] = []
    if project_root and project_root.exists():
        records = collect_records(project_root, eng_name)

    total_used, note = estimate_usage(records)
    fraction = total_used / cumulative_budget if cumulative_budget else 0.0

    if fraction <= WARN_FRACTION:
        status = "ok"
        verdict = f"on budget ({fraction:.1%})"
        exit_code = 0
    elif fraction <= HARD_FRACTION:
        status = "warn"
        verdict = f"approaching budget ({fraction:.1%}); plan finishing strategy"
        exit_code = 0
    else:
        status = "fail"
        verdict = f"over budget ({fraction:.1%}); auto-promote, scope-sync, or known-deferrals required"
        exit_code = 1

    result = {
        "engagement": eng_name,
        "size": size,
        "iter": cur_iter,
        "tier_budget": budget_per_iter,
        "cumulative_budget": cumulative_budget,
        "tokens_used": total_used,
        "fraction": round(fraction, 4),
        "status": status,
        "verdict": verdict,
        "data_source": note,
        "metrics_records": len(records),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code

    flag = {"ok": "[OK  ]", "warn": "[WARN]", "fail": "[FAIL]"}[status]
    print(f"{flag} token-budget {eng_name}")
    print(f"  size={size} iter={cur_iter} budget/iter={budget_per_iter:,} cumulative={cumulative_budget:,}")
    print(f"  used={total_used:,} fraction={fraction:.1%} ({note})")
    print(f"  verdict: {verdict}")
    if status == "fail":
        print()
        print("  Fix options:")
        print("  (a) auto-promote: python ~/.claude/scripts/size-detect.py engagement/ "
              "--mode runtime --auto-promote")
        print("      — if scope grew naturally, ratchet tier up so budget resizes.")
        print("  (b) scope-sync with user: surface deferrals via director-mediated escalation,")
        print("      record reduced scope in scope-sync.md, criteria.md trims locked.")
        print("  (c) accept partial: ship what's done, list remainder in handoff §11 Known deferrals.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
