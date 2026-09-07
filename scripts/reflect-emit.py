#!/usr/bin/env python3
"""Thin CLI to append ONE reflection to engagement/engagement-reflections.md.

S4 stopgap (2026-06-12). The pre-gate Workflow's resumeFromRunId is a SINGLE-SESSION
run-journal, so a multi-day L engagement that exceeds one Workflow invocation gets
hand-driven across sessions and never reaches the acceptance seam — where the manager
would normally write engagement-reflections.md. Result: the richest real engagements
emit ZERO reflections and are invisible to the self-learning loop (the SkillOpt harvest
reads engagement-reflections.md). See the design note:
  _plan_scratch/s4-cross-session-continuation-design-2026-06-12.md

This shim lets a hand-driver (or any markdown agent that can run a one-line Bash command,
but cannot import the Python libs) emit a reflection MID-FLIGHT, at a session boundary,
in the exact on-disk format the harvest already reads — so the experience is captured
without waiting for an acceptance that may never come in one session. Sibling of
ledger-emit.py (which does the same for events.jsonl).

Design: BEST-EFFORT. Observability must never break real work. Any failure (engagement
dir absent, write error, etc.) prints a WARNING to stderr and exits 0. Only a structurally
malformed CLI invocation (missing a required arg) exits non-zero (argparse, exit 2).

Canonical block appended (matches acceptance-protocol §"Per-engagement reflection"):
    ## Reflection — <engagement> — <date> — verdict: <verdict>
    - target: <target>
      class: <class>
      observation: <observation>
      evidence: <evidence>

`class` is one of the rule_* taxonomy (rule_missing/rule_wrong/rule_ignored) when the
signal points at a skill/agent rule (these feed the SkillOpt cluster count), OR a
non-rule tag (engine_targeted/script_targeted/observation/near_miss) for engine/script
signals (recorded for the director sweep, excluded from the SkillOpt readiness check by
the `Failure class:`-line parser in skillopt-ready.py).

`--kind worked` emits the same block under a `- worked:` bullet instead — Channel C, the
success side. Everything else this system records is a failure, so every edit the loop has
ever authored pushed the corpus toward suspicion and nothing pushed back. A worked bullet
names a behaviour that CARRIED an engagement, so a cycle has something to reinforce and not
only something to forbid. Its `class` is a short reinforcement slug (what the behaviour was),
not a rule_* token. Two of them on one target make it reinforcement fuel; they never open a
cycle by themselves.

Usage:
  python ~/.claude/scripts/reflect-emit.py ENGAGEMENT \
      --target "engine: engagement-workflow.js code-mode" \
      --class engine_targeted \
      --observation "worktree isolation void under containerized bind-mount-root tests" \
      --evidence "engagement/NEXT-SESSION-PROMPT.md ⚠️ block" \
      --session 4 --phase deliver

  python ~/.claude/scripts/reflect-emit.py ENGAGEMENT --kind worked \
      --target "skill: validation-pipeline" \
      --class evidence-before-claims \
      --observation "every validator finding carried a file:line, so the manager judged on artefacts" \
      --evidence "engagement/validation-outputs/code-reviewer.json"
"""

from __future__ import annotations

import sys as _sys

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import datetime
import sys
from pathlib import Path

REFLECTIONS_HEADER = (
    "# Engagement reflections — {name}\n\n"
    "> M/L per-engagement reflections (acceptance-protocol §\"Per-engagement reflection\").\n"
    "> Append-only. rule_missing/rule_wrong/rule_ignored feed the SkillOpt cluster count;\n"
    "> engine/script-targeted signals are recorded for the director sweep but excluded from\n"
    "> the readiness check. `- worked:` bullets are the success channel (Channel C):\n"
    "> reinforcement fuel for a cycle some failure already earned, never a trigger.\n"
    "> Mid-flight entries (verdict IN-PROGRESS) are emitted by\n"
    "> reflect-emit.py on hand-driven cross-session engagements (S4 stopgap).\n\n"
)


def _warn(msg: str) -> None:
    print(f"WARNING [reflect-emit]: {msg} (reflection not recorded; continuing)",
          file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append one reflection to engagement/engagement-reflections.md "
                    "(best-effort; never blocks real work).",
    )
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--target", required=True,
                        help='What the signal points at, e.g. "skill: validation-pipeline" '
                             'or "engine: engagement-workflow.js code-mode"')
    parser.add_argument("--kind", choices=("gap", "worked"), default="gap",
                        help="gap (default) = a failure signal, emitted as `- target:` "
                             "(Channel B). worked = a behaviour that carried the "
                             "engagement, emitted as `- worked:` (Channel C, reinforcement "
                             "fuel at >=2 on one target; never opens a cycle by itself)")
    parser.add_argument("--class", dest="klass", required=True,
                        help="For --kind gap: rule_missing | rule_wrong | rule_ignored "
                             "(feed SkillOpt) | engine_targeted | script_targeted | "
                             "observation | near_miss (director sweep only). "
                             "For --kind worked: a short reinforcement slug naming the "
                             "behaviour, e.g. evidence-before-claims")
    parser.add_argument("--observation", required=True,
                        help="The reflection body — what happened and why it matters")
    parser.add_argument("--evidence", help="Path(s) / signal(s) backing the observation")
    parser.add_argument("--engagement-name",
                        help="Engagement name for the heading; default = engagement dir's parent name")
    parser.add_argument("--date", help="ISO date YYYY-MM-DD; default = today")
    parser.add_argument("--verdict", default="IN-PROGRESS (mid-flight)",
                        help="Verdict line; default 'IN-PROGRESS (mid-flight)' for hand-driven entries")
    parser.add_argument("--session", help="Session number/marker (cross-session hand-drive)")
    parser.add_argument("--phase", help="Engagement phase this reflection was emitted from")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress the success line")
    args = parser.parse_args()

    # --- everything below is best-effort: soft-fail returns exit 0 ---
    eng = Path(args.engagement)
    if not eng.exists() or not eng.is_dir():
        _warn(f"engagement directory not found: {eng}")
        return 0

    try:
        name = args.engagement_name or (eng.parent.name if eng.name == "engagement" else eng.name)
        date = args.date or datetime.date.today().isoformat()
        ref = eng / "engagement-reflections.md"

        tail = []
        if args.session:
            tail.append(f"session {args.session}")
        if args.phase:
            tail.append(f"phase {args.phase}")
        suffix = f" ({', '.join(tail)})" if tail else ""

        block_lines = [
            f"## Reflection — {name} — {date} — verdict: {args.verdict}{suffix}",
            "",
            f"- {'worked' if args.kind == 'worked' else 'target'}: {args.target}",
            f"  class: {args.klass}",
            f"  observation: {args.observation}",
        ]
        if args.evidence:
            block_lines.append(f"  evidence: {args.evidence}")
        block = "\n".join(block_lines) + "\n"

        if not ref.exists():
            ref.write_text(REFLECTIONS_HEADER.format(name=name) + block, encoding="utf-8")
        else:
            existing = ref.read_text(encoding="utf-8")
            sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
            ref.write_text(existing + sep + block, encoding="utf-8")
    except Exception as e:
        _warn(f"append failed ({e})")
        return 0

    if not args.quiet:
        print(f"reflection appended to {ref}  [{args.kind}/{args.klass}] {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
