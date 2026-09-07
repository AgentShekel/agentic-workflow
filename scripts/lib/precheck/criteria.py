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

from .common import CRITERIA_FRONTMATTER_REQUIRED, WHITELIST, run


def _criteria_named_deliverables(eng: Path) -> set[str]:
    """Top-level engagement/ entries that criteria.md explicitly names as
    deliverables (e.g. `engagement/live-health-report.md`). The whitelist's
    intent is to block phantom-hiding sidecars, NOT to reject secretary-mandated
    outputs; criteria.md takes precedence over protocol for *what deliverables
    exist* (authority invariant: criteria > protocol for scope/deliverables).
    Returns the first path segment after each `engagement/<...>` reference."""
    crit = eng / "criteria.md"
    if not crit.exists():
        return set()
    try:
        text = crit.read_text(encoding="utf-8")
    except Exception:
        return set()
    return set(re.findall(r"engagement/([\w\-.]+)", text))


def _preflight_override(eng: Path) -> str | None:
    """A documented intake preflight override in criteria.md, of the form
    `<!-- preflight: ... status=PASS ... override ... -->`. This is the
    human/lead intake decision (criteria > protocol) that preflight.py's host
    probe is a false positive — e.g. pg/redis run in compose containers reached
    over the compose network, with no host pg_isready/redis-cli. Returns the
    (whitespace-collapsed, truncated) marker text, or None."""
    crit = eng / "criteria.md"
    if not crit.exists():
        return None
    try:
        text = crit.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r"<!--\s*preflight:.*?-->", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    block = m.group(0)
    if re.search(r"status\s*=\s*PASS", block, re.IGNORECASE) and re.search(r"overrid", block, re.IGNORECASE):
        return " ".join(block.split())[:200]
    return None


def check_whitelist(eng: Path) -> dict:
    if not eng.exists() or not eng.is_dir():
        return {"name": "whitelist", "status": "fail", "detail": f"not a directory: {eng}"}
    allowed = WHITELIST | _criteria_named_deliverables(eng)
    rogue = [entry.name for entry in eng.iterdir() if entry.name not in allowed]
    if rogue:
        return {
            "name": "whitelist",
            "status": "fail",
            "detail": f"out-of-whitelist entries: {rogue}",
            "fix": "Move content into validation-log.md / handoff.md / executor-reports/, then delete rogue files. (Files that criteria.md names as deliverables via an `engagement/<file>` path are auto-allowed.)",
        }
    return {"name": "whitelist", "status": "pass", "detail": f"{len(list(eng.iterdir()))} entries, all whitelisted or criteria-named"}


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
        failed = [t["name"] for t in data.get("tools", []) if t.get("status") != "pass"]
        if _preflight_override(eng):
            return {
                "name": "preflight",
                "status": "pass",
                "detail": f"preflight.py flagged {failed}, but criteria.md documents a PASS override "
                          f"(intake-adjudicated false positive - e.g. containerized service reached via the compose network, not host CLI)",
            }
        return {"name": "preflight", "status": "fail", "detail": f"failed tools: {failed}"}
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


# `- [ ] q-1: text — needed to: ... — status: open`
_OQ_ROW = re.compile(
    r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?(q-\d+)\s*:(.*?)$",
    re.MULTILINE)
_OQ_STATUS = re.compile(r"status\s*:\s*(open|answered|waived)\b", re.IGNORECASE)


def check_open_questions(eng: Path) -> dict:
    """Every question intake could not resolve is written down and dispositioned.

    Intake asks one clarifying question and locks criteria. Whatever stayed
    ambiguous after that used to live nowhere: not in criteria.md, not in the
    handoff, not in the acceptance record. It resurfaced as a specialist guessing,
    and the guess only became visible when the manager rejected the result.

    The rule is borrowed from a tracker-draft tool that had the same problem: an
    open question blocks readiness until it is either answered or EXPLICITLY
    waived, and a waived question rides along as an acknowledged warning rather
    than disappearing. Waiving is a decision someone made and left a trace of.
    Silence is not.

    Warn, not fail: the section is new, every engagement written before it has
    none, and a hard gate here would be waived on day one. The blocking half
    lives at intake (agency-intake §6), where the question is still cheap.
    """
    name = "open-questions"
    crit = eng / "criteria.md"
    if not crit.exists():
        return {"name": name, "status": "skip", "detail": "criteria.md not present"}

    text = crit.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^##\s*Open questions\s*$(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not m:
        return {"name": name, "status": "skip",
                "detail": "no `## Open questions` section (pre-dates the convention)"}

    body = m.group(1)
    rows = _OQ_ROW.findall(body)
    if not rows:
        return {"name": name, "status": "pass",
                "detail": "Open questions section present and empty — nothing was left hanging"}

    undispositioned, still_open, waived = [], [], []
    for qid, rest in rows:
        st = _OQ_STATUS.search(rest)
        if not st:
            undispositioned.append(qid)
        elif st.group(1).lower() == "open":
            still_open.append(qid)
        elif st.group(1).lower() == "waived":
            waived.append(qid)

    if undispositioned:
        return {
            "name": name, "status": "warn",
            "detail": f"questions with no status at all: {undispositioned}. A question "
                      f"without a disposition is indistinguishable from one nobody read.",
            "fix": "Give each row `status: open | answered | waived`. Answered carries the "
                   "answer; waived is the user's explicit decision to proceed without one.",
        }
    if still_open:
        return {
            "name": name, "status": "warn",
            "detail": f"still open at handoff: {still_open}. Intake should have closed or "
                      f"waived these before the engagement started.",
            "fix": "Answer them, or mark `status: waived` so they travel into acceptance as "
                   "acknowledged warnings instead of quietly shaping someone's guess.",
        }
    detail = f"{len(rows)} question(s) dispositioned"
    if waived:
        detail += f"; {len(waived)} waived and carried forward as acknowledged: {waived}"
    return {"name": name, "status": "pass", "detail": detail}
