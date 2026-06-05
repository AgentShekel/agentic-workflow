#!/usr/bin/env python3
"""
Lint: every agent in ~/.claude/agents/*.md must declare a valid model tier in its
frontmatter. Roster-agnostic — unlike the retired assign-agent-models.py it hardcodes
NO agent names, so it never breaks when the roster changes (add / remove / rename an
agent freely). The model policy itself lives in each agent's `model:` frontmatter (the
source of truth); this only guards against drift: a missing line, a typo, or an unknown
tier on a newly-added agent.

Policy reference (categories, not a hardcoded list — see agents' frontmatter for the
authoritative per-agent assignment):
  opus   — top-level leads, per-engagement acceptor managers, system-optimizer directors,
           dev-tech-architect, and verdict-bearing critical validators (code-reviewer,
           security-auditor, skeptic, reality-checker, userspec-adequacy-validator)
  haiku  — mechanical / template-compliance validators
  sonnet — everything else (engineers, designers, analysts, researchers, and
           non-critical deep-reasoning validators)

Run:
  python ~/.claude/scripts/check-agent-models.py          # distribution + violations; exit 1 on any violation
  python ~/.claude/scripts/check-agent-models.py --quiet  # print only violations + exit code
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

AGENTS_DIR = Path(os.path.expanduser("~/.claude/agents"))
VALID_MODELS = ("opus", "sonnet", "haiku")

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MODEL_LINE_RE = re.compile(r"^model:\s*(\S.*?)\s*$", re.MULTILINE)


def model_of(content: str) -> tuple[str | None, str | None]:
    """Return (model, error). error is None when a valid model line is present."""
    fm = FRONTMATTER_RE.match(content)
    if not fm:
        return None, "no frontmatter"
    m = MODEL_LINE_RE.search(fm.group(1))
    if not m:
        return None, "no model: line"
    val = m.group(1).strip()
    if val not in VALID_MODELS:
        return val, f"invalid model {val!r} (want one of {list(VALID_MODELS)})"
    return val, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint agent model frontmatter (roster-agnostic).")
    ap.add_argument("--quiet", action="store_true", help="print only violations")
    args = ap.parse_args()

    files = sorted(AGENTS_DIR.glob("*.md"))
    if not files:
        print(f"no agents found in {AGENTS_DIR}", file=sys.stderr)
        return 2

    counts = {m: 0 for m in VALID_MODELS}
    violations: list[str] = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        model, err = model_of(content)
        if err:
            violations.append(f"{path.name}: {err}")
            continue
        counts[model] += 1

    if not args.quiet:
        dist = " ".join(f"{m}={counts[m]}" for m in VALID_MODELS)
        print(f"agents: {len(files)}  ({dist})")

    for v in violations:
        print(f"VIOLATION {v}")

    if violations:
        print(f"\n{len(violations)} violation(s)")
        return 1
    if not args.quiet:
        print("ok: every agent declares a valid model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
