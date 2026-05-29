#!/usr/bin/env python3
"""Scaffold engagement/human-directive.md from CLI args.

Used in the chat-driven supreme-judge flow: human reads consilium summary
(presented inline in chat by director or coordinating agent), responds with
short verdict in chat. Coordinating agent then invokes this script to write
the well-formed human-directive.md file (which director and handoff-precheck
expect on disk).

Three decision modes:
  PROCEED_TO_VERDICT — director writes formal verdict per consilium
  REJECT_NOW         — director writes minimal REJECT, lead reworks per --reasons
  DIRECTED_VERDICT   — director writes verdict constrained by --address / --override

Usage:
  # Simple PROCEED — director synthesizes per consilium normally
  python ~/.claude/scripts/human-directive.py engagement/ --decision PROCEED

  # PROCEED with brief context note for director
  python ~/.claude/scripts/human-directive.py engagement/ --decision PROCEED \\
      --note "trust the consilium; take SUSTAINED on critical, OVERRULE minor"

  # REJECT — fast loop without long director adjudication
  python ~/.claude/scripts/human-directive.py engagement/ --decision REJECT \\
      --reasons "fix CSRF gap; add dark mode toggle"

  # DIRECTED — pre-decide on specific findings or disagreements
  python ~/.claude/scripts/human-directive.py engagement/ --decision DIRECTED \\
      --address "finding-1, finding-3" \\
      --override "SIDED WITH codex-blind on auth disagreement; haiku catch is REAL"

  # Append rework hint (works with REJECT_NOW or DIRECTED_VERDICT)
  python ~/.claude/scripts/human-directive.py engagement/ --decision REJECT \\
      --reasons "scope was wrong" --revise-criteria "drop dark-mode bullet"

  # Free-form mode — pass full directive body via stdin
  echo "Decision: PROCEED_TO_VERDICT
   Custom note: ..." | python ~/.claude/scripts/human-directive.py engagement/ --raw

Aliases:
  --decision accepts: PROCEED, PROCEED_TO_VERDICT, GO, OK
                      REJECT, REJECT_NOW, NO, RW (rework)
                      DIRECTED, DIRECTED_VERDICT, MIXED, PARTIAL

Exit codes:
  0 — directive written
  1 — directive already exists for current iteration (use --overwrite)
  2 — invocation error
"""

from __future__ import annotations
import sys as _sys

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import sys
from datetime import datetime
from pathlib import Path

DECISION_ALIASES = {
    "PROCEED": "PROCEED_TO_VERDICT",
    "PROCEED_TO_VERDICT": "PROCEED_TO_VERDICT",
    "GO": "PROCEED_TO_VERDICT",
    "OK": "PROCEED_TO_VERDICT",
    "ACCEPT_PATH": "PROCEED_TO_VERDICT",

    "REJECT": "REJECT_NOW",
    "REJECT_NOW": "REJECT_NOW",
    "NO": "REJECT_NOW",
    "RW": "REJECT_NOW",
    "REWORK": "REJECT_NOW",

    "DIRECTED": "DIRECTED_VERDICT",
    "DIRECTED_VERDICT": "DIRECTED_VERDICT",
    "MIXED": "DIRECTED_VERDICT",
    "PARTIAL": "DIRECTED_VERDICT",
}


