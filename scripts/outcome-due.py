#!/usr/bin/env python3
"""Surfaces outcome hypotheses whose check date has arrived.

`agency-intake` makes every engagement write an `## Outcome hypothesis` with a `check on:`
date, and tells the human to close it with an `outcome_check` ledger event. Nothing carried
the date forward. A hypothesis whose closing half depends on someone remembering a date
written weeks earlier is a hypothesis that never closes, and `outcome_validation_rate` in
metrics.py stays at `no data` forever while looking like an ordinary empty metric.

This walks the engagement roots, reads each `criteria.md` for a hypothesis and its date, and
reports the ones that are due and unclosed. Due means: the date has passed, and no
`outcome_check` event exists in that engagement's `events.jsonl`.

A `metric: none` hypothesis (declared infrastructure work with no user-visible effect) is
honest and closed by construction; it is not reported.

Modes: (default) human report, exit 1 when something is due; --hook (silent unless due, always
exit 0, SessionStart-safe); --json.
"""
from __future__ import annotations

import sys as _sys

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import datetime as dt
import json
import re
from pathlib import Path

ROOTS = [Path("C:/work-projects")]
# Covers engagement/, engagement-archived/, engagement-aborted/ and any nested per-domain or
# per-phase subdirectory, so a hypothesis cannot go unseen because of where it was filed.
# Named explicitly rather than as `engagement*`: that glob also swept in directories like
# `engagement-notes/`, reporting a stray document as if it were an engagement.
_ENGAGEMENT_DIRS = ("engagement", "engagement-archived", "engagement-aborted")
# `**` rather than a fixed set of depths: engagements nest by phase and by domain, and a
# hand-counted depth limit is a hypothesis silently going unseen at depth three.
ENGAGEMENT_GLOBS = tuple(f"*/{d}/**/criteria.md" for d in _ENGAGEMENT_DIRS) + \
                   tuple(f"*/{d}/criteria.md" for d in _ENGAGEMENT_DIRS)

HYPOTHESIS_RE = re.compile(r"^##\s*Outcome hypothesis\s*$(.*?)(?=^##\s|\Z)",
                           re.MULTILINE | re.DOTALL | re.IGNORECASE)
# `\**` tolerates bold labels — `- **check on:** 2026-08-26` is ordinary Markdown and an
# unbolded-only regex silently treats such an engagement as having no hypothesis at all.
DATE_RE = re.compile(r"^\s*[-*]?\s*\**\s*check\s+on:?\**:?\s*\**\s*(\d{4}-\d{2}-\d{2})",
                     re.MULTILINE | re.IGNORECASE)
METRIC_RE = re.compile(r"^\s*[-*]?\s*\**\s*metric:?\**:?\s*\**\s*(.+?)\s*\**$",
                       re.MULTILINE | re.IGNORECASE)
PLACEHOLDER = re.compile(r"^\s*\{.*\}\s*$")


def has_outcome_check(eng: Path) -> bool:
    ledger = eng / "events.jsonl"
    if not ledger.exists():
        return False
    try:
        for line in ledger.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line or "outcome_check" not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            # A valid JSON line need not be an object; `["outcome_check"]` used to crash the
            # whole scan on .get(), taking every other engagement's report down with it.
            if not isinstance(event, dict) or event.get("payload_type") != "outcome_check":
                continue
            # `payload` is not guaranteed to be an object either. And a result is what closes
            # a hypothesis: metrics.py reads payload.result, so an event without one records
            # that someone looked rather than what they found. A whitespace-only string is
            # not a finding — it was truthy, and it used to silence the reminder.
            payload = event.get("payload")
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, str) and result.strip():
                return True
    except OSError:
        return False
    return False


def scan(today: dt.date, roots: list[Path]) -> list[dict]:
    due = []
    # One `seen` set across ALL roots, keyed on the resolved path: overlapping roots (a parent
    # and a child passed together) would otherwise report the same engagement twice.
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in ENGAGEMENT_GLOBS:
            for crit in root.glob(pattern):
                crit = crit.resolve()
                if crit in seen:
                    continue
                seen.add(crit)
                try:
                    text = crit.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                block = HYPOTHESIS_RE.search(text)
                if not block:
                    continue
                body = block.group(1)
                metric = METRIC_RE.search(body)
                metric_val = metric.group(1).strip() if metric else ""
                # A declared no-effect hypothesis is closed by construction. So is an
                # unfilled template: reporting a placeholder as "due" trains people to
                # ignore the report. `none` matches as a WHOLE WORD: a prefix test
                # skipped "nonequilibrium concentration", a real metric.
                if re.match(r"none\b", metric_val, re.IGNORECASE) or PLACEHOLDER.match(metric_val):
                    continue
                d = DATE_RE.search(body)
                if not d or PLACEHOLDER.match(d.group(1)):
                    continue
                try:
                    check_on = dt.date.fromisoformat(d.group(1))
                except ValueError:
                    continue
                if check_on > today:
                    continue
                eng = crit.parent
                if has_outcome_check(eng):
                    continue
                due.append({"engagement": str(eng), "check_on": check_on.isoformat(),
                            "days_overdue": (today - check_on).days,
                            "metric": metric_val[:120]})
    due.sort(key=lambda x: -x["days_overdue"])
    return due


def main() -> int:
    ap = argparse.ArgumentParser(description="Outcome hypotheses due for their check")
    ap.add_argument("--hook", action="store_true",
                    help="silent unless something is due; always exit 0")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests")
    ap.add_argument("--root", action="append", help="engagement root to scan (repeatable)")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    roots = [Path(r) for r in args.root] if args.root else ROOTS
    due = scan(today, roots)

    if args.hook:
        if due:
            lines = ["Outcome hypotheses are due. Nothing else will raise these — the check "
                     "date was written weeks ago and only this hook carries it forward:"]
            for d in due:
                lines.append(f"- {d['engagement']} (due {d['check_on']}, "
                             f"{d['days_overdue']}d overdue) — {d['metric']}")
            lines.append("Close each with `ledger-emit.py <engagement> --agent human "
                         "--type outcome_check --payload-json '{\"result\":\"confirmed|"
                         "not_confirmed|unknown\", ...}'`.")
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}},
                ensure_ascii=False))
        return 0

    if args.json:
        print(json.dumps({"today": today.isoformat(), "due": due}, ensure_ascii=False, indent=2))
        return 1 if due else 0

    print(f"Outcome checks due as of {today.isoformat()}")
    if not due:
        print("  none due.")
        return 0
    for d in due:
        print(f"  {d['days_overdue']:>4}d overdue  {d['engagement']}")
        print(f"                 due {d['check_on']} — {d['metric']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
