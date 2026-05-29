#!/usr/bin/env python3
"""SkillOpt readiness checker — tells you (in-session) when to run the loop.

Reads the private skill-evolution-log.md, counts LIVE same-class signal buckets
per domain, and reports whether the >=3-same-class trigger for a system-
optimization (SkillOpt) cycle is met.

"Live" excludes:
  - dryrun: true   (synthetic seed signals)
  - resolved:      (already closed by a direct fix)
and a bucket only counts toward readiness if at least one of its signals is
skill/agent-targeted (the loop edits skills/agents — pure script-targeted
signals are direct-fix territory, not loop fuel; they are still listed).

Modes:
  (default)  human report + exit 1 if a cycle is due, else 0.
  --hook     print a single surface-to-user reminder ONLY when due (silent
             otherwise); always exit 0 (safe to wire into a SessionStart hook).
  --json     machine-readable.

Log path: --log PATH, else first match of
  ~/.claude/projects/*/memory/skill-evolution-log.md
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
from collections import defaultdict
from pathlib import Path
from typing import Optional

THRESHOLD = 3
SIGNAL_RE = re.compile(r"^###\s+SIGNAL\s*\|", re.IGNORECASE)
HEADER_RE = re.compile(r"^#{2,}\s+")  # any ## / ### header ends a signal block
DOMAIN_RE = re.compile(r"domain:\s*([A-Za-z]+)", re.IGNORECASE)
CLASS_RE = re.compile(r"^Failure class:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TAXON_RE = re.compile(r"\b(rule_missing|rule_wrong|rule_ignored)\b", re.IGNORECASE)
TRACED_RE = re.compile(r"^Traced to:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
DRYRUN_RE = re.compile(r"^dryrun:\s*true\b", re.IGNORECASE | re.MULTILINE)
RESOLVED_RE = re.compile(r"^resolved:", re.IGNORECASE | re.MULTILINE)


def find_log(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return None
    matches = sorted(base.glob("*/memory/skill-evolution-log.md"))
    return matches[0] if matches else None


def class_key(failure_class: str) -> str:
    """Descriptive problem identity, dropping a trailing taxonomy paren.

    "intake-size-misclassification (rule_wrong)" -> "intake-size-misclassification"
    """
    s = re.sub(r"\s*\(rule_\w+\)\s*$", "", failure_class.strip(), flags=re.IGNORECASE)
    return s.strip().lower()


def parse_signals(text: str) -> list:
    blocks = []
    cur = None
    for ln in text.splitlines():
        if SIGNAL_RE.match(ln):
            if cur is not None:
                blocks.append(cur)
            cur = [ln]
        elif cur is not None:
            if HEADER_RE.match(ln):  # next header (## RESOLUTION / ### CYCLE / ...) ends the block
                blocks.append(cur)
                cur = None
            else:
                cur.append(ln)
    if cur is not None:
        blocks.append(cur)

    out = []
    for blk in blocks:
        header = blk[0]
        body = "\n".join(blk)
        dom = DOMAIN_RE.search(header)
        cls = CLASS_RE.search(body)
        tax = TAXON_RE.search(body)
        traced = TRACED_RE.search(body)
        traced_s = traced.group(1).strip() if traced else ""
        t = traced_s.lower()
        if "agents/" in t or "skills/" in t:
            target = "skill_agent"
        elif "scripts/" in t:
            target = "script"
        else:
            target = "other"
        out.append({
            "domain": dom.group(1).lower() if dom else "?",
            "failure_class": cls.group(1).strip() if cls else "?",
            "class_key": class_key(cls.group(1)) if cls else "?",
            "taxonomy": tax.group(1).lower() if tax else None,
            "traced": traced_s,
            "target": target,
            "dryrun": bool(DRYRUN_RE.search(body)),
            "resolved": bool(RESOLVED_RE.search(body)),
        })
    return out


def analyze(signals):
    live = [s for s in signals if not s["dryrun"] and not s["resolved"]]
    buckets = defaultdict(list)
    for s in live:
        buckets[(s["domain"], s["class_key"])].append(s)
    due = []
    for (dom, ck), sigs in buckets.items():
        loop_actionable = any(s["target"] == "skill_agent" for s in sigs)
        if len(sigs) >= THRESHOLD and loop_actionable:
            due.append((dom, ck, len(sigs)))
    due.sort(key=lambda x: -x[2])
    return live, buckets, due


def main() -> int:
    ap = argparse.ArgumentParser(description="SkillOpt readiness checker")
    ap.add_argument("--log", help="path to skill-evolution-log.md")
    ap.add_argument("--hook", action="store_true",
                    help="silent unless a cycle is due; always exit 0 (SessionStart hook mode)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    log = find_log(args.log)
    if log is None:
        if not args.hook:
            print("skill-evolution-log.md not found (pass --log PATH)", file=sys.stderr)
        return 0
    signals = parse_signals(log.read_text(encoding="utf-8"))
    live, buckets, due = analyze(signals)

    if args.hook:
        # SessionStart hook mode: emit the additionalContext envelope ONLY when a
        # cycle is due; print nothing otherwise. Always exit 0 (never block the
        # session start).
        if due:
            lines = ["A system-optimization (SkillOpt) cycle is DUE — the >=3-same-class "
                     "trigger is met. Surface this to the user as a reminder:"]
            for dom, ck, n in due:
                lines.append(f"- {dom}/{ck}: {n} live signals -> run `прогнать skill-evolution {dom}`")
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(lines),
                }
            }, ensure_ascii=False))
        return 0

    if args.json:
        print(json.dumps({
            "log": str(log),
            "threshold": THRESHOLD,
            "live_count": len(live),
            "buckets": {f"{d}/{c}": len(v) for (d, c), v in buckets.items()},
            "due": [{"domain": d, "class": c, "count": n} for d, c, n in due],
            "ready": bool(due),
        }, ensure_ascii=False, indent=2))
        return 1 if due else 0

    print(f"SkillOpt readiness — {log}")
    print(f"  live signals (excl. dryrun/resolved): {len(live)}  | threshold: >={THRESHOLD} same-class")
    if not buckets:
        print("  no live signal buckets — nothing accumulating.")
    else:
        print("  buckets (domain/class -> count):")
        for (d, c), v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            tgts = sorted(set(s["target"] for s in v))
            actionable = len(v) >= THRESHOLD and any(s["target"] == "skill_agent" for s in v)
            flag = "  <<< DUE" if actionable else ""
            note = "" if any(t == "skill_agent" for t in tgts) else "  [script/other -> direct-fix, not loop fuel]"
            print(f"    {d}/{c}: {len(v)}  ({','.join(tgts)}){flag}{note}")
    print()
    if due:
        print("VERDICT: a SkillOpt cycle is DUE.")
        for d, c, n in due:
            print(f"  -> прогнать skill-evolution {d}   ({c}, {n} signals)")
        return 1
    print("VERDICT: not yet — no (domain,class) bucket has >=3 loop-actionable live signals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
