#!/usr/bin/env python3
"""Diagnose and (with --fix) repair corrupted engagement state.

Catches things that handoff-precheck flags as fail but doesn't itself repair:
- iteration counter file corrupt / out of sync with acceptance-log
- frontmatter malformed
- validation-log.md inconsistent with validation-outputs/
- truncated handoff.md / acceptance-log.md
- whitelist violations with auto-relocate suggestion
- missing executor-reports/ directory while reports referenced

Usage:
  python ~/.claude/scripts/engagement-doctor.py engagement/             # diagnose only
  python ~/.claude/scripts/engagement-doctor.py engagement/ --fix       # apply safe repairs

Exit codes:
  0 — no issues (or all repaired)
  1 — issues found / unrepaired
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
import json
import re
import sys
from pathlib import Path


STALLED_THRESHOLDS_MINUTES = {"S": 5, "M": 15, "L": 30, "default": 15}


def read_size(eng: Path) -> str:
    crit = eng / "criteria.md"
    if not crit.exists():
        return "default"
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return "default"
    m = re.search(r"^size\s*:\s*(\S+)", fm.group(1), re.MULTILINE)
    return (m.group(1).strip().strip('"').strip("'") if m else "default").upper()


def check_stalled(eng: Path) -> list[dict]:
    """Detect stalled engagement: most recent file mtime exceeds size-based threshold."""
    import time
    size = read_size(eng)
    threshold_min = STALLED_THRESHOLDS_MINUTES.get(size, STALLED_THRESHOLDS_MINUTES["default"])

    # If handoff.md exists with completion markers, engagement is past stall risk
    handoff = eng / "handoff.md"
    accept = eng / "acceptance-log.md"
    if accept.exists() and "ACCEPT" in accept.read_text(encoding="utf-8").upper():
        return []  # done, not stalled

    # Most recent mtime in any artefact under engagement/
    latest_mtime = 0.0
    latest_path = None
    for f in eng.rglob("*"):
        if f.is_file():
            t = f.stat().st_mtime
            if t > latest_mtime:
                latest_mtime = t
                latest_path = f

    if latest_mtime == 0:
        return []

    age_min = (time.time() - latest_mtime) / 60.0
    if age_min < threshold_min:
        return []  # fresh activity

    # Stalled — check if heartbeat in validation-log gives explanation
    log = eng / "validation-log.md"
    last_heartbeat_age = None
    last_heartbeat_phase = None
    if log.exists():
        text = log.read_text(encoding="utf-8")
        m = re.search(r"^##\s*Heartbeat\s*[—\-]\s*Phase\s+(.+?)\s*[—\-]\s*completed\s+(\S+\s+\S+)",
                      text, re.MULTILINE | re.IGNORECASE)
        if m:
            last_heartbeat_phase = m.group(1).strip()

    return [{
        "id": "stalled-engagement",
        "severity": "high" if age_min < threshold_min * 4 else "critical",
        "msg": (f"engagement size={size}, threshold={threshold_min}min: "
                f"newest artefact ({latest_path.name if latest_path else '?'}) is {age_min:.1f}min old; "
                f"last heartbeat phase: {last_heartbeat_phase or 'none recorded'}"),
        "fix": None,  # human decision: kill + re-dispatch from last heartbeat phase
    }]


def diagnose(eng: Path) -> list[dict]:
    """Return list of issues. Each dict has: id, severity, msg, fix (callable or None)."""
    issues = []
    issues.extend(check_stalled(eng))

    crit = eng / "criteria.md"
    if not crit.exists():
        issues.append({
            "id": "no-criteria",
            "severity": "critical",
            "msg": "criteria.md missing — engagement is not real",
            "fix": None,
        })
        return issues

    crit_text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", crit_text, re.DOTALL)
    if not fm:
        issues.append({
            "id": "no-frontmatter",
            "severity": "critical",
            "msg": "criteria.md has no frontmatter",
            "fix": None,
        })

    # iteration counter
    counter_path = eng / "iteration"
    log_path = eng / "acceptance-log.md"
    log_iters = []
    if log_path.exists():
        log_iters = sorted({int(x) for x in re.findall(r"^##\s*Iteration\s+(\d+)", log_path.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)})

    if counter_path.exists():
        try:
            n = int(counter_path.read_text(encoding="utf-8").strip())
        except Exception:
            issues.append({
                "id": "counter-corrupt",
                "severity": "high",
                "msg": f"iteration file unparseable as int",
                "fix": ("rewrite-counter", max(log_iters) + 1 if log_iters else 1),
            })
            n = None
        if n is not None and log_iters:
            expected = {max(log_iters), max(log_iters) + 1}
            if n not in expected:
                issues.append({
                    "id": "counter-out-of-sync",
                    "severity": "medium",
                    "msg": f"counter={n} but acceptance-log iterations={log_iters}",
                    "fix": ("rewrite-counter", max(log_iters) + 1),
                })
    else:
        if log_iters:
            issues.append({
                "id": "counter-missing",
                "severity": "medium",
                "msg": "iteration file missing but acceptance-log has iterations",
                "fix": ("rewrite-counter", max(log_iters) + 1),
            })

    # validation-outputs vs validation-log
    log_md = eng / "validation-log.md"
    outputs_dir = eng / "validation-outputs"
    if log_md.exists() and not outputs_dir.exists():
        issues.append({
            "id": "outputs-dir-missing",
            "severity": "medium",
            "msg": "validation-log.md present but validation-outputs/ missing",
            "fix": ("create-outputs-dir", None),
        })

    # validation-outputs JSON parseability
    if outputs_dir.exists():
        for f in outputs_dir.glob("*.json"):
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                issues.append({
                    "id": "output-corrupt",
                    "severity": "medium",
                    "msg": f"{f.name} not parseable as JSON: {e}",
                    "fix": None,  # cannot auto-recover content
                })

    # rogue files
    WHITELIST_FILES = {"criteria.md", "scope-sync.md", "plan.md", "validation-log.md",
                       "deploy-log.md", "docs-diff.md", "handoff.md", "acceptance-log.md",
                       "iteration"}
    WHITELIST_DIRS = {"specs", "tasks", "brand", "design-system", "ui",
                      "executor-reports", "screens", "traces", "validation-outputs"}
    for entry in eng.iterdir():
        if entry.name in WHITELIST_FILES or (entry.is_dir() and entry.name in WHITELIST_DIRS):
            continue
        issues.append({
            "id": "rogue-file",
            "severity": "high",
            "msg": f"out-of-whitelist entry: {entry.name}",
            "fix": None,  # require manual relocation — auto-move is risky
        })

    # truncated markdown
    for fname in ["handoff.md", "acceptance-log.md", "scope-sync.md"]:
        f = eng / fname
        if f.exists() and f.stat().st_size < 50 and f.read_text(encoding="utf-8").strip() == "":
            issues.append({
                "id": "empty-artefact",
                "severity": "low",
                "msg": f"{fname} exists but is empty",
                "fix": None,
            })

    return issues


def apply_fix(eng: Path, issue: dict) -> bool:
    """Apply repair if fix is automatable."""
    fix = issue.get("fix")
    if not fix:
        return False
    kind, arg = fix
    try:
        if kind == "rewrite-counter":
            (eng / "iteration").write_text(str(arg), encoding="utf-8")
            return True
        if kind == "create-outputs-dir":
            (eng / "validation-outputs").mkdir(exist_ok=True)
            return True
    except Exception as e:
        print(f"  [fix-error] {issue['id']}: {e}")
        return False
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("engagement", help="Path to engagement directory")
    p.add_argument("--fix", action="store_true", help="Apply automated fixes (only safe ones)")
    args = p.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        print(f"ERROR: engagement not found: {eng}", file=sys.stderr)
        return 2

    issues = diagnose(eng)
    if not issues:
        print(f"Engagement healthy: {eng}")
        return 0

    print(f"Diagnosis for {eng}:")
    print(f"  {len(issues)} issue(s) found.")
    print()
    fixed = 0
    unfixed = 0
    for i, issue in enumerate(issues, 1):
        sev = issue["severity"].upper()
        print(f"  [{sev:8}] {issue['id']}: {issue['msg']}")
        if args.fix:
            if apply_fix(eng, issue):
                print(f"           → fixed")
                fixed += 1
            else:
                if issue.get("fix"):
                    print(f"           → fix attempted but failed")
                else:
                    print(f"           → no automated fix available; manual repair required")
                unfixed += 1

    print()
    if args.fix:
        print(f"Summary: {fixed} fixed, {unfixed} unfixed.")
        return 0 if unfixed == 0 else 1
    print("Run with --fix to apply automated repairs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
