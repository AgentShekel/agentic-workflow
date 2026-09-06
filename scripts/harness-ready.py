#!/usr/bin/env python3
"""Harness-evolution readiness checker — the harness-layer twin of skillopt-ready.py.

SkillOpt (skillopt-ready.py) watches signals whose `Traced to:` names a SKILL or AGENT and
EXCLUDES script/engine-targeted ones ("direct-fix, not loop fuel"). This checker watches
exactly the layer SkillOpt drops: the orchestration/acceptance SCRIPTS + the workflow ENGINE
(scripts/*.py, scripts/lib/precheck/*.py, workflows/engagement-workflow.js). It clusters OPEN
harness signals by (script x failure-class) and reports when a >=2-same-(script,class) cluster
is live — the trigger for a harness-evolution pass (a direct-fix or, once recurrence justifies
it, a harness-director cycle).

Threshold is >=2 (not SkillOpt's >=3): harness bugs are DETERMINISTIC and reproducible, so a
2nd same-(script,class) hit is a confirmed regression class, not statistical prompt drift. A
lone high-severity harness bug is still worth a direct fix immediately — it just does not
auto-mint a cluster.

"Open" excludes: `dryrun: true`; ANY `resolved` line (incl. partials like
`resolved (SCRIPT half):` / `resolved (ENGINE root...`); and platform-limitation signals (a
working field workaround, not a fixable harness defect).

Channel A only (skill-evolution-log.md SIGNAL blocks). Reflections are skill/agent-oriented —
SkillOpt's channel; harness signals are appended to the log directly. Channel B is a
deliberate non-goal for this lean v1.

Modes: (default) human report + exit 1 if a cluster is due, else 0; --hook (silent unless due,
always exit 0 — SessionStart-safe); --json (machine-readable).
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

THRESHOLD = 2

SIGNAL_RE = re.compile(r"^###\s+SIGNAL\s*\|", re.IGNORECASE)
HEADER_RE = re.compile(r"^#{2,}\s+")  # any ## / ### header ends a signal block
ENG_RE = re.compile(r"engagement:\s*([A-Za-z0-9._-]+)", re.IGNORECASE)
CLASS_RE = re.compile(r"^Failure class:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TRACED_RE = re.compile(r"^Traced to:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
DRYRUN_RE = re.compile(r"^dryrun:\s*true\b", re.IGNORECASE | re.MULTILINE)
# Broad, because harness signals carry partial-resolved lines ("resolved (SCRIPT half):",
# "resolved (PREFLIGHT half):", "resolved (ENGINE root, ...):") — but NOT so broad that it
# swallows the SKILL loop's half-marker.
#
# `resolved (SKILL half):` means the skill half is fixed and the SCRIPT half is still open,
# so this checker must keep counting the signal. Without the lookahead the broad `^resolved`
# closed it, silently dropping the still-open script half out of the >=2 cluster — the mirror
# image of skillopt-ready closing on `resolved (SCRIPT half):`, which it likewise must not do.
RESOLVED_RE = re.compile(r"^resolved\b(?!\s*\(SKILL)", re.IGNORECASE | re.MULTILINE)
PLATFORM_RE = re.compile(r"platform-limitation|status:\s*PLATFORM-LIMITATION", re.IGNORECASE)

# Harness target extraction from a `Traced to:` line.
SCRIPT_RE = re.compile(r"(scripts/(?:lib/precheck/)?[A-Za-z0-9_./-]+\.py)", re.IGNORECASE)
JS_RE = re.compile(r"([A-Za-z0-9_./-]+\.js)", re.IGNORECASE)
ENGINE_ALIAS_RE = re.compile(r"engagement-workflow", re.IGNORECASE)
ENGINE_PATH = "workflows/engagement-workflow.js"


def class_key(failure_class: str) -> str:
    """Stable problem-identity key for clustering — mirrors skillopt-ready.class_key so the
    two checkers bucket the same way. Convention A "slug (rule_token)" -> slug; Convention B
    "rule_token (prose)" -> token; else the whole string."""
    s = failure_class.strip()
    a = re.sub(r"\s*\(rule_\w+\b[^)]*\)\s*$", "", s, flags=re.IGNORECASE).strip()
    if a.lower() != s.lower():
        return a.lower()
    m = re.match(r"^(rule_missing|rule_wrong|rule_ignored)\b", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return s.lower()


def harness_target(traced: str) -> Optional[str]:
    """The harness file a signal points at, or None if it names no script/engine. A mixed
    'skills/X + scripts/Y.py + agents/Z' trace returns scripts/Y.py (the harness half) — the
    skill/agent half is SkillOpt's; this checker owns the script/engine half."""
    t = traced or ""
    m = SCRIPT_RE.search(t)
    if m:
        return m.group(1).replace("\\", "/").lower()
    m = JS_RE.search(t)
    if m:
        return m.group(1).replace("\\", "/").lower()
    if ENGINE_ALIAS_RE.search(t):
        return ENGINE_PATH
    return None


