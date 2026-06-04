#!/usr/bin/env python3
"""SkillOpt readiness checker — tells you (in-session) when to run the loop.

Counts LIVE same-class signals across BOTH input channels and reports whether the
>=3-same-class trigger for a system-optimization (SkillOpt) cycle is met:

  Channel A — explicit SIGNAL entries in skill-evolution-log.md (managers / system
              sessions append these). Clustered by (domain, class).
  Channel B — per-engagement reflections (engagement-reflections.md), written by the
              manager at M/L acceptance. Previously visible ONLY to a never-run manual
              "reflection sweep"; this checker now harvests them so the slow-burn
              patterns they encode can trip the same gate. Clustered by
              (domain, target, class) per protocol §Trigger Layer-3 — reflections name
              a specific target, so a finer key avoids firing on 3 unrelated gaps that
              merely share a class.

Channel B counts ONLY *orphan* reflections — those with NO twin SIGNAL in the log for
the same (engagement, class). The log is the authoritative channel: once an issue is
promoted there it carries the resolved-tracking, and double-counting its reflection
origin would inflate the gate (reflections are write-once and are never retro-marked
`resolved:`). So B surfaces exactly the reflections that fell through to no log signal —
which was the actual bug this harvest fixes.

"Live" excludes (both channels): `dryrun: true`, `resolved:`, and — for B — any reflection
with a log twin. A bucket only counts toward readiness if >=1 of its signals is
skill/agent-targeted (the loop edits skills/agents; pure script-targeted signals are
direct-fix territory, listed but not loop fuel).

Modes:
  (default)  human report + exit 1 if a cycle is due, else 0.
  --hook     print a single surface-to-user reminder ONLY when due (silent
             otherwise); always exit 0 (safe to wire into a SessionStart hook).
  --json     machine-readable.

Log path: --log PATH, else first match of ~/.claude/projects/*/memory/skill-evolution-log.md
Reflection roots: --reflection-root PATH (repeatable) / env SKILLOPT_REFLECTION_ROOTS
  (os.pathsep-separated), else DEFAULT_REFLECTION_ROOTS. Missing roots are skipped, so
  this is safe on any machine.
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
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

THRESHOLD = 3
REFLECTION_WINDOW_DAYS = 90  # Channel-B recency window (protocol §Trigger: "last 30-60 days")
# Where engagements (and their engagement-reflections.md) live. Overridable via
# --reflection-root / env SKILLOPT_REFLECTION_ROOTS. Missing roots are skipped, so a
# machine without these dirs (e.g. the public mirror) just sees zero reflections.
DEFAULT_REFLECTION_ROOTS = []
REFLECTION_FILE = "engagement-reflections.md"

SIGNAL_RE = re.compile(r"^###\s+SIGNAL\s*\|", re.IGNORECASE)
HEADER_RE = re.compile(r"^#{2,}\s+")  # any ## / ### header ends a signal block
DOMAIN_RE = re.compile(r"domain:\s*([A-Za-z]+)", re.IGNORECASE)
DOMAIN_FM_RE = re.compile(r"^domain:\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
ENG_RE = re.compile(r"engagement:\s*([A-Za-z0-9._-]+)", re.IGNORECASE)
CLASS_RE = re.compile(r"^Failure class:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TAXON_RE = re.compile(r"\b(rule_missing|rule_wrong|rule_ignored)\b", re.IGNORECASE)
TRACED_RE = re.compile(r"^Traced to:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
DRYRUN_RE = re.compile(r"^dryrun:\s*true\b", re.IGNORECASE | re.MULTILINE)
RESOLVED_RE = re.compile(r"^resolved:", re.IGNORECASE | re.MULTILINE)
DATE_SUFFIX_RE = re.compile(r"-?\d{4}-\d{2}-\d{2}$")

# Channel B (reflection) parsing. Header separators may be em-dash (canonical) or a
# spaced hyphen; the mandatory surrounding whitespace keeps in-name hyphens
# (e.g. "some-hyphenated-engagement-name") from being read as separators.
REFL_HEADER_RE = re.compile(
    r"^##\s+Reflection\s+[—-]\s+(?P<eng>.+?)\s+[—-]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+[—-]\s+verdict:",
    re.IGNORECASE,
)
REFL_TARGET_RE = re.compile(r"^\s*-\s*target:\s*(?P<target>.+?)\s*$", re.IGNORECASE)
REFL_CLASS_RE = re.compile(r"^\s*class:\s*(?P<cls>.+?)\s*$", re.IGNORECASE)
REFL_RESOLVED_RE = re.compile(r"^\s*resolved:", re.IGNORECASE)
REFL_DRYRUN_RE = re.compile(r"^\s*dryrun:\s*true\b", re.IGNORECASE)
TARGET_NAME_RE = re.compile(r"(?:skills?|agents?)\s*[:/]\s*([A-Za-z0-9_][A-Za-z0-9_./-]*)")


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
    """Stable problem-identity key for clustering — tolerant of BOTH authored
    conventions for the `Failure class:` line:

      "intake-size-misclassification (rule_wrong)"  -> "intake-size-misclassification"
      "rule_ignored (mandatory consilium skipped...)" -> "rule_ignored"
      "rule_ignored"                                 -> "rule_ignored"
      "token-drift"                                  -> "token-drift"

    Convention A leads with a descriptive slug and trails a (rule_token); the
    slug is the key. Convention B leads with the taxonomy token and trails FREE
    PROSE — prose is not a stable cluster key, so we key on the token instead.
    Without this, a token-leading signal keys on its whole verbose line and never
    clusters with a same-gap signal worded differently."""
    s = failure_class.strip()
    # Convention A: strip a trailing "(rule_token[ / extra prose])" -> descriptive slug
    # remains. The `[^)]*` tolerates a parenthetical carrying the token PLUS extra text,
    # e.g. "(rule_wrong / internal-contradiction)" -> still keyed by the slug, so two
    # slug-identical signals worded with/without the extra cluster together.
    a = re.sub(r"\s*\(rule_\w+\b[^)]*\)\s*$", "", s, flags=re.IGNORECASE).strip()
    if a.lower() != s.lower():
        return a.lower()
    # Convention B: text leads with a taxonomy token (optionally + a prose tail)
    # -> key on the stable token, dropping the variable prose.
    m = re.match(r"^(rule_missing|rule_wrong|rule_ignored)\b", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    # Otherwise the whole class string is its own identity (e.g. "token-drift").
    return s.lower()


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
        eng = ENG_RE.search(header)
        cls = CLASS_RE.search(body)
        # Taxonomy comes ONLY from the declared `Failure class:` line, never arbitrary
        # prose: a note/evidence line that merely *mentions* rule_missing/wrong/ignored
        # (e.g. cross-referencing another signal) must NOT mint a phantom taxonomy that
        # then twin-excludes a real same-engagement reflection from Channel B.
        tax = TAXON_RE.search(cls.group(1)) if cls else None
        traced = TRACED_RE.search(body)
        traced_s = traced.group(1).strip() if traced else ""
        out.append({
            "domain": dom.group(1).lower() if dom else "?",
            "engagement": eng.group(1).strip() if eng else "",
            "failure_class": cls.group(1).strip() if cls else "?",
            "class_key": class_key(cls.group(1)) if cls else "?",
            "taxonomy": tax.group(1).lower() if tax else None,
            "traced": traced_s,
            "target": classify_target(traced_s),
            "dryrun": bool(DRYRUN_RE.search(body)),
            "resolved": bool(RESOLVED_RE.search(body)),
            "source": "log",
        })
    return out


def resolve_domain(reflection_path: Path) -> str:
    """Reflections carry no domain; derive it from the engagement's criteria.md
    frontmatter (sibling first, then parent — covers both `<eng>/` and
    `<eng>/primary/` layouts)."""
    d = reflection_path.parent
    for cand in (d / "criteria.md", d.parent / "criteria.md"):
        try:
            if cand.exists():
                m = DOMAIN_FM_RE.search(cand.read_text(encoding="utf-8", errors="replace"))
                if m:
                    return m.group(1).lower()
        except Exception:
            continue
    return "?"


def parse_reflection_file(text: str) -> list:
    """Parse one engagement-reflections.md into reflection records. Each `- target:`
    bullet is one record; class/resolved/dryrun are read from its indented lines;
    engagement+date come from the enclosing `## Reflection — …` header."""
    records = []
    cur_eng, cur_date = None, None
    cur = None

    def flush():
        nonlocal cur
        if cur is not None:
            records.append(cur)
            cur = None

    for ln in text.splitlines():
        h = REFL_HEADER_RE.match(ln)
        if h:
            flush()
            cur_eng, cur_date = h.group("eng").strip(), h.group("date").strip()
            continue
        t = REFL_TARGET_RE.match(ln)
        if t:
            flush()
            cur = {
                "engagement": cur_eng,
                "date": cur_date,
                "target_raw": t.group("target").strip(),
                "class_raw": None,
                "resolved": False,
                "dryrun": False,
            }
            continue
        if HEADER_RE.match(ln):  # any other header ends the current record
            flush()
            continue
        if cur is not None:
            c = REFL_CLASS_RE.match(ln)
            if c and cur["class_raw"] is None:
                cur["class_raw"] = c.group("cls").strip()
            elif REFL_RESOLVED_RE.match(ln):
                cur["resolved"] = True
            elif REFL_DRYRUN_RE.match(ln):
                cur["dryrun"] = True
    flush()
    return records


def reflection_to_signal(rec: dict, domain: str) -> dict:
    cls_raw = rec.get("class_raw") or "?"
    target_raw = rec.get("target_raw") or ""
    tax = TAXON_RE.search(cls_raw)
    return {
        "domain": domain,
        "failure_class": cls_raw,
        "class_key": class_key(cls_raw) if cls_raw != "?" else "?",
        "taxonomy": tax.group(1).lower() if tax else None,
        "traced": target_raw,
        "target": classify_target(target_raw),
        "target_names": extract_target_names(target_raw),
        "primary_target": primary_target(target_raw),
        "dryrun": bool(rec.get("dryrun")),
        "resolved": bool(rec.get("resolved")),
        "source": "reflection",
        "engagement": rec.get("engagement"),
        "date": rec.get("date"),
    }


def within_window(rec_date: Optional[str], window_days: int) -> bool:
    if not window_days or window_days <= 0:
        return True
    if not rec_date:
        return True
    try:
        d = datetime.strptime(rec_date, "%Y-%m-%d").date()
    except Exception:
        return True  # unparseable -> keep (never silently drop a real reflection)
    return (date.today() - d).days <= window_days


def default_reflection_roots() -> list:
    env = os.environ.get("SKILLOPT_REFLECTION_ROOTS")
    if env:
        return [p for p in env.split(os.pathsep) if p.strip()]
    return list(DEFAULT_REFLECTION_ROOTS)


def scan_reflections(roots: list, window_days: int) -> list:
    """Harvest Channel B: every engagement-reflections.md under the given roots
    (live + archived, with/without a primary/ subdir), normalized to signal records."""
    patterns = [
        f"*/engagement/{REFLECTION_FILE}",
        f"*/engagement-archived/*/{REFLECTION_FILE}",
        f"*/engagement-archived/*/primary/{REFLECTION_FILE}",
    ]
    out, seen = [], set()
    for root in roots:
        rp = Path(root)
        if not rp.exists():
            continue
        for pat in patterns:
            for f in rp.glob(pat):
                rf = f.resolve()
                if rf in seen:
                    continue
                seen.add(rf)
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                domain = resolve_domain(f)
                for rec in parse_reflection_file(text):
                    if rec.get("class_raw") is None:  # not a real reflection block
                        continue
                    if not within_window(rec.get("date"), window_days):
                        continue
                    sig = reflection_to_signal(rec, domain)
                    sig["source_file"] = str(f)
                    out.append(sig)
    return out


def analyze(signals):
    """Channel A: cluster log signals by (domain, class_key)."""
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


def analyze_reflections(signals, log_twin_keys):
    """Channel B: keep only orphan reflections (no log twin by (norm-engagement,
    class_key)), then cluster by (domain, primary_target, class_key)."""
    def _has_twin(s):
        eng = norm_eng(s.get("engagement"))
        return (eng, s.get("taxonomy")) in log_twin_keys or (eng, s["class_key"]) in log_twin_keys

    live = [
        s for s in signals
        if not s["dryrun"] and not s["resolved"] and not _has_twin(s)
    ]
    buckets = defaultdict(list)
    for s in live:
        buckets[(s["domain"], s["primary_target"], s["class_key"])].append(s)
    due = []
    for (dom, tgt, ck), sigs in buckets.items():
        loop_actionable = any(s["target"] == "skill_agent" for s in sigs)
        if len(sigs) >= THRESHOLD and loop_actionable:
            due.append((dom, tgt, ck, len(sigs)))
    due.sort(key=lambda x: -x[3])
    return live, buckets, due


def _refl_bucket_detail(buckets) -> dict:
    out = {}
    for (d, tgt, c), v in buckets.items():
        engs = sorted({s.get("engagement") for s in v if s.get("engagement")})
        out[f"{d}/{tgt}/{c}"] = {
            "count": len(v),
            "loop_actionable": any(s["target"] == "skill_agent" for s in v),
            "engagements": engs,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SkillOpt readiness checker")
    ap.add_argument("--log", help="path to skill-evolution-log.md")
    ap.add_argument("--hook", action="store_true",
                    help="silent unless a cycle is due; always exit 0 (SessionStart hook mode)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reflection-root", action="append", default=None,
                    help="root dir to scan for engagement-reflections.md (repeatable)")
    ap.add_argument("--reflection-window-days", type=int, default=REFLECTION_WINDOW_DAYS,
                    help=f"Channel-B recency window in days (default {REFLECTION_WINDOW_DAYS}; 0 = no limit)")
    ap.add_argument("--no-reflections", action="store_true",
                    help="disable Channel B (log signals only)")
    args = ap.parse_args()

    log = find_log(args.log)
    if log is None:
        if not args.hook:
            print("skill-evolution-log.md not found (pass --log PATH)", file=sys.stderr)
        return 0
    signals = parse_signals(log.read_text(encoding="utf-8"))
    live, buckets, due = analyze(signals)

    # Twin set: ANY log signal (live or resolved) claims its (engagement, taxonomy) for
    # the authoritative channel, so its reflection origin is not double-counted in B.
    # Cross-channel issue identity = (engagement, rule_* taxonomy): the log states the
    # class as a descriptive slug carrying the token (e.g. "intake-size-misclassification
    # (rule_wrong)") while reflections state the bare token ("class: rule_wrong"), so a
    # class_key match alone misses them — key on the embedded taxonomy, keep class_key
    # as a fallback for non-rule classes.
    log_twin_keys = set()
    for s in signals:
        eng = norm_eng(s.get("engagement"))
        if not eng:
            continue
        if s.get("taxonomy"):
            log_twin_keys.add((eng, s["taxonomy"]))
        log_twin_keys.add((eng, s["class_key"]))
    roots = args.reflection_root or default_reflection_roots()
    refl_signals = [] if args.no_reflections else scan_reflections(roots, args.reflection_window_days)
    refl_live, refl_buckets, refl_due = analyze_reflections(refl_signals, log_twin_keys)
    ready = bool(due) or bool(refl_due)

    if args.hook:
        # SessionStart hook mode: emit the additionalContext envelope ONLY when a
        # cycle is due; print nothing otherwise. Always exit 0 (never block the
        # session start).
        if ready:
            lines = ["A system-optimization (SkillOpt) cycle is DUE — the >=3-same-class "
                     "trigger is met. Surface this to the user as a reminder:"]
            for dom, ck, n in due:
                lines.append(f"- {dom}/{ck}: {n} live log signals -> run `прогнать skill-evolution {dom}`")
            for dom, tgt, ck, n in refl_due:
                lines.append(f"- {dom}/{tgt}/{ck}: {n} live reflections -> run `прогнать skill-evolution {dom}`")
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
            "reflection_window_days": args.reflection_window_days,
            "reflection_count": len(refl_live),
            "reflection_buckets": _refl_bucket_detail(refl_buckets),
            "reflection_due": [
                {"domain": d, "target": t, "class": c, "count": n} for d, t, c, n in refl_due
            ],
            "ready": ready,
        }, ensure_ascii=False, indent=2))
        return 1 if ready else 0

    print(f"SkillOpt readiness — {log}")
    print(f"  live log signals (excl. dryrun/resolved): {len(live)}  | threshold: >={THRESHOLD} same-class")
    if not buckets:
        print("  Channel A (log signals): none accumulating.")
    else:
        print("  Channel A — log buckets (domain/class -> count):")
        for (d, c), v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            tgts = sorted(set(s["target"] for s in v))
            actionable = len(v) >= THRESHOLD and any(s["target"] == "skill_agent" for s in v)
            flag = "  <<< DUE" if actionable else ""
            note = "" if any(t == "skill_agent" for t in tgts) else "  [script/other -> direct-fix, not loop fuel]"
            print(f"    {d}/{c}: {len(v)}  ({','.join(tgts)}){flag}{note}")

    print(f"  Channel B — orphan reflections (window {args.reflection_window_days}d, "
          f"{len(refl_live)} live, no log twin):")
    if not refl_buckets:
        print("    none accumulating.")
    else:
        for (d, tgt, c), v in sorted(refl_buckets.items(), key=lambda kv: -len(kv[1])):
            actionable = len(v) >= THRESHOLD and any(s["target"] == "skill_agent" for s in v)
            flag = "  <<< DUE" if actionable else ""
            engs = sorted({s.get("engagement") for s in v if s.get("engagement")})
            print(f"    {d}/{tgt}/{c}: {len(v)}  [{', '.join(engs)}]{flag}")
    print()

    if ready:
        print("VERDICT: a SkillOpt cycle is DUE.")
        for d, c, n in due:
            print(f"  -> прогнать skill-evolution {d}   (log: {c}, {n} signals)")
        for d, tgt, c, n in refl_due:
            print(f"  -> прогнать skill-evolution {d}   (reflections: {tgt}/{c}, {n})")
        return 1
    print("VERDICT: not yet — no (domain,class) bucket has >=3 loop-actionable live signals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