def read_iter_counter(eng: Path) -> int:
    counter = eng / "iteration"
    if counter.exists():
        try:
            return int(counter.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


def normalize_decision(raw: str) -> str | None:
    if not raw:
        return None
    return DECISION_ALIASES.get(raw.strip().upper())


def build_directive_body(
    decision: str,
    iter_n: int,
    note: str | None,
    reasons: list[str],
    address: list[str],
    overrides: list[str],
    revise_criteria: str | None,
    abandon_reason: str | None,
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    lines.append("---")
    lines.append("role: supreme-judge")
    lines.append("read_after: consilium-summary.md")
    lines.append("---")
    lines.append("")
    lines.append(f"## Human directive — iter {iter_n} — {ts}")
    lines.append("")
    lines.append(f"Decision: {decision}")
    lines.append("")

    if decision == "PROCEED_TO_VERDICT":
        if note:
            lines.append(f"Note for director: {note}")
        else:
            lines.append("Director: synthesize verdict per consilium normally. "
                         "Address all signals with required adjudication markers.")
        lines.append("")
    elif decision == "REJECT_NOW":
        if reasons:
            lines.append("Rework targets:")
            for r in reasons:
                lines.append(f"- {r.strip()}")
            lines.append("")
        if revise_criteria:
            lines.append(f"Or revise criteria: {revise_criteria}")
            lines.append("")
        if abandon_reason:
            lines.append(f"Or abandon: {abandon_reason}")
            lines.append("")
        if not (reasons or revise_criteria or abandon_reason):
            lines.append("Director: minimal REJECT verdict. Lead reworks per consilium-summary findings.")
            lines.append("")
    elif decision == "DIRECTED_VERDICT":
        if address:
            lines.append("Mandatory address (director must include in verdict):")
            for a in address:
                lines.append(f"- {a.strip()}")
            lines.append("")
        if overrides:
            lines.append("Overrides on disputed findings (director must apply):")
            for o in overrides:
                lines.append(f"- {o.strip()}")
            lines.append("")
        if note:
            lines.append(f"Additional note: {note}")
            lines.append("")
        if not (address or overrides or note):
            lines.append("Director: write verdict at your discretion within consilium signals; "
                         "no specific overrides from human.")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold human-directive.md from CLI args")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--decision", "-d", help="Decision (alias OK): PROCEED | REJECT | DIRECTED")
    parser.add_argument("--note", "-n", help="Brief note for director (PROCEED_TO_VERDICT or DIRECTED_VERDICT)")
    parser.add_argument("--reasons", "-r", action="append", default=[],
                        help="REJECT_NOW: reason for rework (repeatable). Or use comma-separated string.")
    parser.add_argument("--address", "-a", action="append", default=[],
                        help="DIRECTED_VERDICT: finding to mandatorily address (repeatable / comma-sep)")
    parser.add_argument("--override", "-o", action="append", default=[],
                        help="DIRECTED_VERDICT: pre-decided override on a disputed finding (repeatable / comma-sep)")
    parser.add_argument("--revise-criteria", help="REJECT_NOW: instead of rework, revise criteria.md")
    parser.add_argument("--abandon", help="REJECT_NOW: abandon engagement with reason")
    parser.add_argument("--raw", action="store_true",
                        help="Read full directive body from stdin (escape hatch for free-form)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing human-directive.md (default: refuse if exists)")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    iter_n = args.iter if args.iter is not None else read_iter_counter(eng)
    target = eng / "human-directive.md"

    if target.exists() and not args.overwrite:
        # Check if it's for the current iter — if so, refuse; if older, allow rewrite
        existing = target.read_text(encoding="utf-8")
        if f"iter {iter_n}" in existing:
            print(f"ERROR: human-directive.md already exists for iter {iter_n}. "
                  f"Use --overwrite or read it first to confirm intent: {target}",
                  file=sys.stderr)
            return 1
        # Older iter — append, don't overwrite

    # Raw mode — body from stdin
    if args.raw:
        body = sys.stdin.read().rstrip() + "\n"
        target.write_text(body, encoding="utf-8")
        print(f"Wrote (raw mode): {target}")
        return 0

    # Decision required
    if not args.decision:
        print("ERROR: --decision required (PROCEED | REJECT | DIRECTED) "
              "unless --raw used", file=sys.stderr)
        return 2

    decision = normalize_decision(args.decision)
    if not decision:
        print(f"ERROR: unknown --decision={args.decision!r}. "
              f"Accepted: {sorted(set(DECISION_ALIASES.values()))} "
              f"or aliases: {sorted(DECISION_ALIASES.keys())}", file=sys.stderr)
        return 2

    # Flatten comma-separated values
    def flatten(raw_list: list[str]) -> list[str]:
        out = []
        for item in raw_list:
            for piece in item.split(";"):
                for p in piece.split(","):
                    p = p.strip()
                    if p:
                        out.append(p)
        return out

    reasons = flatten(args.reasons)
    address = flatten(args.address)
    overrides = flatten(args.override)

    body = build_directive_body(
        decision=decision,
        iter_n=iter_n,
        note=args.note,
        reasons=reasons,
        address=address,
        overrides=overrides,
        revise_criteria=args.revise_criteria,
        abandon_reason=args.abandon,
    )

    # If existing for older iter, append rather than overwrite
    if target.exists() and not args.overwrite:
        existing = target.read_text(encoding="utf-8")
        target.write_text(existing.rstrip() + "\n\n---\n\n" + body, encoding="utf-8")
        print(f"Appended new directive (iter {iter_n}) to: {target}")
    else:
        target.write_text(body, encoding="utf-8")
        print(f"Wrote: {target} (Decision: {decision}, iter {iter_n})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