def find_log(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return None
    matches = sorted(base.glob("*/memory/skill-evolution-log.md"))
    return matches[0] if matches else None


def parse_signals(text: str) -> list:
    blocks, cur = [], None
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
        header, body = blk[0], "\n".join(blk)
        cls = CLASS_RE.search(body)
        traced = TRACED_RE.search(body)
        traced_s = traced.group(1).strip() if traced else ""
        eng = ENG_RE.search(header)
        out.append({
            "engagement": eng.group(1).strip() if eng else "",
            "failure_class": cls.group(1).strip() if cls else "?",
            "class_key": class_key(cls.group(1)) if cls else "?",
            "traced": traced_s,
            "target": harness_target(traced_s),
            "dryrun": bool(DRYRUN_RE.search(body)),
            "resolved": bool(RESOLVED_RE.search(body)),
            "platform": bool(PLATFORM_RE.search(body)),
        })
    return out


def analyze(signals: list):
    """Cluster OPEN harness signals by (script, class_key); a bucket >= THRESHOLD is due."""
    live = [
        s for s in signals
        if s["target"] and not s["dryrun"] and not s["resolved"] and not s["platform"]
    ]
    buckets = defaultdict(list)
    for s in live:
        buckets[(s["target"], s["class_key"])].append(s)
    due = [(tgt, ck, len(v)) for (tgt, ck), v in buckets.items() if len(v) >= THRESHOLD]
    due.sort(key=lambda x: -x[2])
    return live, buckets, due


def main() -> int:
    ap = argparse.ArgumentParser(description="Harness-evolution readiness checker")
    ap.add_argument("--log", help="path to skill-evolution-log.md")
    ap.add_argument("--hook", action="store_true",
                    help="silent unless a cluster is due; always exit 0 (SessionStart hook mode)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    log = find_log(args.log)
    if log is None:
        if not args.hook:
            print("skill-evolution-log.md not found (pass --log PATH)", file=sys.stderr)
        return 0
    signals = parse_signals(log.read_text(encoding="utf-8"))
    live, buckets, due = analyze(signals)
    ready = bool(due)

    if args.hook:
        if ready:
            lines = ["A harness-evolution cluster is DUE (>=2 open same-(script,class) harness "
                     "signals). Surface this to the user as a reminder:"]
            for tgt, ck, n in due:
                lines.append(f"- {tgt} / {ck}: {n} open signals -> run `прогнать harness-evolution`")
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}},
                ensure_ascii=False))
        return 0

    if args.json:
        print(json.dumps({
            "log": str(log), "threshold": THRESHOLD, "live_count": len(live),
            "buckets": {f"{t}|{c}": len(v) for (t, c), v in buckets.items()},
            "due": [{"target": t, "class": c, "count": n} for t, c, n in due],
            "ready": ready,
        }, ensure_ascii=False, indent=2))
        return 1 if ready else 0

    print(f"Harness-evolution readiness — {log}")
    print(f"  open harness signals (excl. dryrun/resolved/platform): {len(live)}  "
          f"| threshold: >={THRESHOLD} same (script,class)")
    if not buckets:
        print("  none accumulating.")
    else:
        for (t, c), v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            flag = "  <<< DUE" if len(v) >= THRESHOLD else ""
            engs = sorted({s["engagement"] for s in v if s["engagement"]})
            print(f"    {t} / {c}: {len(v)}  [{', '.join(engs)}]{flag}")
    print()

    if ready:
        print("VERDICT: a harness-evolution cluster is DUE.")
        for t, c, n in due:
            print(f"  -> прогнать harness-evolution   ({t} / {c}, {n} signals)")
        return 1
    print("VERDICT: not yet — no (script,class) bucket has >=2 open harness signals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
