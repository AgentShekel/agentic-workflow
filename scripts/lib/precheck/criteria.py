"""Engagement structure checks: directory shape, criteria.md, tier/size, tasks.

Five checks live here:
  - check_whitelist: top-level entries must be in WHITELIST.
  - check_criteria_frontmatter: criteria.md frontmatter has required fields.
  - check_preflight: delegate to preflight.py (tool reachability per criteria).
  - check_size_drift: delegate to size-detect.py runtime; catch lead who
    forgot to promote tier.
  - check_tasks_decomposition: tasks/ presence rules per tier (S/M/L).

All check signatures: `(eng: Path, ...) -> dict` returning
`{name, status, detail, [fix]}`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import WHITELIST, CRITERIA_FRONTMATTER_REQUIRED, run


def check_whitelist(eng: Path) -> dict:
    if not eng.exists() or not eng.is_dir():
        return {"name": "whitelist", "status": "fail", "detail": f"not a directory: {eng}"}
    rogue = []
    for entry in eng.iterdir():
        name = entry.name
        if name in WHITELIST:
            continue
        if entry.is_dir() and name in WHITELIST:
            continue
        rogue.append(name)
    if rogue:
        return {
            "name": "whitelist",
            "status": "fail",
            "detail": f"out-of-whitelist entries: {rogue}",
            "fix": "Move content into validation-log.md / handoff.md / executor-reports/, then delete rogue files.",
        }
    return {"name": "whitelist", "status": "pass", "detail": f"{len(list(eng.iterdir()))} entries, all whitelisted"}


def check_criteria_frontmatter(eng: Path) -> dict:
    crit = eng / "criteria.md"
    if not crit.exists():
        return {"name": "criteria-frontmatter", "status": "fail", "detail": "criteria.md missing"}
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return {"name": "criteria-frontmatter", "status": "fail", "detail": "criteria.md has no frontmatter"}
    body = fm.group(1)
    missing = [k for k in CRITERIA_FRONTMATTER_REQUIRED if not re.search(rf"^{k}\s*:", body, re.MULTILINE)]
    if missing:
        return {"name": "criteria-frontmatter", "status": "fail", "detail": f"missing fields: {missing}"}

    return {"name": "criteria-frontmatter", "status": "pass", "detail": "all required fields present"}


def check_preflight(eng: Path, scripts_dir: Path) -> dict:
    crit = eng / "criteria.md"
    if not crit.exists():
        return {"name": "preflight", "status": "fail", "detail": "criteria.md missing"}
    code, out = run([sys.executable, str(scripts_dir / "preflight.py"), "--criteria", str(crit), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "preflight", "status": "pass", "detail": "all tools reachable"}
        return {"name": "preflight", "status": "fail", "detail": f"failed tools: {[t['name'] for t in data.get('tools', []) if t.get('status') != 'pass']}"}
    except json.JSONDecodeError:
        return {"name": "preflight", "status": "fail", "detail": f"preflight script error (exit {code}): {out[:200]}"}


def check_size_drift(eng: Path, scripts_dir: Path) -> dict:
    """Run size-detect.py runtime to catch lead who forgot to promote.

    If observed > current, the engagement is being submitted under-tier:
    handoff schema relaxations don't match the actual scope. REJECT with
    explicit fix instruction (re-run with --auto-promote).
    """
    detector = scripts_dir / "size-detect.py"
    if not detector.exists():
        return {"name": "size-drift", "status": "skip", "detail": "size-detect.py not installed"}
    code, out = run([sys.executable, str(detector), str(eng), "--mode", "runtime", "--json"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"name": "size-drift", "status": "skip", "detail": f"size-detect output unparseable: {out[:160]}"}

    if data.get("status") != "ok":
        return {"name": "size-drift", "status": "skip", "detail": data.get("reason", "size-detect error")}

    if data.get("promote"):
        return {
            "name": "size-drift",
            "status": "fail",
            "detail": f"size drift: criteria.md size={data['current']} but observations indicate {data['observed']}; triggers: {data.get('triggered', [])[:3]}",
            "fix": "Run `python ~/.claude/scripts/size-detect.py engagement/ --mode runtime --auto-promote` to update criteria.md + scope-sync.md, then re-submit. Promotion is one-way (S->M, M->L); rigour ratchets up to match real scope.",
        }
    return {"name": "size-drift", "status": "pass", "detail": f"size={data['current']} matches observations"}


def check_tasks_decomposition(eng: Path, size: str, ux_heavy: str) -> dict:
    """Tasks/ directory presence rule by tier.

    - S: skip (N/A by protocol).
    - M: warn if absent AND multi-specialist (>=2 executor-reports).
    - L: fail if absent or empty; INDEX.md required.
    """
    if size == "S":
        return {"name": "tasks-decomposition", "status": "skip", "detail": "size=S, tasks/ N/A"}

    tasks_dir = eng / "tasks"
    has_tasks = tasks_dir.exists() and any(
        f.is_file() and f.suffix == ".md" and f.name != "INDEX.md"
        for f in tasks_dir.iterdir()
    ) if tasks_dir.exists() else False

    reports_dir = eng / "executor-reports"
    specialist_count = len(list(reports_dir.glob("*.md"))) if reports_dir.exists() else 0

    if size == "L":
        if not has_tasks:
            return {
                "name": "tasks-decomposition",
                "status": "fail",
                "detail": "size=L requires tasks/*.md atomic decomposition (none found)",
                "fix": "Lead must run domain task-decomposition skill (marketing-task-decomposition / design-task-decomposition / task-decomposition) at Phase 2.5 to produce engagement/tasks/{NN}-{slug}.md before dispatch.",
            }
        index = tasks_dir / "INDEX.md"
        if not index.exists():
            return {
                "name": "tasks-decomposition",
                "status": "fail",
                "detail": "size=L requires tasks/INDEX.md (dependency graph + wave grouping); not found",
                "fix": "Author tasks/INDEX.md listing waves, each task one line with owner + crit_refs (per domain task-decomposition skill).",
            }
        return {"name": "tasks-decomposition", "status": "pass", "detail": "L-tier: tasks/ has files + INDEX.md"}

    # size == M
    if not has_tasks and specialist_count >= 2:
        return {
            "name": "tasks-decomposition",
            "status": "warn",
            "detail": f"size=M with {specialist_count} specialists has no tasks/*.md (recommended for iter-2 retargeting)",
            "fix": "Run domain task-decomposition skill at Phase 2.5. Atomic tasks let lead re-dispatch only the broken unit on REJECT instead of the whole phase.",
        }
    return {"name": "tasks-decomposition", "status": "pass", "detail": f"M-tier: {'tasks present' if has_tasks else 'tasks not required (single specialist)'}"}
