#!/usr/bin/env python3
"""LangGraph engagement-level orchestrator.

Owns the whole engagement lifecycle from intake to archive, replacing the
previously-implicit "lead dispatches, validators run, manager accepts" flow
with an explicit state machine.

Graph structure, state
schema, node placeholders, HITL scaffold, checkpointer, ledger emit, CLI
all wired. Node bodies are dry-run-safe placeholders: they emit ledger
events and advance state with the minimum updates needed for the graph
to complete, but DO NOT invoke real lead/specialist/validator/manager
agents. Real wiring lands in Waves B-F (see
engagement_lg.py docstring).

Default mode is `--dry-run` (skeleton-safe). To run a node body for real
in this state you would need to pass `--real`, which currently raises
NotImplementedError — by design, partial deployments fail loudly.

Existing engines remain authoritative for their phases:
  - validator_lg.py   — validation phase (subprocess delegate)
  - adversary_lg.py   — consilium phase (subprocess delegate)
  - handoff-precheck.py — invoked at handoff submission + manager-accept
  - engagement-archive.py — final archival

Usage:
  python engagement_lg.py engagement/                  # invoke (init or continue)
  python engagement_lg.py engagement/ --resume         # explicit resume
  python engagement_lg.py engagement/ --status         # print current state
  python engagement_lg.py engagement/ --dry-run        # default: skeleton mode
  python engagement_lg.py engagement/ --tier-override M
  python engagement_lg.py engagement/ --no-hitl        # debug: disable pauses
  python engagement_lg.py engagement/ --interrupt-on-criteria
  python engagement_lg.py engagement/ --resume-interrupt THREAD --decision PROCEED
  python engagement_lg.py engagement/ --no-checkpoint
  python engagement_lg.py engagement/ --json

Exit codes:
  0 — graph completed (ACCEPT or paused awaiting human)
  1 — graph completed with REJECT or ABORTED final verdict
  2 — invocation error / engagement directory not found / NotImplementedError in --real
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# venv bootstrap — re-exec under the dedicated venv if langgraph is absent.
# Shares .venv-adversary-lg with adversary_lg.py and validator_lg.py so all
# three LangGraph engines run on identical pinned dependencies.
# ---------------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path

_VENV = _Path(__file__).resolve().parent / ".venv-adversary-lg"


def _bootstrap() -> None:
    try:
        import langgraph  # noqa: F401
        return
    except ImportError:
        pass
    venv_py = _VENV / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = _VENV / "bin" / "python"
    here = _Path(__file__).resolve()
    already_in_venv = (
        _Path(_sys.executable).resolve() == venv_py.resolve()
        if venv_py.exists() else False
    )
    if venv_py.exists() and not already_in_venv:
        import subprocess as _sp
        _sys.exit(_sp.run([str(venv_py), str(here), *_sys.argv[1:]]).returncode)
    _sys.stderr.write(
        "engagement_lg.py needs langgraph/langchain. Create the venv:\n"
        f'  python -m venv "{_VENV}"\n'
        f'  "{(_VENV / "Scripts" / "python.exe")}" -m pip install -r '
        f'"{_Path(__file__).resolve().parent / "requirements-adversary-lg.txt"}"\n'
    )
    _sys.exit(2)


_bootstrap()

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import hashlib
import json
import operator
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, Send, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

# Make sibling lib/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lib.ledger import EventLedger  # noqa: E402
    _LEDGER_AVAILABLE = True
except Exception:
    EventLedger = None  # type: ignore
    _LEDGER_AVAILABLE = False

_RUN_LEDGER: "Optional[EventLedger]" = None


def _ledger_emit(payload_type: str, **kwargs):
    if _RUN_LEDGER is None:
        return None
    try:
        return _RUN_LEDGER.emit(payload_type, **kwargs)
    except Exception as e:
        print(f"WARN: ledger emit failed ({payload_type}): {e}", file=sys.stderr)
        return None


# ===========================================================================
# State
# ===========================================================================


class EngagementState(TypedDict, total=False):
    # Identity
    engagement: str
    engagement_id: str

    # Criteria meta (from criteria.md frontmatter)
    tier: str                    # "S" | "M" | "L"
    domain: str                  # "dev" | "design" | "marketing"
    ux_heavy: str                # "true" | "false" | "minor"

    # Lifecycle position
    phase: str                   # see PHASE_NAMES
    iter_n: int
    iter_max: int                # 1 (S), 2 (M), 3 (L)

    # Phase outputs
    intake_status: str
    plan_status: str
    dispatch_status: str
    validation_verdict: str
    consilium_verdict: str
    human_directive_decision: str
    manager_verdict: str
    archive_status: str

    # Specialist fan-out (list parsed from plan.md frontmatter;
    # consumes the list via Send fan-out; results append here).
    specialists: list[str]
    specialist_results: Annotated[list[dict], operator.add]

    # HITL
    hitl_enabled: bool
    paused_at: str
    human_directive: dict

    # Bookkeeping
    started_at: str
    last_phase_at: str
    error: str

    # Mode flags (set by main(), propagated by nodes)
    dry_run: bool                # True: placeholders skip real work
    mock: bool                   # True: real graph paths, but subprocess
                                 # wrappers return canned artefacts (no LLM
                                 # / no claude CLI / no external state).
                                 # Lets test the full graph end-to-end on
                                 # boxes that don't have claude CLI installed.
    interrupt_on_criteria: bool  # opt-in extra pause at criteria_lock


# ===========================================================================
# Constants
# ===========================================================================


PHASE_NAMES = {
    "intake":    "phase:intake",
    "plan":      "phase:plan",
    "dispatch":  "phase:dispatch",
    "validate":  "phase:validate",
    "consilium": "phase:consilium",
    "accept":    "phase:accept",
    "archive":   "phase:archive",
    "done":      "phase:done",
}

TIER_ITER_MAX = {"S": 1, "M": 2, "L": 3}
TIER_USES_CONSILIUM = {"S": False, "M": True, "L": True}
TIER_USES_HITL_DEFAULT = {"S": False, "M": True, "L": True}


# ===========================================================================
# Helpers
# ===========================================================================


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_criteria_meta(eng: Path) -> dict:
    """Frontmatter parse — mirror of lib/precheck/common.py read_criteria_meta
    (kept local to avoid hard-coupling engagement_lg.py to the precheck package
    in case someone strips lib/precheck/)."""
    crit = eng / "criteria.md"
    if not crit.exists():
        return {}
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return {}
    body = fm.group(1)
    meta = {}
    for k in ["size", "ux_heavy", "domain", "engagement"]:
        m = re.search(rf"^{k}\s*:\s*(\S+)", body, re.MULTILINE)
        if m:
            meta[k] = m.group(1).strip().strip('"').strip("'")
    return meta


def _read_iter_counter(eng: Path) -> int:
    """engagement/iteration file → int. Default 1."""
    f = eng / "iteration"
    if not f.exists():
        return 1
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except Exception:
        return 1


def _not_implemented(node_name: str, state: EngagementState) -> dict:
    """Raise NotImplementedError unless dry_run — partial pipelines fail loud."""
    if state.get("dry_run"):
        return {}
    raise NotImplementedError(
        f"engagement_lg: {node_name!r} body not implemented. "
        f"Pass --dry-run for skeleton mode, or wait for next wave to wire this node. "
        f"See engagement_lg.py docstring for design notes."
    )


# ---------------------------------------------------------------------------
# Helpers — claude CLI discovery + subprocess wrappers.
# Mirror of validator_lg.py SubprocessInvoker._find_claude_cmd pattern.
# ---------------------------------------------------------------------------


import shutil as _shutil  # noqa: E402


def _find_claude_cmd() -> Optional[str]:
    # Windows: claude.CMD wrapper truncates multiline argv at the first
    # newline (CMD line-parsing semantics), silently mangling multi-line
    # prompts. Resolve to the underlying claude.exe when the resolved
    # entry is a .CMD wrapper. Unix/macOS path unaffected.
    for c in ("claude", "claude.cmd", "claude.exe"):
        p = _shutil.which(c)
        if p:
            if Path(p).suffix.lower() == ".cmd":
                exe = Path(p).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
                if exe.exists():
                    return str(exe)
            return p
    return None


def _run_size_detect(eng: Path, scripts_dir: Path) -> dict:
    """Run size-detect.py --mode runtime --auto-promote --json.

    Returns {"status": "ok"|"skip"|"error", "promoted": bool, "old": str,
    "new": str, "triggered": [...], "raw": str}.

    --auto-promote writes new tier into criteria.md in-place when it detects
    drift; caller must re-read criteria_meta after.
    """
    import subprocess as _sp
    detector = scripts_dir / "size-detect.py"
    if not detector.exists():
        return {"status": "skip", "reason": "size-detect.py missing", "promoted": False}
    try:
        r = _sp.run(
            [sys.executable, str(detector), str(eng),
             "--mode", "runtime", "--auto-promote", "--json"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        out = (r.stdout + r.stderr).strip()
        try:
            data = json.loads(r.stdout)
        except Exception:
            return {"status": "error", "raw": out[:300], "promoted": False}
        if data.get("status") != "ok":
            return {"status": "skip", "reason": data.get("reason", "non-ok"),
                    "promoted": False, "raw": out[:300]}
        promoted = (data.get("current") != data.get("observed")
                    and data.get("observed") in {"S", "M", "L"})
        return {
            "status": "ok",
            "promoted": bool(data.get("promoted") or promoted),
            "old": data.get("current"),
            "new": data.get("observed"),
            "triggered": data.get("triggered", []),
            "raw": out[:300],
        }
    except _sp.TimeoutExpired:
        return {"status": "error", "error": "size-detect timeout", "promoted": False}
    except Exception as e:
        return {"status": "error", "error": str(e), "promoted": False}


def _invoke_lead_subprocess(domain: str, eng: Path, prompt: str,
                            timeout: int = 600, mock: bool = False) -> dict:
    """Invoke `claude -p --agent {domain}-lead <prompt>`.

    Returns {"status": "ok"|"error", "stdout": str, "stderr": str, "rc": int}.

    When mock=True, write a canned plan.md instead of subprocess. Used by
    --mock CLI flag for end-to-end testing without claude CLI.
    """
    if mock:
        return _mock_invoke_lead(domain, eng)
    import subprocess as _sp
    claude = _find_claude_cmd()
    if not claude:
        return {"status": "error", "error": "claude CLI not found in PATH"}
    agent_name = f"{domain}-lead"
    try:
        r = _sp.run(
            [claude, "-p", "--agent", agent_name, prompt],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return {
            "status": "ok" if r.returncode == 0 else "error",
            "stdout": (r.stdout or "")[:5000],
            "stderr": (r.stderr or "")[:2000],
            "rc": r.returncode,
        }
    except _sp.TimeoutExpired:
        return {"status": "error",
                "error": f"{agent_name} timeout after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _mock_invoke_lead(domain: str, eng: Path) -> dict:
    """--mock path: write a canned plan.md with a synthetic specialists list.

    Specialist set per domain (mirrors the agency mid-lead default rosters):
      dev:       backend-engineer + qa-engineer + tech-architect
      design:    ui-designer + ux-designer
      marketing: copywriter + seo-specialist
    """
    specialists_by_domain = {
        "dev": ["dev-backend-engineer", "dev-qa-engineer", "dev-tech-architect"],
        "design": ["design-ui-designer", "design-ux-designer"],
        "marketing": ["marketing-copywriter", "marketing-seo-specialist"],
    }
    specialists = specialists_by_domain.get(domain, ["dev-backend-engineer"])
    plan_path = eng / "plan.md"
    body = (
        f"---\n"
        f"plan_version: 1\n"
        f"author: {domain}-lead (mock)\n"
        f"specialists: [{', '.join(specialists)}]\n"
        f"---\n"
        f"\n"
        f"# Plan — engagement {eng.name} (mock)\n"
        f"\n"
        f"This plan was generated by `engagement_lg.py --mock` for end-to-end "
        f"testing. It is NOT a real lead-authored plan.\n"
        f"\n"
        f"## Phase 2 — dispatch\n"
        f"Specialists to dispatch in Phase 2: {', '.join(specialists)}.\n"
        f"\n"
        f"## Scope\nMock scope — see criteria.md.\n"
        f"\n"
        f"## Risks\nNone (mock).\n"
    )
    plan_path.write_text(body, encoding="utf-8")
    return {"status": "ok", "stdout": str(plan_path), "stderr": "", "rc": 0,
            "mock": True}


def _invoke_specialist_subprocess(specialist: str, eng: Path, prompt: str,
                                  timeout: int = 900,
                                  mock: bool = False) -> dict:
    """Invoke `claude -p --agent {specialist} <prompt>`.

    Each specialist writes executor-reports/{specialist}.md per protocol.
    Mock mode writes canned executor-report.
    """
    if mock:
        return _mock_invoke_specialist(specialist, eng)
    import subprocess as _sp
    claude = _find_claude_cmd()
    if not claude:
        return {"status": "error", "error": "claude CLI not found in PATH"}
    try:
        r = _sp.run(
            [claude, "-p", "--agent", specialist, prompt],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return {
            "status": "ok" if r.returncode == 0 else "error",
            "stdout": (r.stdout or "")[:5000],
            "stderr": (r.stderr or "")[:2000],
            "rc": r.returncode,
            "specialist": specialist,
        }
    except _sp.TimeoutExpired:
        return {"status": "error",
                "error": f"{specialist} timeout after {timeout}s",
                "specialist": specialist}
    except Exception as e:
        return {"status": "error", "error": str(e), "specialist": specialist}


def _mock_invoke_specialist(specialist: str, eng: Path) -> dict:
    """--mock path: write a canned executor-report and return ok."""
    reports_dir = eng / "executor-reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / f"{specialist}.md"
    body = (
        f"# Executor report — {specialist} (mock)\n"
        f"\n"
        f"## Criteria acknowledgement\n"
        f"- crit-1 — addressed (mock)\n"
        f"- crit-2 — addressed (mock)\n"
        f"\n"
        f"## Iteration 1\n"
        f"Mock specialist {specialist} executed on engagement "
        f"{eng.name}. No real work happened; this file exists so the "
        f"downstream graph (validators, manager) sees the artefacts they "
        f"expect.\n"
    )
    report_path.write_text(body, encoding="utf-8")
    return {"status": "ok", "stdout": str(report_path), "stderr": "", "rc": 0,
            "mock": True, "specialist": specialist}


def _invoke_manager_subprocess(domain: str, eng: Path, prompt: str,
                               timeout: int = 600,
                               mock: bool = False) -> dict:
    """Invoke `claude -p --agent {domain}-manager <prompt>` for acceptance.

    Manager reads handoff + consilium + human-directive + reflections; writes
    acceptance-log.md with verdict. Mock writes a canned ACCEPT acceptance-log.
    """
    if mock:
        return _mock_invoke_manager(domain, eng)
    import subprocess as _sp
    claude = _find_claude_cmd()
    if not claude:
        return {"status": "error", "error": "claude CLI not found in PATH"}
    agent_name = f"{domain}-manager"
    try:
        r = _sp.run(
            [claude, "-p", "--agent", agent_name, prompt],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return {
            "status": "ok" if r.returncode == 0 else "error",
            "stdout": (r.stdout or "")[:5000],
            "stderr": (r.stderr or "")[:2000],
            "rc": r.returncode,
        }
    except _sp.TimeoutExpired:
        return {"status": "error",
                "error": f"{agent_name} timeout after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _mock_invoke_manager(domain: str, eng: Path) -> dict:
    """--mock path: write canonical ACCEPT acceptance-log.md."""
    log_path = eng / "acceptance-log.md"
    body = (
        f"# Acceptance log — engagement {eng.name} (mock)\n"
        f"\n"
        f"## Iteration 1\n"
        f"\n"
        f"### Verdict: ACCEPT\n"
        f"\n"
        f"Mock {domain}-manager invocation. All criteria addressed per "
        f"executor-reports; no blocking findings. End-to-end test "
        f"verdict — not real acceptance.\n"
    )
    log_path.write_text(body, encoding="utf-8")
    return {"status": "ok", "stdout": str(log_path), "stderr": "", "rc": 0,
            "mock": True}


def _parse_acceptance_verdict(eng: Path) -> Optional[str]:
    """Extract canonical `### Verdict: ACCEPT|REJECT|ABORTED` from
    acceptance-log.md. Returns None if absent or unparseable."""
    log = eng / "acceptance-log.md"
    if not log.exists():
        return None
    text = log.read_text(encoding="utf-8")
    m = re.search(r"^###\s+Verdict:\s+(ACCEPT|REJECT|ABORTED)\b",
                  text, re.MULTILINE)
    return m.group(1) if m else None


def _run_validator_lg_subprocess(eng: Path, scripts_dir: Path,
                                 mock: bool = False) -> dict:
    """Run validator_lg.py --auto on the engagement. Parses JSON output.

    Returns {"status": "ok"|"error", "verdict": "ACCEPT"|"REJECT"|"partial",
             "ok": int, "fail": int, "raw": dict|str}.
    Mock simulates ACCEPT.
    """
    if mock:
        return {"status": "ok", "verdict": "ACCEPT", "ok": 0, "fail": 0,
                "raw": {"mock": True}, "mock": True}
    import subprocess as _sp
    script = scripts_dir / "validator_lg.py"
    if not script.exists():
        return {"status": "error", "error": "validator_lg.py missing",
                "verdict": "partial"}
    try:
        r = _sp.run(
            [sys.executable, str(script), str(eng), "--auto", "--json"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=3600,
        )
        try:
            data = json.loads(r.stdout)
        except Exception:
            return {"status": "error",
                    "error": f"validator_lg output unparseable: "
                             f"{(r.stdout or r.stderr or '')[:300]}",
                    "verdict": "partial"}
        ok = int(data.get("ok", 0))
        fail = int(data.get("fail", 0))
        # validator_lg exit 0 = no failures; 1 = at least one failure
        verdict = "ACCEPT" if (r.returncode == 0 and fail == 0) else "REJECT"
        return {"status": "ok", "verdict": verdict, "ok": ok, "fail": fail,
                "raw": data}
    except _sp.TimeoutExpired:
        return {"status": "error", "error": "validator_lg timeout",
                "verdict": "partial"}
    except Exception as e:
        return {"status": "error", "error": str(e), "verdict": "partial"}


def _run_adversary_lg_subprocess(eng: Path, tier: str, scripts_dir: Path,
                                 mock: bool = False) -> dict:
    """Run adversary_lg.py --consilium TIER. Parses JSON / reads
    consilium-summary.md.

    Returns {"status": "ok"|"error", "verdict": "ACCEPT"|"REJECT"|"DIRECTED",
             "raw": dict|str}.
    Mock simulates ACCEPT + writes minimal consilium-summary.md.
    """
    if mock:
        # Mock writes a minimal consilium-summary.md so downstream
        # checks (human-directive prerequisite) see the artefact.
        summary = eng / "consilium-summary.md"
        summary.write_text(
            f"# Consilium summary — {eng.name} (mock)\n\n"
            f"Tier: {tier}\n"
            f"Aggregate verdict: satisfied (mock)\n"
            f"No findings to adjudicate.\n",
            encoding="utf-8",
        )
        return {"status": "ok", "verdict": "ACCEPT", "raw": {"mock": True},
                "mock": True}
    import subprocess as _sp
    script = scripts_dir / "adversary_lg.py"
    if not script.exists():
        return {"status": "error", "error": "adversary_lg.py missing",
                "verdict": "partial"}
    try:
        r = _sp.run(
            [sys.executable, str(script), str(eng),
             "--consilium", tier, "--auto-synth", "--json"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=3600,
        )
        # adversary_lg writes consilium-summary.md as side effect.
        try:
            data = json.loads(r.stdout) if r.stdout else {}
        except Exception:
            data = {"raw_stdout": (r.stdout or "")[:300]}
        # Map aggregate verdict from adversary_lg JSON.
        agg = data.get("aggregate_verdict") or data.get("verdict") or "?"
        if agg in {"satisfied", "ACCEPT"}:
            verdict = "ACCEPT"
        elif agg in {"rework_required", "REJECT", "suspicious_too_clean"}:
            verdict = "REJECT"
        else:
            verdict = "DIRECTED"  # ambiguous → directed branch
        return {"status": "ok" if r.returncode == 0 else "error",
                "verdict": verdict, "raw": data}
    except _sp.TimeoutExpired:
        return {"status": "error", "error": "adversary_lg timeout",
                "verdict": "partial"}
    except Exception as e:
        return {"status": "error", "error": str(e), "verdict": "partial"}


def _run_archive_subprocess(eng: Path, scripts_dir: Path,
                            mock: bool = False) -> dict:
    """Run engagement-archive.py on the engagement. Mock = no-op."""
    if mock:
        return {"status": "ok", "mock": True}
    import subprocess as _sp
    script = scripts_dir / "engagement-archive.py"
    if not script.exists():
        return {"status": "error", "error": "engagement-archive.py missing"}
    try:
        r = _sp.run(
            [sys.executable, str(script), str(eng)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        return {"status": "ok" if r.returncode == 0 else "error",
                "stdout": (r.stdout or "")[:1000],
                "stderr": (r.stderr or "")[:500]}
    except _sp.TimeoutExpired:
        return {"status": "error", "error": "engagement-archive timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _parse_plan_specialists(plan_path: Path) -> list[str]:
    """Extract `specialists: [name1, name2, ...]` from plan.md YAML frontmatter.

    Accepts list-form (`specialists: [a, b, c]`) and bullet-form (multi-line
    `specialists:\n  - a\n  - b`). Returns [] if absent or unparseable.
    """
    if not plan_path.exists():
        return []
    text = plan_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return []
    body = fm_match.group(1)

    # Inline form: `specialists: [a, b, c]`
    m = re.search(r"^specialists\s*:\s*\[([^\]]+)\]", body, re.MULTILINE)
    if m:
        return [s.strip().strip('"').strip("'")
                for s in m.group(1).split(",")
                if s.strip()]

    # Bullet form: `specialists:` followed by `  - name` lines
    m = re.search(
        r"^specialists\s*:\s*\n((?:\s+-\s+[^\n]+\n?)+)",
        body, re.MULTILINE,
    )
    if m:
        bullets = re.findall(r"^\s+-\s+(\S+)", m.group(1), re.MULTILINE)
        return [b.strip().strip('"').strip("'") for b in bullets]

    return []


# ===========================================================================
# Nodes — placeholders for dry-run mode.
# Each node emits ledger events and returns minimum state updates so the
# In real mode, bodies invoke subprocess actors.
# ===========================================================================


def _intake_node(state: EngagementState) -> dict:
    """Real body: read criteria.md, run size-detect (--real only),
    validate frontmatter, populate state.

    Dry-run path: identical to skeleton (cold read of criteria.md only).
    """
    eng = Path(state["engagement"])
    _ledger_emit("phase_started", node=PHASE_NAMES["intake"],
                 payload={"iter_n": state.get("iter_n", 1)})

    # 1. Read criteria.md frontmatter (always — both dry-run and real).
    meta = _read_criteria_meta(eng)

    # 2. Real mode only: run size-detect --auto-promote. May mutate criteria.md.
    size_drift_info = None
    if not state.get("dry_run"):
        scripts_dir = Path(__file__).resolve().parent
        sd = _run_size_detect(eng, scripts_dir)
        size_drift_info = sd
        if sd.get("status") == "ok" and sd.get("promoted"):
            # size-detect updated criteria.md in-place; re-read.
            meta = _read_criteria_meta(eng)
        elif sd.get("status") == "error":
            # Log but don't fail — size-detect is helpful not blocking.
            print(f"WARN: size-detect failed: {sd.get('error', sd.get('raw', '?'))}",
                  file=sys.stderr)

    tier = (meta.get("size") or state.get("tier") or "M").upper()
    if tier not in {"S", "M", "L"}:
        tier = "M"
    domain = (meta.get("domain") or "dev").lower()
    ux_heavy = (meta.get("ux_heavy") or "false").lower()
    engagement_id = meta.get("engagement") or eng.name

    # 3. Real mode only: validate criteria-frontmatter structure via
    # lib.precheck.criteria.check_criteria_frontmatter. Failure raises.
    if not state.get("dry_run"):
        try:
            from lib.precheck.criteria import check_criteria_frontmatter
            cf = check_criteria_frontmatter(eng)
            if cf.get("status") == "fail":
                _ledger_emit("phase_completed", node=PHASE_NAMES["intake"],
                             payload={"intake_status": "error",
                                      "detail": cf.get("detail", "")},
                             verdict="REJECT")
                raise ValueError(
                    f"intake_node: criteria.md frontmatter invalid: "
                    f"{cf.get('detail', '?')}. Fix and re-invoke."
                )
        except ImportError:
            # lib.precheck not installed — skip validation, intake is best-effort.
            pass

    updates = {
        "engagement_id": engagement_id,
        "tier": tier,
        "domain": domain,
        "ux_heavy": ux_heavy,
        "iter_max": TIER_ITER_MAX[tier],
        "intake_status": "ok",
        "phase": PHASE_NAMES["intake"],
        "last_phase_at": _now(),
    }
    # Default HITL behaviour per tier unless already set by CLI flag.
    if "hitl_enabled" not in state:
        updates["hitl_enabled"] = TIER_USES_HITL_DEFAULT[tier]

    payload = {"tier": tier, "domain": domain, "ux_heavy": ux_heavy,
               "engagement_id": engagement_id}
    if size_drift_info and size_drift_info.get("promoted"):
        payload["size_promoted"] = (f"{size_drift_info.get('old')}"
                                    f"→{size_drift_info.get('new')}")
        payload["size_triggers"] = size_drift_info.get("triggered", [])[:3]
    _ledger_emit("phase_completed", node=PHASE_NAMES["intake"],
                 payload=payload, verdict="ACCEPT")
    return updates


def _criteria_lock_node(state: EngagementState) -> dict:
    """Optional HITL pause point between intake and plan.

    Only pauses when state['interrupt_on_criteria'] is True. Default off;
    most engagements skip straight to plan. Mirror of the HITL interrupt pattern.
    """
    if not state.get("interrupt_on_criteria") or not state.get("hitl_enabled", True):
        return {}  # pass-through

    payload = {
        "reason": "criteria_lock",
        "engagement_id": state.get("engagement_id"),
        "tier": state.get("tier"),
        "domain": state.get("domain"),
        "instructions": (
            "Review criteria.md. Resume with "
            "`python engagement_lg.py <eng> --resume-interrupt <thread> "
            "--decision PROCEED|ABORT [--note ...]`"
        ),
    }
    _ledger_emit("interrupt_paused", node="criteria_lock",
                 payload=payload, interrupt_state="paused")
    directive = interrupt(payload)
    _ledger_emit("interrupt_resumed", node="criteria_lock",
                 payload={"decision": (directive or {}).get("decision")},
                 interrupt_state="resumed")
    return {"human_directive": directive or {}, "paused_at": None}


def _plan_node(state: EngagementState) -> dict:
    """Real body: subprocess `claude -p --agent {domain}-lead` to
    author plan.md; parse frontmatter for specialists list.

    Dry-run path: skip subprocess, return empty specialists.
    """
    eng = Path(state["engagement"])
    domain = state.get("domain", "dev")
    iter_n = state.get("iter_n", 1)
    _ledger_emit("phase_started", node=PHASE_NAMES["plan"],
                 payload={"iter_n": iter_n, "tier": state.get("tier"),
                          "domain": domain})

    if state.get("dry_run"):
        # Dry-run: no subprocess. Specialists empty; downstream skeleton
        # treats this as "no fan-out" and skips dispatch fan-out cleanly.
        updates = {
            "plan_status": "ok",
            "specialists": [],
            "phase": PHASE_NAMES["plan"],
            "last_phase_at": _now(),
        }
        _ledger_emit("phase_completed", node=PHASE_NAMES["plan"],
                     payload={"plan_status": "ok", "dry_run": True,
                              "specialists_count": 0},
                     verdict="ACCEPT")
        return updates

    # Real mode: invoke lead-agent. Prompt asks lead to author plan.md
    # with structured frontmatter listing specialists.
    plan_path = eng / "plan.md"
    pre_existed = plan_path.exists()
    prompt = (
        f"You are {domain}-lead invoked by engagement_lg.py for Phase 1 (plan), "
        f"iteration {iter_n}.\n\n"
        f"Engagement path: {eng}\n\n"
        f"Task:\n"
        f"1. Read engagement/criteria.md (and engagement/scope-sync.md if it exists).\n"
        f"2. Write engagement/plan.md. Include YAML frontmatter at the top with "
        f"   a `specialists` field listing every specialist you would dispatch "
        f"   in Phase 2. Use list form: `specialists: [name1, name2, ...]` "
        f"   (e.g. `specialists: [dev-backend-engineer, dev-qa-engineer]`).\n"
        f"3. Below the frontmatter, write the standard plan.md body per "
        f"   engagement-protocol §plan (phases, scope, risks, deliverables).\n"
        f"4. DO NOT invoke any specialists yet — engagement_lg.py owns dispatch "
        f"   in Phase 2. Only write the plan.\n\n"
        f"When done, output the absolute path to plan.md as the last line."
    )
    result = _invoke_lead_subprocess(domain, eng, prompt, timeout=600,
                                     mock=bool(state.get("mock")))

    if result.get("status") != "ok":
        err = result.get("error") or result.get("stderr") or "?"
        _ledger_emit("phase_completed", node=PHASE_NAMES["plan"],
                     payload={"plan_status": "error",
                              "error": str(err)[:200]},
                     verdict="REJECT")
        raise RuntimeError(f"plan_node: lead-agent invocation failed: {err}")

    # Verify plan.md exists and was authored / updated.
    if not plan_path.exists():
        _ledger_emit("phase_completed", node=PHASE_NAMES["plan"],
                     payload={"plan_status": "error",
                              "error": "plan.md not written"},
                     verdict="REJECT")
        raise RuntimeError(
            f"plan_node: lead-agent returned ok (rc=0) but plan.md was not "
            f"written at {plan_path}. Inspect agent output: "
            f"{result.get('stdout', '')[:500]}"
        )

    specialists = _parse_plan_specialists(plan_path)
    if not specialists:
        # Lead wrote plan.md but no specialists frontmatter found.
        # Warn, but proceed — dispatch will be empty fan-out.
        print("WARN: plan_node: plan.md written but no `specialists:` "
              "frontmatter found. Dispatch will fan out to 0 specialists. "
              "Add `specialists: [...]` to plan.md YAML frontmatter.",
              file=sys.stderr)

    updates = {
        "plan_status": "ok",
        "specialists": specialists,
        "phase": PHASE_NAMES["plan"],
        "last_phase_at": _now(),
    }
    _ledger_emit("phase_completed", node=PHASE_NAMES["plan"],
                 payload={"plan_status": "ok",
                          "specialists_count": len(specialists),
                          "specialists": specialists[:10],  # cap payload size
                          "plan_pre_existed": pre_existed},
                 verdict="ACCEPT")
    return updates


def _danger_gate_node(state: EngagementState) -> dict:
    """Conditional HITL pause if danger-scan finds unauthorized ops.

    Skeleton: no danger-scan invocation, no pause. Real implementation runs
    `danger-scan.py --engagement <eng> --json` and pause if findings
    not already authorized in scope-sync.md.
    """
    if not state.get("hitl_enabled", True):
        return {}  # explicit disable

    # Skeleton: skip pause. Real mode would check.
    # When wired:
    #     findings = run_danger_scan(eng)
    #     unauthorized = filter_against_scope_sync(eng, findings)
    #     if unauthorized:
    #         _ledger_emit("interrupt_paused", node="danger_gate", ...)
    #         directive = interrupt({"reason": "danger_gate", ...})
    #         _ledger_emit("interrupt_resumed", ...)
    #         return {"human_directive": directive, "paused_at": None}
    return {}


def _dispatch_node(state: EngagementState) -> dict:
    """state-advance only. Actual Send fan-out happens via the
    `_route_after_dispatch` conditional edge attached to this node in
    `build_graph()`.

    Dry-run path: identical (no fan-out, specialists list is empty).
    """
    specialists = state.get("specialists", []) or []
    _ledger_emit("phase_started", node=PHASE_NAMES["dispatch"],
                 payload={"iter_n": state.get("iter_n", 1),
                          "specialist_count": len(specialists),
                          "specialists": specialists[:10]})
    # Per-specialist `specialist_dispatched` events emitted here too — the
    # Send fan-out below will emit `specialist_completed` per branch.
    for s in specialists:
        _ledger_emit("specialist_dispatched", node="dispatch",
                     actor=s,
                     payload={"specialist": s,
                              "iter_n": state.get("iter_n", 1)})

    return {
        "dispatch_status": "fan-out" if specialists else "no-specialists",
        "phase": PHASE_NAMES["dispatch"],
        "last_phase_at": _now(),
    }


def _specialist_node(state: EngagementState) -> dict:
    """Per-specialist branch invoked via Send. Each Send payload carries
    {specialist: "name", engagement, mock} so this node knows who it is.

    Subprocess `claude -p --agent <specialist>` (or mock); each
    specialist writes its executor-report into
    `engagement/executor-reports/{specialist}.md`.

    Dry-run path: skipped entirely (no fan-out from dispatch_node).
    """
    eng = Path(state["engagement"])
    specialist = state.get("specialist") or "?"  # type: ignore[index]
    iter_n = state.get("iter_n", 1)

    _ledger_emit("specialist_dispatched", node="specialist",
                 actor=specialist,
                 payload={"specialist": specialist, "iter_n": iter_n})

    if state.get("dry_run"):
        _ledger_emit("specialist_completed", node="specialist",
                     actor=specialist,
                     payload={"specialist": specialist,
                              "status": "dry_run_skip"})
        return {"specialist_results": [{"specialist": specialist,
                                        "status": "dry_run_skip"}]}

    prompt = (
        f"You are {specialist} invoked by engagement_lg.py for Phase 2 "
        f"(dispatch), iteration {iter_n}.\n\n"
        f"Engagement path: {eng}\n\n"
        f"Task:\n"
        f"1. Read engagement/criteria.md and engagement/plan.md.\n"
        f"2. Execute your role per your agent definition.\n"
        f"3. Write engagement/executor-reports/{specialist}.md with a "
        f"`## Criteria acknowledgement` section + `## Iteration {iter_n}` "
        f"section per engagement-protocol §executor-reports.\n"
        f"4. Do NOT invoke validators or other specialists.\n"
    )
    result = _invoke_specialist_subprocess(
        specialist, eng, prompt, timeout=900,
        mock=bool(state.get("mock")),
    )
    ok = (result.get("status") == "ok")
    _ledger_emit("specialist_completed", node="specialist",
                 actor=specialist,
                 payload={"specialist": specialist,
                          "status": result.get("status"),
                          "mock": bool(result.get("mock")),
                          "error": str(result.get("error") or "")[:200]
                                   if not ok else None})
    return {"specialist_results": [{
        "specialist": specialist,
        "status": result.get("status"),
        "mock": bool(result.get("mock")),
        "error": result.get("error") if not ok else None,
    }]}


def _barrier_dispatch_node(state: EngagementState) -> dict:
    """Sync point after Send fan-out to specialists. Emits a single
    `phase_completed(dispatch)` summary covering all branches."""
    results = state.get("specialist_results", []) or []
    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = sum(1 for r in results if r.get("status") not in {"ok",
                                                              "dry_run_skip"})
    _ledger_emit("barrier_passed", node="barrier_dispatch",
                 payload={"specialist_total": len(results),
                          "ok": ok, "fail": fail})
    _ledger_emit("phase_completed", node=PHASE_NAMES["dispatch"],
                 payload={"dispatch_status": "done",
                          "specialist_total": len(results),
                          "ok": ok, "fail": fail},
                 verdict="ACCEPT" if fail == 0 else "REJECT")
    return {"dispatch_status": "done" if fail == 0 else "error"}


def _validate_node(state: EngagementState) -> dict:
    """Delegate to validator_lg.py --auto subprocess (or mock).

    Dry-run path: pretend ACCEPT (skeleton).
    """
    eng = Path(state["engagement"])
    iter_n = state.get("iter_n", 1)
    _ledger_emit("phase_started", node=PHASE_NAMES["validate"],
                 payload={"iter_n": iter_n})

    if state.get("dry_run"):
        verdict = "ACCEPT"
        _ledger_emit("phase_completed", node=PHASE_NAMES["validate"],
                     payload={"validation_verdict": verdict,
                              "dry_run": True}, verdict=verdict)
        return {"validation_verdict": verdict,
                "phase": PHASE_NAMES["validate"],
                "last_phase_at": _now()}

    scripts_dir = Path(__file__).resolve().parent
    result = _run_validator_lg_subprocess(eng, scripts_dir,
                                          mock=bool(state.get("mock")))
    verdict = result.get("verdict", "partial")
    if result.get("status") != "ok":
        _ledger_emit("phase_completed", node=PHASE_NAMES["validate"],
                     payload={"validation_verdict": verdict,
                              "error": str(result.get("error", ""))[:200]},
                     verdict="REJECT" if verdict == "REJECT" else "N/A")
        # validator_lg subprocess error is NOT fatal — surface verdict
        # and let route decide. (Partial verdict will fall through to
        # consilium / accept depending on routing rules.)
    else:
        _ledger_emit("phase_completed", node=PHASE_NAMES["validate"],
                     payload={"validation_verdict": verdict,
                              "ok": result.get("ok", 0),
                              "fail": result.get("fail", 0),
                              "mock": bool(result.get("mock"))},
                     verdict=verdict)
    return {"validation_verdict": verdict,
            "phase": PHASE_NAMES["validate"],
            "last_phase_at": _now()}


def _consilium_node(state: EngagementState) -> dict:
    """Delegate to adversary_lg.py --consilium subprocess (or mock).
    Skip entirely for tier=S."""
    tier = state.get("tier", "M")
    if not TIER_USES_CONSILIUM.get(tier, True):
        _ledger_emit("phase_skipped", node=PHASE_NAMES["consilium"],
                     payload={"reason": f"tier={tier} skips consilium"})
        return {"consilium_verdict": "skipped_S",
                "phase": PHASE_NAMES["consilium"]}

    eng = Path(state["engagement"])
    _ledger_emit("phase_started", node=PHASE_NAMES["consilium"],
                 payload={"iter_n": state.get("iter_n", 1), "tier": tier})

    if state.get("dry_run"):
        verdict = "ACCEPT"
        _ledger_emit("phase_completed", node=PHASE_NAMES["consilium"],
                     payload={"consilium_verdict": verdict, "dry_run": True},
                     verdict=verdict)
        return {"consilium_verdict": verdict,
                "phase": PHASE_NAMES["consilium"],
                "last_phase_at": _now()}

    scripts_dir = Path(__file__).resolve().parent
    result = _run_adversary_lg_subprocess(eng, tier, scripts_dir,
                                          mock=bool(state.get("mock")))
    verdict = result.get("verdict", "partial")
    _ledger_emit("phase_completed", node=PHASE_NAMES["consilium"],
                 payload={"consilium_verdict": verdict,
                          "status": result.get("status"),
                          "mock": bool(result.get("mock")),
                          "error": str(result.get("error", ""))[:200]
                                   if result.get("status") != "ok" else None},
                 verdict=verdict if verdict in {"ACCEPT", "REJECT",
                                                "DIRECTED"} else "N/A")
    return {"consilium_verdict": verdict,
            "phase": PHASE_NAMES["consilium"],
            "last_phase_at": _now()}


def _human_directive_node(state: EngagementState) -> dict:
    """Mandatory HITL pause for M/L after consilium. Skeleton: pretend
    PROCEED_TO_VERDICT without actually pausing if hitl_enabled is False
    (e.g. --no-hitl debug mode)."""
    tier = state.get("tier", "M")
    if not TIER_USES_CONSILIUM.get(tier, True):
        # S tier: no consilium, no directive needed.
        return {"human_directive_decision": "skipped_S"}

    if not state.get("hitl_enabled", True):
        # --no-hitl: synthesize PROCEED directive without pause.
        return {"human_directive_decision": "PROCEED_TO_VERDICT",
                "human_directive": {"decision": "PROCEED_TO_VERDICT",
                                    "synthesized_no_hitl": True}}

    payload = {
        "reason": "human_directive",
        "engagement_id": state.get("engagement_id"),
        "tier": tier,
        "consilium_verdict": state.get("consilium_verdict"),
        "instructions": (
            "Read engagement/consilium-summary.md, then resume with "
            "`python engagement_lg.py <eng> --resume-interrupt <thread> "
            "--decision PROCEED_TO_VERDICT|REJECT_NOW|DIRECTED_VERDICT [--note ...]`"
        ),
    }
    _ledger_emit("interrupt_paused", node="human_directive",
                 payload=payload, interrupt_state="paused")
    directive = interrupt(payload)
    decision = (directive or {}).get("decision", "PROCEED_TO_VERDICT")
    _ledger_emit("interrupt_resumed", node="human_directive",
                 payload={"decision": decision}, interrupt_state="resumed")
    _ledger_emit("human_directive_received", node="human_directive",
                 payload=directive or {}, verdict=decision)
    return {"human_directive": directive or {},
            "human_directive_decision": decision,
            "paused_at": None}


def _manager_accept_node(state: EngagementState) -> dict:
    """Manager-agent writes acceptance-log.md with verdict. Real mode: subprocess
    `claude -p --agent {domain}-manager` (or mock); then parse the canonical
    `### Verdict: ACCEPT|REJECT|ABORTED` from acceptance-log.md.

    Dry-run path: skeleton ACCEPT (no subprocess, no acceptance-log written).
    Honors `human_directive_decision`: REJECT_NOW forces REJECT without
    invoking manager; DIRECTED_VERDICT and PROCEED_TO_VERDICT both invoke
    manager normally (manager reads directive itself per protocol).
    """
    eng = Path(state["engagement"])
    domain = state.get("domain", "dev")
    iter_n = state.get("iter_n", 1)
    directive = state.get("human_directive_decision")
    _ledger_emit("phase_started", node=PHASE_NAMES["accept"],
                 payload={"iter_n": iter_n,
                          "tier": state.get("tier"),
                          "human_directive_decision": directive})

    # REJECT_NOW short-circuits — human declared a hard reject; skip manager.
    if directive == "REJECT_NOW":
        verdict = "REJECT"
        _ledger_emit("verdict_written", node=PHASE_NAMES["accept"],
                     payload={"verdict": verdict, "iter_n": iter_n,
                              "reason": "human directive REJECT_NOW"},
                     verdict=verdict)
        _ledger_emit("phase_completed", node=PHASE_NAMES["accept"],
                     payload={"manager_verdict": verdict,
                              "short_circuited": True}, verdict=verdict)
        return {"manager_verdict": verdict,
                "phase": PHASE_NAMES["accept"],
                "last_phase_at": _now()}

    if state.get("dry_run"):
        verdict = "ACCEPT"
        _ledger_emit("verdict_written", node=PHASE_NAMES["accept"],
                     payload={"verdict": verdict, "iter_n": iter_n,
                              "dry_run": True}, verdict=verdict)
        _ledger_emit("phase_completed", node=PHASE_NAMES["accept"],
                     payload={"manager_verdict": verdict, "dry_run": True},
                     verdict=verdict)
        return {"manager_verdict": verdict,
                "phase": PHASE_NAMES["accept"],
                "last_phase_at": _now()}

    prompt = (
        f"You are {domain}-manager invoked by engagement_lg.py for Phase 5 "
        f"(acceptance), iteration {iter_n}.\n\n"
        f"Engagement path: {eng}\n\n"
        f"Task: per acceptance-protocol §"
        f"acceptor, read handoff.md + consilium-summary.md (if present) + "
        f"human-directive.md (if present) + engagement-reflections.md (if "
        f"present), then write engagement/acceptance-log.md with a canonical "
        f"`### Verdict: ACCEPT|REJECT|ABORTED` line per protocol §11."
    )
    result = _invoke_manager_subprocess(domain, eng, prompt, timeout=600,
                                        mock=bool(state.get("mock")))
    if result.get("status") != "ok":
        err = result.get("error") or result.get("stderr") or "?"
        _ledger_emit("phase_completed", node=PHASE_NAMES["accept"],
                     payload={"manager_verdict": "error",
                              "error": str(err)[:200]},
                     verdict="REJECT")
        raise RuntimeError(f"manager_accept_node: {domain}-manager "
                           f"invocation failed: {err}")

    verdict = _parse_acceptance_verdict(eng)
    if verdict is None:
        _ledger_emit("phase_completed", node=PHASE_NAMES["accept"],
                     payload={"manager_verdict": "unparseable"},
                     verdict="N/A")
        raise RuntimeError(
            f"manager_accept_node: {domain}-manager returned ok but "
            f"acceptance-log.md missing canonical `### Verdict: "
            f"ACCEPT|REJECT|ABORTED`. Inspect "
            f"{eng / 'acceptance-log.md'}."
        )

    _ledger_emit("verdict_written", node=PHASE_NAMES["accept"],
                 payload={"verdict": verdict, "iter_n": iter_n,
                          "mock": bool(result.get("mock"))},
                 verdict=verdict)
    _ledger_emit("phase_completed", node=PHASE_NAMES["accept"],
                 payload={"manager_verdict": verdict,
                          "mock": bool(result.get("mock"))},
                 verdict=verdict)
    return {"manager_verdict": verdict,
            "phase": PHASE_NAMES["accept"],
            "last_phase_at": _now()}


def _archive_node(state: EngagementState) -> dict:
    """Delegate to engagement-archive.py subprocess (or mock).
    Skip if not ACCEPTed."""
    mv = state.get("manager_verdict")
    if mv != "ACCEPT":
        _ledger_emit("phase_skipped", node=PHASE_NAMES["archive"],
                     payload={"reason": f"manager_verdict={mv} not ACCEPT"})
        return {"archive_status": "skipped_REJECT",
                "phase": PHASE_NAMES["done"]}

    eng = Path(state["engagement"])
    _ledger_emit("phase_started", node=PHASE_NAMES["archive"], payload={})

    if state.get("dry_run"):
        _ledger_emit("phase_completed", node=PHASE_NAMES["archive"],
                     payload={"archive_status": "ok", "dry_run": True},
                     verdict="ACCEPT")
        return {"archive_status": "ok", "phase": PHASE_NAMES["done"]}

    scripts_dir = Path(__file__).resolve().parent
    result = _run_archive_subprocess(eng, scripts_dir,
                                     mock=bool(state.get("mock")))
    ok = (result.get("status") == "ok")
    _ledger_emit("phase_completed", node=PHASE_NAMES["archive"],
                 payload={"archive_status": "ok" if ok else "error",
                          "mock": bool(result.get("mock")),
                          "error": str(result.get("error", ""))[:200]
                                   if not ok else None},
                 verdict="ACCEPT" if ok else "REJECT")
    return {"archive_status": "ok" if ok else "error",
            "phase": PHASE_NAMES["done"]}


# ===========================================================================
# Routing
# ===========================================================================


def _route_after_validate(state: EngagementState) -> str:
    """Loop back to plan on REJECT (if budget allows), else proceed."""
    verdict = state.get("validation_verdict")
    iter_n = state.get("iter_n", 1)
    iter_max = state.get("iter_max", TIER_ITER_MAX.get(state.get("tier", "M"), 2))
    if verdict == "REJECT" and iter_n < iter_max:
        return "plan"  # rework — note: requires iter_n increment in plan_node entry
    tier = state.get("tier", "M")
    return "consilium" if TIER_USES_CONSILIUM.get(tier, True) else "manager_accept"


def _route_after_consilium(state: EngagementState) -> str:
    """After consilium (or skip for S), go to human_directive."""
    return "human_directive"


def _route_after_directive(state: EngagementState) -> str:
    """After human_directive, go to manager_accept (or END for REJECT_NOW)."""
    decision = state.get("human_directive_decision")
    if decision == "REJECT_NOW":
        # Manager skipped; treat as REJECT directly (real mode handles this
        # branch with a dedicated reject-finalize node).
        return "manager_accept"  # still passes through, will write REJECT
    return "manager_accept"


def _route_after_accept(state: EngagementState) -> str:
    """Manager verdict resolution: ACCEPT→archive, REJECT→loop or END, ABORTED→END."""
    verdict = state.get("manager_verdict")
    iter_n = state.get("iter_n", 1)
    iter_max = state.get("iter_max", TIER_ITER_MAX.get(state.get("tier", "M"), 2))
    if verdict == "ACCEPT":
        return "archive"
    if verdict == "REJECT" and iter_n < iter_max:
        return "plan"
    # REJECT at budget OR ABORTED → END (archive skipped).
    return "end"


def _route_after_dispatch(state: EngagementState):
    """Send fan-out to specialist branches.

    Returns a list of `Send("specialist", payload)` — one per specialist
    from state.specialists. If no specialists (dry-run or empty plan),
    short-circuits directly to barrier_dispatch so the graph still
    advances to validate.
    """
    specialists = state.get("specialists", []) or []
    if not specialists:
        return "barrier_dispatch"
    return [
        Send("specialist", {
            "engagement": state["engagement"],
            "specialist": s,
            "iter_n": state.get("iter_n", 1),
            "dry_run": bool(state.get("dry_run")),
            "mock": bool(state.get("mock")),
        })
        for s in specialists
    ]


# ===========================================================================
# Graph
# ===========================================================================


def build_graph(checkpointer=None):
    builder = StateGraph(EngagementState)

    builder.add_node("intake",            _intake_node)
    builder.add_node("criteria_lock",     _criteria_lock_node)
    builder.add_node("plan",              _plan_node)
    builder.add_node("danger_gate",       _danger_gate_node)
    builder.add_node("dispatch",          _dispatch_node)
    builder.add_node("specialist",        _specialist_node)
    builder.add_node("barrier_dispatch",  _barrier_dispatch_node)
    builder.add_node("validate",          _validate_node)
    builder.add_node("consilium",         _consilium_node)
    builder.add_node("human_directive",   _human_directive_node)
    builder.add_node("manager_accept",    _manager_accept_node)
    builder.add_node("archive",           _archive_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "criteria_lock")
    builder.add_edge("criteria_lock", "plan")
    builder.add_edge("plan", "danger_gate")
    builder.add_edge("danger_gate", "dispatch")

    # Dispatch fans out via Send to specialist branches.
    # Empty specialists list short-circuits to barrier_dispatch.
    builder.add_conditional_edges(
        "dispatch", _route_after_dispatch,
        ["specialist", "barrier_dispatch"],
    )
    # Every specialist branch funnels into barrier_dispatch (sync point).
    builder.add_edge("specialist", "barrier_dispatch")
    builder.add_edge("barrier_dispatch", "validate")

    builder.add_conditional_edges(
        "validate", _route_after_validate,
        {"plan": "plan", "consilium": "consilium",
         "manager_accept": "manager_accept"},
    )
    builder.add_conditional_edges(
        "consilium", _route_after_consilium,
        {"human_directive": "human_directive"},
    )
    builder.add_conditional_edges(
        "human_directive", _route_after_directive,
        {"manager_accept": "manager_accept"},
    )
    builder.add_conditional_edges(
        "manager_accept", _route_after_accept,
        {"plan": "plan", "archive": "archive", "end": END},
    )
    builder.add_edge("archive", END)

    return builder.compile(checkpointer=checkpointer)


# ===========================================================================
# Checkpointer
# ===========================================================================


CHECKPOINT_DB = Path(__file__).resolve().parent / ".engagement-lg-checkpoints.sqlite"


def make_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    return SqliteSaver(conn)


def thread_id_for(eng: Path) -> str:
    """Stable thread_id per engagement (NOT per iter — engagement_lg owns
    all iterations within one engagement)."""
    h = hashlib.sha1(str(eng).encode("utf-8")).hexdigest()[:12]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{h}-engagement-{ts}"


# ===========================================================================
# LangSmith hook (mirror validator_lg.py / adversary_lg.py pattern)
# ===========================================================================


def setup_langsmith() -> str:
    """Return a one-line status string. Auto-instrumented when
    LANGSMITH_API_KEY + LANGSMITH_PROJECT env vars are set."""
    if os.environ.get("LANGSMITH_API_KEY") and os.environ.get("LANGSMITH_PROJECT"):
        return (f"[LangSmith] project={os.environ['LANGSMITH_PROJECT']} "
                f"(traces will appear at https://smith.langchain.com)")
    return "[LangSmith] disabled (set LANGSMITH_API_KEY + LANGSMITH_PROJECT to enable)"


# ===========================================================================
# Status mode (cold read — no graph invocation)
# ===========================================================================


def _read_acceptance_verdict(eng: Path) -> Optional[str]:
    log = eng / "acceptance-log.md"
    if not log.exists():
        return None
    text = log.read_text(encoding="utf-8")
    m = re.search(r"^###\s+Verdict:\s+(ACCEPT|REJECT|ABORTED)\b",
                  text, re.MULTILINE)
    return m.group(1) if m else None


def _status_main(eng: Path, args) -> int:
    """Read engagement state from artefacts (no graph invocation).

    Sources:
      - criteria.md frontmatter: tier, domain, ux_heavy
      - iteration file: current iter_n
      - acceptance-log.md: final verdict (if any)
      - events.jsonl: phase transitions (most recent phase_started/completed)
      - validation-outputs/: most-recent iter run
      - consilium-summary.md: presence
      - human-directive.md: presence + parsed decision
    """
    meta = _read_criteria_meta(eng)
    tier = (meta.get("size") or "?").upper()
    domain = meta.get("domain") or "?"
    ux_heavy = meta.get("ux_heavy") or "?"
    iter_n = _read_iter_counter(eng)

    consilium_present = (eng / "consilium-summary.md").exists()
    directive_present = (eng / "human-directive.md").exists()
    handoff_present = (eng / "handoff.md").exists()
    acceptance_verdict = _read_acceptance_verdict(eng)

    # Latest phase from events.jsonl (if present)
    last_phase = None
    events_path = eng / "events.jsonl"
    if events_path.exists():
        try:
            for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                ev = json.loads(line)
                pt = ev.get("payload_type")
                if pt in ("phase_started", "phase_completed", "phase_skipped"):
                    last_phase = ev.get("node")
                    break
        except Exception:
            pass

    status = {
        "engagement": str(eng),
        "engagement_id": meta.get("engagement") or eng.name,
        "tier": tier,
        "domain": domain,
        "ux_heavy": ux_heavy,
        "iter_n": iter_n,
        "iter_max": TIER_ITER_MAX.get(tier, "?"),
        "handoff_present": handoff_present,
        "consilium_present": consilium_present,
        "directive_present": directive_present,
        "acceptance_verdict": acceptance_verdict,
        "last_phase_in_ledger": last_phase,
    }

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"Engagement: {status['engagement_id']} ({tier}-tier, {domain}, ux_heavy={ux_heavy})")
        print(f"  Path:     {eng}")
        print(f"  Iter:     {iter_n} / max {status['iter_max']}")
        print(f"  Phase (ledger): {last_phase or 'no ledger / no phase events'}")
        print(f"  Handoff:        {'present' if handoff_present else 'absent'}")
        print(f"  Consilium:      {'present' if consilium_present else 'absent'}")
        print(f"  Human-directive:{'present' if directive_present else 'absent'}")
        print(f"  Verdict:        {acceptance_verdict or 'not written yet'}")
    return 0


# ===========================================================================
# Resume mode
# ===========================================================================


def _resume_interrupt_main(eng: Path, args) -> int:
    """Resume a paused graph by thread_id with a human directive."""
    if not args.decision:
        print("ERROR: --resume-interrupt requires --decision",
              file=sys.stderr)
        return 2
    directive_payload = {
        "decision": args.decision,
        "note": args.note,
        "reasons": args.reasons,
    }

    checkpointer = make_checkpointer()
    try:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": args.resume_interrupt}}
        try:
            final_state = graph.invoke(Command(resume=directive_payload), config)
        except Exception as e:
            print(f"ERROR: resume failed: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return 2
    finally:
        try:
            checkpointer.conn.close()
        except Exception:
            pass

    if isinstance(final_state, dict) and final_state.get("__interrupt__"):
        # Could pause again at a later HITL point.
        msg = _format_pause(final_state, args.resume_interrupt, eng, args)
        return 0

    return _print_final(final_state, args)


# ===========================================================================
# Output formatting
# ===========================================================================


def _format_pause(state: dict, thread_id: str, eng: Path, args) -> int:
    interrupt_info = state.get("__interrupt__")
    payload = None
    try:
        first = interrupt_info[0] if interrupt_info else None
        payload = getattr(first, "value", None) or (
            first[0] if isinstance(first, tuple) else None
        )
    except Exception:
        payload = None
    msg = {
        "status": "paused",
        "thread_id": thread_id,
        "resume_help": (
            f"python engagement_lg.py {eng} --resume-interrupt {thread_id} "
            f"--decision PROCEED_TO_VERDICT|REJECT_NOW|DIRECTED_VERDICT|PROCEED|ABORT "
            f"[--note ...]"
        ),
        "payload": payload,
    }
    if args.json:
        print(json.dumps(msg, ensure_ascii=False, indent=2))
    else:
        print(f"PAUSED. thread_id={thread_id}", file=sys.stderr)
        print(f"Resume with: {msg['resume_help']}", file=sys.stderr)
    return 0


def _print_final(state: dict, args) -> int:
    mv = state.get("manager_verdict") or "?"
    av = state.get("archive_status") or "?"
    iter_n = state.get("iter_n", 1)
    tier = state.get("tier", "?")
    if args.json:
        print(json.dumps({
            "engagement_id": state.get("engagement_id"),
            "tier": tier,
            "iter_n": iter_n,
            "manager_verdict": mv,
            "archive_status": av,
            "validation_verdict": state.get("validation_verdict"),
            "consilium_verdict": state.get("consilium_verdict"),
            "human_directive_decision": state.get("human_directive_decision"),
            "phase": state.get("phase"),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Engagement {state.get('engagement_id')} ({tier}-tier, iter={iter_n})")
        print(f"  validation_verdict:        {state.get('validation_verdict')}")
        print(f"  consilium_verdict:         {state.get('consilium_verdict')}")
        print(f"  human_directive_decision:  {state.get('human_directive_decision')}")
        print(f"  manager_verdict:           {mv}")
        print(f"  archive_status:            {av}")
    return 0 if mv == "ACCEPT" else 1


# ===========================================================================
# Main
# ===========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LangGraph engagement-level orchestrator ",
    )
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--status", action="store_true",
                        help="Print engagement state without invoking graph")
    parser.add_argument("--resume", action="store_true",
                        help="Continue from checkpoint without re-init")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Skeleton mode: emit ledger, skip real work "
                             "(DEFAULT)")
    parser.add_argument("--real", action="store_true",
                        help="Disable --dry-run; run real subprocess calls "
                             "(requires claude CLI in PATH for lead / "
                             "specialist / manager nodes). Mutually exclusive "
                             "with --mock.")
    parser.add_argument("--mock", action="store_true",
                        help="Run real graph paths but with mock invokers: "
                             "subprocess wrappers write canned artefacts "
                             "instead of calling claude CLI. Lets you smoke "
                             "the full end-to-end pipeline on boxes without "
                             "claude CLI. Mutually exclusive with --real.")
    parser.add_argument("--tier-override", choices=["S", "M", "L"],
                        help="Bypass criteria.md tier")
    parser.add_argument("--no-hitl", action="store_true",
                        help="Disable all HITL pauses (debug)")
    parser.add_argument("--interrupt-on-criteria", action="store_true",
                        help="Add criteria_lock HITL pause point")
    parser.add_argument("--resume-interrupt", type=str, metavar="THREAD_ID",
                        help="Resume paused graph by thread_id; requires --decision")
    parser.add_argument("--decision", type=str, default=None,
                        help="Resume decision: PROCEED_TO_VERDICT|REJECT_NOW|"
                             "DIRECTED_VERDICT|PROCEED|ABORT")
    parser.add_argument("--note", type=str, default=None,
                        help="Optional note attached to --decision")
    parser.add_argument("--reasons", type=str, default=None,
                        help="Optional reasons string for --decision")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Disable SqliteSaver (no resume possible)")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    # Status mode short-circuits.
    if args.status:
        return _status_main(eng, args)

    # Resume mode short-circuits.
    if args.resume_interrupt:
        return _resume_interrupt_main(eng, args)

    # Mode resolution
    # Mode resolution: --dry-run is default; --real OR --mock flips it.
    # --real and --mock are mutually exclusive.
    if args.real and args.mock:
        parser.error("--real and --mock are mutually exclusive")
    dry_run = not (args.real or args.mock)
    if args.real:
        print("[engagement-lg] --real mode: real subprocess calls to "
              "claude CLI / validator_lg / adversary_lg / engagement-archive. "
              "Will fail fast if claude CLI not in PATH.", file=sys.stderr)
    elif args.mock:
        print("[engagement-lg] --mock mode: real graph paths, but "
              "subprocess wrappers return canned artefacts. No claude CLI / "
              "no external state.", file=sys.stderr)

    # LangSmith status to stderr (stdout reserved for --json).
    print(setup_langsmith(), file=sys.stderr)

    # Initialize event ledger (fail-safe).
    global _RUN_LEDGER
    if _LEDGER_AVAILABLE:
        try:
            meta = _read_criteria_meta(eng)
            tier_for_ledger = (
                (args.tier_override or meta.get("size") or "M").upper()
            )
            if tier_for_ledger not in {"S", "M", "L"}:
                tier_for_ledger = "M"
            _RUN_LEDGER = EventLedger(
                eng, agent="engagement-lg", tier=tier_for_ledger,
            )
            _RUN_LEDGER.emit(
                "engagement_started",
                node="engagement_lg:main",
                payload={
                    "tier": tier_for_ledger,
                    "iter_n": _read_iter_counter(eng),
                    "dry_run": dry_run,
                    "hitl_enabled": (not args.no_hitl),
                    "interrupt_on_criteria": bool(args.interrupt_on_criteria),
                    "resume": bool(args.resume),
                },
            )
            if dry_run:
                _RUN_LEDGER.emit(
                    "dryrun_marker",
                    node="engagement_lg:main",
                    payload={
                        "reason": "skeleton mode — node bodies are placeholders",
                        "next_waves": ["B: intake+plan", "C: dispatch+specialists",
                                       "D: validate+consilium", "E: accept+archive",
                                       "F: tests + field test"],
                    },
                )
        except Exception as e:
            print(f"WARN: ledger init failed (continuing without ledger): {e}",
                  file=sys.stderr)
            _RUN_LEDGER = None

    # Init state.
    init_state: EngagementState = {
        "engagement": str(eng),
        "iter_n": _read_iter_counter(eng),
        "dry_run": dry_run,
        "mock": bool(args.mock),
        "interrupt_on_criteria": bool(args.interrupt_on_criteria),
        "specialist_results": [],
        "started_at": _now(),
    }
    if args.tier_override:
        init_state["tier"] = args.tier_override
    if args.no_hitl:
        init_state["hitl_enabled"] = False
    # (intake_node populates remaining criteria meta from criteria.md.)

    checkpointer = None if args.no_checkpoint else make_checkpointer()
    thread_id = thread_id_for(eng)

    try:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            if args.resume:
                # Pure resume — replay from checkpoint (no init state).
                final_state = graph.invoke(None, config)
            else:
                final_state = graph.invoke(init_state, config)
        except NotImplementedError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"ERROR: graph execution failed: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return 2
    finally:
        if checkpointer is not None:
            try:
                checkpointer.conn.close()
            except Exception:
                pass

    # Pause detection (any HITL interrupt fires up to caller).
    if isinstance(final_state, dict) and final_state.get("__interrupt__"):
        return _format_pause(final_state, thread_id, eng, args)

    # Emit final lifecycle event.
    mv = final_state.get("manager_verdict") or "ABORTED"
    _ledger_emit(
        "engagement_completed",
        node="engagement_lg:main",
        payload={
            "manager_verdict": mv,
            "iter_n": final_state.get("iter_n", 1),
            "tier": final_state.get("tier"),
            "duration_s": None,  # populated when started_at deltas measured
        },
        verdict=mv if mv in {"ACCEPT", "REJECT", "ABORTED"} else "N/A",
    )

    return _print_final(final_state, args)


if __name__ == "__main__":
    sys.exit(main())
