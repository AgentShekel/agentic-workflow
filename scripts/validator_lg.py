#!/usr/bin/env python3
"""LangGraph validator orchestrator — first release.

Parallel Send fan-out across atomic validator subagents. Replaces lead's
manual sequential dispatch with one graph invocation. Absorbs
validator-retry.py's recovery loop (corrupt JSON → 1 retry → mark fail).

The 21-validator atomic set per `validation-pipeline` skill rules:
  Dev validators (17): code-reviewer, security-auditor, reality-checker, skeptic,
                  performance-validator, migration-validator, test-reviewer,
                  completeness-validator, task-validator, tech-spec-validator,
                  userspec-quality-validator, userspec-adequacy-validator,
                  feasibility-assessor, infrastructure-reviewer, deploy-reviewer,
                  interview-completeness-checker, anti-pattern-detector
  Design (1):     accessibility-validator (+ ux-review as future internal-subgraph)
  Meta (3):       documentation-reviewer, prompt-reviewer, skill-checker
                  (prompt-reviewer + skill-checker have applies_on=[] meaning
                   "caller-explicit only" — never auto-selected)
  Cross (1):      product-context-validator (Phase 3, embedding-fit, fires on
                  cross-domain engagements)

Excluded from this orchestrator (have their own internal flows):
  pre-deploy-qa, post-deploy-qa  — EXECUTE tests/MCP (internal-subgraph
                                    candidates per chain audit)
  ux-review                      — heaviest logic, internal-subgraph

Invoker modes (--invoker, default subprocess):
  subprocess  claude -p --agent <name>   — rides existing subscription, no
                                            billing change. Default & tested.
  mock        canned output, no LLM calls — for testing the graph wiring.
  api         (deferred to v2)            — direct LangChain ChatAnthropic.

Resume model (artefact-driven, same shape as adversary_lg.py):
  --resume      Skip validators that already have a valid final output
                for this engagement+iter in validation-outputs/, re-run
                the rest. Crash recovery and partial re-runs both work
                without checkpoint replay.

Observability:
  LangSmith tracing auto-instruments when env vars are set:
    LANGSMITH_TRACING=true + LANGSMITH_API_KEY=<key>
    Optional: LANGSMITH_PROJECT=<name>  (defaults to "validator-lg")

Usage (subprocess invoker — default):
  python validator_lg.py engagement/ --validators code-reviewer,security-auditor
  python validator_lg.py engagement/ --auto  # plan from criteria + validation-pipeline rules
  python validator_lg.py engagement/ --auto --json
  python validator_lg.py engagement/ --validators code-reviewer --invoker mock
  python validator_lg.py engagement/ --auto --resume  # crash-resume: skip already-done

Output (per validator, identical to lead's current manual flow — consumed
by handoff-precheck.py and director acceptance unchanged):
  engagement/validation-outputs/{validator}-iter-{N}-{ts}.json
  engagement/validation-log.md       (appended)

Exit codes:
  0 — every requested validator produced parseable output (all retries succeeded)
  1 — at least one validator failed after retry
  2 — invocation error
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# venv bootstrap — share the venv with adversary_lg.py.
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
    already_in_venv = _Path(_sys.executable).resolve() == venv_py.resolve() if venv_py.exists() else False
    if venv_py.exists() and not already_in_venv:
        import subprocess as _sp
        _sys.exit(_sp.run([str(venv_py), str(here), *_sys.argv[1:]]).returncode)
    _sys.stderr.write(
        "validator_lg.py needs langgraph/langchain. Create the venv:\n"
        f'  python -m venv "{_VENV}"\n'
        f'  "{(_VENV / "Scripts" / "python.exe")}" -m pip install -r '
        f'"{here.parent / "requirements-adversary-lg.txt"}"\n'
    )
    _sys.exit(2)


_bootstrap()

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import operator
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

# Append-only event ledger. Optional dependency:
# if lib.ledger is unavailable (script run from a stripped install), wiring
# degrades to no-op so validator_lg.py remains usable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lib.ledger import EventLedger  # noqa: E402
    _LEDGER_AVAILABLE = True
except Exception:
    EventLedger = None  # type: ignore
    _LEDGER_AVAILABLE = False

# Shared claude CLI resolver — single source of the Windows .CMD->.exe logic.
from lib.claude_path import find_claude_cmd as _find_claude_cmd  # noqa: E402

# Module-level ledger for the current main() invocation. Set in main(), used
# by node functions. Single-process / single-invocation assumption; concurrent
# validator_lg invocations within one Python process would race here — not a
# real production case (we invoke as a subprocess from leads).
_RUN_LEDGER: Optional["EventLedger"] = None


def _ledger_emit(payload_type: str, **kwargs) -> Optional[str]:
    """No-op when ledger unavailable / unset. Returns event_id on success."""
    if _RUN_LEDGER is None:
        return None
    try:
        return _RUN_LEDGER.emit(payload_type, **kwargs)
    except Exception as e:
        # Ledger must never break the validator graph — log to stderr and move on.
        print(f"WARN: ledger emit failed ({payload_type}): {e}", file=sys.stderr)
        return None

# ===========================================================================
# Pydantic — lenient base schema for validator outputs.
# Per-validator strict schemas would mean 20+ classes; instead, one base
# accepts the union of common shapes and downstream consumers
# (consilium-synth / handoff-precheck) already tolerate this.
# ===========================================================================

# Common status values seen across validators:
#   code-reviewer/security/reality/skeptic: satisfied | rework_required | suspicious_too_clean
#   tech-spec/task/userspec-quality: pass | fail | needs_improvement
#   completeness: complete | partial | needs_more
#   accessibility/migration: passed | failed | warnings
#   anti-pattern-detector: clean | issues_found
#   feasibility: go | no_go | conditional
#   pre-conditions: blocked | not_applicable
LENIENT_STATUSES = {
    "satisfied", "rework_required", "suspicious_too_clean",
    "pass", "passed", "fail", "failed", "needs_improvement",
    "complete", "partial", "needs_more", "warnings",
    "clean", "issues_found",
    "go", "no_go", "conditional",
    "blocked", "not_applicable",
    "approved", "approved_with_suggestions", "changes_required",
    "ok", "error",
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow")
    severity: Optional[str] = None
    location: Optional[str] = None
    message: Optional[str] = None
    category: Optional[str] = None
    fix: Optional[str] = None


class ValidatorOutput(BaseModel):
    """Lenient base for all validator subagent outputs."""
    model_config = ConfigDict(extra="allow")
    status: str
    findings: list[Finding] = Field(default_factory=list)
    summary: Optional[str] = None
    methodology: Optional[str] = None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        v_low = (v or "").strip().lower()
        # Accept anything from LENIENT_STATUSES; coerce unknown to "error".
        if v_low in LENIENT_STATUSES:
            return v_low
        return v_low or "error"


# ===========================================================================
# Canonical envelope — canonical validator output schema + normalizer.
# Pydantic discriminated-finding union; the normalizer coerces the 23
# validator variants into one shape so downstream consumers (manager,
# Langfuse, analytics, dashboards) see a stable schema. Original raw output
# is kept in the on-disk JSON; the canonical payload sits next to it inside
# the same file under key `canonical`.
# ===========================================================================

CANONICAL_SCHEMA_VERSION = "1.0"

# Verdict normalization — collapses LENIENT_STATUSES into 5 canonical values.
_VERDICT_MAP = {
    # approved
    "satisfied": "approved",
    "pass": "approved",
    "passed": "approved",
    "complete": "approved",
    "clean": "approved",
    "go": "approved",
    "ok": "approved",
    # changes_required
    "rework_required": "changes_required",
    "fail": "changes_required",
    "failed": "changes_required",
    "no_go": "changes_required",
    "issues_found": "changes_required",
    "needs_improvement": "approved_with_caveats",
    "needs_more": "approved_with_caveats",
    "warnings": "approved_with_caveats",
    "conditional": "approved_with_caveats",
    "partial": "approved_with_caveats",
    # suspicious
    "suspicious_too_clean": "suspicious",
    # skipped
    "blocked": "skipped",
    "not_applicable": "skipped",
    "na": "skipped",
    # error
    "error": "error",
}

# Severity normalization — collapses ~15 free-form severity strings into 5.
_SEVERITY_MAP = {
    "critical": "critical", "crit": "critical", "blocker": "critical",
    "blocking": "critical", "severe": "critical",
    "high": "high", "major": "high", "important": "high",
    "medium": "medium", "moderate": "medium", "med": "medium",
    "warn": "medium", "warning": "medium",
    "low": "low", "minor": "low",
    "info": "info", "informational": "info", "note": "info", "nit": "info",
}

# Validators that emit numerical scores (must carry `methodology`).
_NUMERICAL_VALIDATORS = {
    "accessibility-validator",
    "performance-validator",
    "security-auditor",
    "ux-review",
    "anti-pattern-detector",
}


def normalize_verdict(raw: Optional[str]) -> str:
    if raw is None:
        return "error"
    return _VERDICT_MAP.get(str(raw).strip().lower(), str(raw).strip().lower() or "error")


def normalize_severity(raw: Optional[str]) -> str:
    if raw is None:
        return "info"
    return _SEVERITY_MAP.get(str(raw).strip().lower(), "info")


def canonicalize_validator_output(validator: str, parsed: "ValidatorOutput") -> dict:
    """Coerce a ValidatorOutput (lenient base) into the canonical envelope.

    Output shape:
      {
        "schema_version": "1.0",
        "validator": str,
        "validator_type": "numerical" | "judgement",
        "verdict": str,        # one of approved | approved_with_caveats |
                               # changes_required | suspicious | skipped | error
        "summary": str | None,
        "methodology": str | None,
        "findings": [
          {
            "id": str,             # synthetic, "{validator}#{idx}"
            "severity": str,       # critical | high | medium | low | info
            "category": str | None,
            "issue": str,          # original `message` / `issue` / `description`
            "fix": str | None,
            "evidence": str | None,
            "location": str | None,
          }
        ],
        "metrics": dict | None,    # numerical validators only; pulled from extras
      }

    The original raw fields remain available via `parsed.model_dump()` —
    canonical is additive, not lossy.
    """
    raw_dict = parsed.model_dump()
    findings_canonical: list[dict] = []
    for idx, f in enumerate(parsed.findings):
        f_raw = f.model_dump() if hasattr(f, "model_dump") else dict(f or {})
        issue = (
            f_raw.get("message")
            or f_raw.get("issue")
            or f_raw.get("description")
            or f_raw.get("detail")
            or ""
        )
        findings_canonical.append({
            "id": f"{validator}#{idx}",
            "severity": normalize_severity(f_raw.get("severity")),
            "category": f_raw.get("category"),
            "issue": str(issue),
            "fix": f_raw.get("fix"),
            "evidence": f_raw.get("evidence") or f_raw.get("source"),
            "location": f_raw.get("location"),
        })

    is_numerical = validator in _NUMERICAL_VALIDATORS
    metrics = None
    if is_numerical:
        # Heuristic: pull any top-level numeric extras into a metrics block.
        metrics = {
            k: v for k, v in raw_dict.items()
            if isinstance(v, (int, float))
            and k not in {"status", "findings", "summary", "methodology"}
        }
        if not metrics:
            metrics = None

    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "validator": validator,
        "validator_type": "numerical" if is_numerical else "judgement",
        "verdict": normalize_verdict(parsed.status),
        "summary": parsed.summary,
        "methodology": parsed.methodology,
        "findings": findings_canonical,
        "metrics": metrics,
    }


# ===========================================================================
# VALIDATOR_CONFIG — single source of truth for the atomic validator set.
# applies_on lists domains; applies_when lists artefact predicates.
# system_hint is short — full body lives in the subagent's .md + skill.
# ===========================================================================

VALIDATOR_CONFIG: dict[str, dict] = {
    # Code-producing validators
    "code-reviewer":              {"model": "opus",   "applies_on": ["dev"]},
    "security-auditor":           {"model": "opus",   "applies_on": ["dev"],     "predicate": "auth_or_data_touched"},
    "reality-checker":            {"model": "opus",   "applies_on": ["dev", "marketing"]},
    "skeptic":                    {"model": "opus",   "applies_on": ["dev", "marketing"]},
    "anti-pattern-detector":      {"model": "sonnet", "applies_on": ["dev"],     "predicate": "has_git_diff"},
    "performance-validator":      {"model": "sonnet", "applies_on": ["dev"],     "predicate": "perf_relevant"},
    "migration-validator":        {"model": "sonnet", "applies_on": ["dev"],     "predicate": "migration_present"},
    "test-reviewer":              {"model": "sonnet", "applies_on": ["dev"],     "predicate": "tests_present"},
    # Spec validators (run before code-producing waves)
    "completeness-validator":     {"model": "sonnet", "applies_on": ["dev"],     "predicate": "spec_present"},
    "tech-spec-validator":        {"model": "haiku",  "applies_on": ["dev"],     "predicate": "tech_spec_present"},
    "task-validator":             {"model": "haiku",  "applies_on": ["dev"],     "predicate": "tasks_present"},
    "userspec-quality-validator": {"model": "sonnet", "applies_on": ["dev"],     "predicate": "user_spec_present"},
    "userspec-adequacy-validator":{"model": "opus",   "applies_on": ["dev"],     "predicate": "user_spec_present"},
    "feasibility-assessor":       {"model": "sonnet", "applies_on": ["dev"],     "predicate": "research_verdict_present"},
    "interview-completeness-checker": {"model": "sonnet", "applies_on": ["dev"], "predicate": "interview_completed"},
    # Infra validators
    "infrastructure-reviewer":    {"model": "haiku",  "applies_on": ["dev"],     "predicate": "infra_changes"},
    "deploy-reviewer":            {"model": "haiku",  "applies_on": ["dev"],     "predicate": "ci_cd_changes"},
    # Design validators
    "accessibility-validator":    {"model": "haiku",  "applies_on": ["design", "marketing"], "predicate": "ui_present"},
    # Meta validators (skills, docs, prompts) — applies_on: [] means "caller-explicit only",
    # never auto-selected by domain; predicate always returns False so --auto skips them.
    # Use --validators prompt-reviewer to invoke explicitly.
    "documentation-reviewer":     {"model": "haiku",  "applies_on": ["dev"],     "predicate": "docs_changes"},
    "prompt-reviewer":            {"model": "haiku",  "applies_on": [],          "predicate": "prompt_changes"},
    "skill-checker":              {"model": "haiku",  "applies_on": [],          "predicate": "skill_changes"},
    # Cross-domain coherence validator (Phase 3, Layer 5 embedding-fit check)
    "product-context-validator":  {"model": "sonnet", "applies_on": ["dev", "design", "marketing"], "predicate": "cross_domain_engaged"},
}


# ===========================================================================
# Plan node — read criteria.md + validation-pipeline rules, return validators.
# Predicates are simple artefact-existence / frontmatter checks. The point is
# to skip validators that have nothing to look at — saves Haiku-level cost
# but more importantly avoids "not_applicable" noise in validation-log.
# ===========================================================================

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _read_criteria_frontmatter(eng: Path) -> dict:
    crit = eng / "criteria.md"
    if not crit.exists():
        return {}
    text = crit.read_text(encoding="utf-8", errors="ignore")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"\'')
    return fm


def _predicate_check(predicate: str, eng: Path, criteria_fm: dict) -> bool:
    """Return True if predicate is satisfied (validator should run)."""
    if predicate == "auth_or_data_touched":
        return True  # conservative — let security-auditor self-judge
    if predicate == "has_git_diff":
        # Lead must produce engagement/handoff.md with §1 Diff before validators run.
        ho = eng / "handoff.md"
        return ho.exists() and "Diff summary" in ho.read_text(encoding="utf-8", errors="ignore")
    if predicate == "perf_relevant":
        return any((eng / "executor-reports").glob("*.md")) if (eng / "executor-reports").exists() else True
    if predicate == "migration_present":
        return any(eng.rglob("*migration*")) or any(eng.rglob("*alembic*"))
    if predicate == "tests_present":
        return True  # conservative
    if predicate == "spec_present":
        return (eng / "specs").exists() and any((eng / "specs").glob("*.md"))
    if predicate == "tech_spec_present":
        return (eng / "specs" / "tech-spec.md").exists()
    if predicate == "tasks_present":
        return (eng / "tasks").exists() and any((eng / "tasks").glob("*.md"))
    if predicate == "user_spec_present":
        return (eng / "specs" / "user-spec.md").exists()
    if predicate == "research_verdict_present":
        return (eng / "specs" / "research-verdict.md").exists()
    if predicate == "interview_completed":
        return (eng / "specs" / "user-spec.md").exists()
    if predicate == "infra_changes":
        return True  # conservative
    if predicate == "ci_cd_changes":
        return True
    if predicate == "ui_present":
        return (eng / "ui").exists() or (eng / "screens").exists()
    if predicate == "docs_changes":
        return (eng / "docs-diff.md").exists()
    if predicate == "prompt_changes":
        return False  # specialized — caller asks explicitly
    if predicate == "skill_changes":
        return False  # specialized
    if predicate == "cross_domain_engaged":
        # product-context-validator runs only when criteria.md or plan.md indicate
        # cross-domain work (multiple domains contributing artefacts).
        # Heuristic: look for cross_domain frontmatter field OR secondary engagement
        # reference in plan.md.
        if criteria_fm.get("cross_domain", "").lower() in {"true", "1", "yes"}:
            return True
        plan = eng / "plan.md"
        if plan.exists():
            text = plan.read_text(encoding="utf-8", errors="ignore").lower()
            if "cross-domain" in text or "engagement-secondary" in text:
                return True
        return False
    return True


def _select_validators(domain: str, eng: Path, criteria_fm: dict) -> list[str]:
    """Default validator selection per domain + predicates."""
    selected = []
    for name, cfg in VALIDATOR_CONFIG.items():
        applies_on = cfg.get("applies_on", [])
        if applies_on and domain not in applies_on:
            continue
        predicate = cfg.get("predicate")
        if predicate and not _predicate_check(predicate, eng, criteria_fm):
            continue
        selected.append(name)
    return selected


# ===========================================================================
# State
# ===========================================================================


class ValidatorState(TypedDict, total=False):
    engagement: str
    iter_n: int
    validators: list[str]
    domain: str
    invoker_mode: str
    resume: bool
    skipped_done_validators: list[str]
    # Per-validator Send payload:
    validator: str
    retry_n: int
    # Reducer — every validator-node appends here.
    results: Annotated[list[dict], operator.add]
    # Opt-in native HITL pause on critical findings.
    # Tier read from criteria.md (S|M|L). interrupt_enabled set by CLI flag.
    # Pause only fires when interrupt_enabled AND tier∈{M,L} AND any result
    # carries severity=critical finding. Default behaviour (flag absent) is
    # unchanged: critical_check is a no-op pass-through.
    tier: str
    interrupt_enabled: bool
    # Captured human directive once resumed (from Command(resume=...)).
    human_directive: dict
    human_directive_result: dict


# ===========================================================================
# Invokers — three modes, mirror adversary_lg.py:
#   subprocess  default — `claude -p --agent <name>` rides existing subscription
#   api         opt-in  — LangChain ChatAnthropic per validator, needs API key
#   mock        testing — canned output, no LLM calls
# ===========================================================================


class Invoker:
    name = "base"
    def invoke_validator(self, validator: str, eng: Path) -> dict:
        raise NotImplementedError


class SubprocessInvoker(Invoker):
    name = "subprocess"

    def __init__(self):
        self.claude = _find_claude_cmd()
        if not self.claude:
            raise RuntimeError("claude CLI not found in PATH")

    def invoke_validator(self, validator: str, eng: Path) -> dict:
        # Dispatch the validator subagent on the engagement directory.
        # The subagent reads engagement/ on its own — we just pass the path
        # and ask for JSON output.
        prompt = (
            f"Run validator '{validator}' on engagement at {eng}. "
            f"Output JSON only to stdout matching the validator's standard schema. "
            f"No prose, no markdown fences."
        )
        try:
            r = subprocess.run(
                [self.claude, "-p", "--agent", validator, prompt],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600,
            )
            stdout = (r.stdout or "").strip()
            if r.returncode != 0:
                return {"status": "error", "raw_stderr": (r.stderr or "")[:500],
                        "rc": r.returncode}
            return _extract_json(stdout) or {"status": "error", "raw_stdout": stdout[:500]}
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "subagent timed out (600s)"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ApiInvoker(Invoker):
    """Opt-in. Uses LangChain ChatAnthropic directly — needs ANTHROPIC_API_KEY,
    a separate billing surface from the subscription the subprocess invoker
    rides. Imports are lazy so a missing langchain-anthropic does not break
    subprocess mode.

    Reads validator's agent .md to extract the system prompt (everything
    after the frontmatter --- block). The model field from frontmatter is
    respected; falls back to VALIDATOR_CONFIG's `model` if no agent file.

    Output format: validator's prompt requests JSON-only stdout matching its
    standard schema. We parse via _extract_json (same as subprocess invoker).

    Limitations vs subprocess invoker:
      - No access to project files via Read/Glob/Grep tools (api invoker is
        text-only). Use only for validators that can judge from the engagement/
        directory state passed via prompt, NOT for validators that need to
        grep the codebase. In practice: subprocess invoker is correct for
        production; api invoker is for batch testing / reproducible benchmarks
        where speed-vs-cost trade-off favours API.
    """
    name = "api"

    def __init__(self):
        self._llm_cache: dict = {}
        self._agents_dir = Path.home() / ".claude" / "agents"

    def _get_llm(self, model: str):
        if model not in self._llm_cache:
            from langchain_anthropic import ChatAnthropic
            self._llm_cache[model] = ChatAnthropic(model=model, max_tokens=8000)
        return self._llm_cache[model]

    def _read_agent_prompt(self, validator: str) -> tuple[str, str]:
        """Returns (model, system_prompt_body) from agent .md file.
        Falls back to VALIDATOR_CONFIG model if frontmatter missing."""
        agent_file = self._agents_dir / f"{validator}.md"
        config_model = VALIDATOR_CONFIG.get(validator, {}).get("model", "claude-sonnet-4-5")
        # Map config short names to full Anthropic model ids.
        model_map = {
            "haiku": "claude-haiku-4-5",
            "sonnet": "claude-sonnet-4-5",
            "opus": "claude-opus-4-5",
        }
        model = model_map.get(config_model, config_model)
        if not agent_file.exists():
            return model, f"Run validator '{validator}'. Output JSON only."
        text = agent_file.read_text(encoding="utf-8", errors="ignore")
        # Strip frontmatter.
        if text.startswith("---"):
            end = text.find("\n---", 4)
            if end != -1:
                body = text[end + 4:].lstrip("\n")
                return model, body
        return model, text

    def invoke_validator(self, validator: str, eng: Path) -> dict:
        try:
            model, system_body = self._read_agent_prompt(validator)
            llm = self._get_llm(model)
            user_prompt = (
                f"Engagement directory: {eng}\n\n"
                f"Run the validator described in your system prompt against this "
                f"engagement. Output JSON only to stdout matching your standard "
                f"output schema. No prose, no markdown fences."
            )
            full_prompt = system_body + "\n\n---\n\n" + user_prompt
            resp = llm.invoke(full_prompt)
            content = resp.content if isinstance(resp.content, str) else json.dumps(resp.content)
            return _extract_json(content) or {"status": "error", "raw_response": content[:500]}
        except Exception as e:
            return {"status": "error", "error": f"api invoker error: {type(e).__name__}: {e}"}


class MockInvoker(Invoker):
    name = "mock"

    def __init__(self):
        self.fail_set = set((os.environ.get("VALIDATOR_MOCK_FAIL", "")).split(","))
        self.sleep = float(os.environ.get("VALIDATOR_MOCK_SLEEP", "0.05"))

    def invoke_validator(self, validator: str, eng: Path) -> dict:
        time.sleep(self.sleep)
        if validator in self.fail_set:
            return {"status": "error", "error": "mocked failure"}
        return {
            "status": "satisfied",
            "findings": [],
            "summary": f"mock {validator}: OK",
            "methodology": "MOCK",
        }


def make_invoker(mode: str) -> Invoker:
    if mode == "subprocess":
        return SubprocessInvoker()
    if mode == "api":
        return ApiInvoker()
    if mode == "mock":
        return MockInvoker()
    raise ValueError(f"unknown invoker mode: {mode}")


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from validator stdout."""
    text = text.strip()
    if not text:
        return None
    # Strip markdown fence if present.
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find first { ... last matching }.
    first = text.find("{")
    if first == -1:
        return None
    depth = 0
    for i in range(first, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[first:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ===========================================================================
# Nodes
# ===========================================================================


def _find_completed_validators(eng: Path, iter_n: int, candidates: list[str]) -> set[str]:
    """Scan validation-outputs/ for already-completed validators in this iter.
    A validator is 'completed' if there's a parseable JSON file with a valid
    status field. Used for --resume: skip these on re-run.
    """
    out_dir = eng / "validation-outputs"
    if not out_dir.exists():
        return set()
    completed: set[str] = set()
    for v in candidates:
        # Find any {validator}-iter-{N}-*.json (excluding -preliminary- variants)
        for p in out_dir.glob(f"{v}-iter-{iter_n}-*.json"):
            if "-preliminary-" in p.name:
                continue
            try:
                payload = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                ValidatorOutput.model_validate(payload)
                completed.add(v)
                break
            except Exception:
                # Corrupt file — let the retry edge treat it as missing.
                pass
    return completed


def _plan_node(state: ValidatorState) -> dict:
    """Decide which validators to run. If state.validators is explicit, use it.
    Otherwise auto-select per domain + predicates.

    On --resume, validators that already have a valid final output for this
    engagement+iter are skipped — re-run only the missing AND the failed ones.
    """
    eng = Path(state["engagement"])
    explicit = state.get("validators")
    domain = state.get("domain", "")
    fm = _read_criteria_frontmatter(eng)
    if not domain:
        domain = fm.get("domain", "dev")

    if explicit:
        candidates = [v for v in explicit if v in VALIDATOR_CONFIG]
    else:
        candidates = _select_validators(domain, eng, fm)

    skipped_done: list[str] = []
    if state.get("resume"):
        iter_n = state["iter_n"]
        done = _find_completed_validators(eng, iter_n, candidates)
        skipped_done = sorted(done)
        candidates = [v for v in candidates if v not in done]

    # propagate tier from criteria.md frontmatter into state so the
    # critical_check node can gate interrupt on M/L only.
    tier_raw = str(fm.get("size", "")).strip().upper()
    tier = tier_raw if tier_raw in {"S", "M", "L"} else "S"

    _ledger_emit(
        "phase_started",
        node="phase:validation_plan",
        payload={
            "domain": domain,
            "candidates": candidates,
            "skipped_already_done": skipped_done,
            "tier": tier,
        },
    )
    return {
        "validators": candidates,
        "domain": domain,
        "skipped_done_validators": skipped_done,
        "tier": tier,
    }


def _route_after_plan(state: ValidatorState):
    """Fan out — one Send per validator. If none selected, go straight to finalize."""
    validators = state.get("validators", [])
    if not validators:
        return "finalize"
    eng = state["engagement"]
    iter_n = state["iter_n"]
    return [
        Send("run_validator", {
            "engagement": eng,
            "iter_n": iter_n,
            "validator": v,
            "retry_n": 0,
            "domain": state.get("domain", ""),
            "invoker_mode": state.get("invoker_mode", "subprocess"),
        })
        for v in validators
    ]


def _ensure_outputs_dir(eng: Path) -> Path:
    out = eng / "validation-outputs"
    out.mkdir(exist_ok=True)
    return out


def _write_output(eng: Path, validator: str, iter_n: int, payload: dict) -> Path:
    out = _ensure_outputs_dir(eng)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = out / f"{validator}-iter-{iter_n}-{ts}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _make_run_validator_node(invoker_cache: dict):
    """Run one validator. Validates output via Pydantic; on failure, returns
    {status: error}. Retry logic lives in _route_after_validator."""
    def run_validator(state: ValidatorState) -> dict:
        validator = state["validator"]
        eng = Path(state["engagement"])
        iter_n = state["iter_n"]
        retry_n = state.get("retry_n", 0)
        mode = state.get("invoker_mode", "subprocess")
        # Cache invokers per mode (one Subprocess per process).
        if mode not in invoker_cache:
            invoker_cache[mode] = make_invoker(mode)
        invoker = invoker_cache[mode]

        _ledger_emit(
            "validator_started",
            node="run_validator",
            actor=validator,
            payload={"validator": validator, "retry_n": retry_n, "mode": mode},
        )

        t0 = time.time()
        raw = invoker.invoke_validator(validator, eng)
        elapsed = round(time.time() - t0, 2)

        # Try to coerce through Pydantic.
        try:
            parsed = ValidatorOutput.model_validate(raw)
            # Canonical envelope — also build canonical envelope; written alongside raw so
            # consumers can pick either shape without re-parsing.
            canonical = canonicalize_validator_output(validator, parsed)
            raw_dump = parsed.model_dump()
            on_disk_payload = {**raw_dump, "canonical": canonical}
            crit_findings = sum(
                1 for f in canonical.get("findings", [])
                if f.get("severity") == "critical"
            )
            result = {
                "validator": validator,
                "status": "ok",
                "verdict": parsed.status,
                "canonical_verdict": canonical["verdict"],
                "findings_count": len(parsed.findings),
                "critical_count": crit_findings,
                "retry_n": retry_n,
                "elapsed_s": elapsed,
                "payload": on_disk_payload,
            }
            # Write to validation-outputs/ — this is what consilium-synth and
            # handoff-precheck consume. Raw fields preserved; canonical added.
            path = _write_output(eng, validator, iter_n, on_disk_payload)
            result["output_path"] = str(path)
            _ledger_emit(
                "validator_completed",
                node="run_validator",
                actor=validator,
                payload={
                    "validator": validator,
                    "verdict": parsed.status,
                    "canonical_verdict": canonical["verdict"],
                    "findings_count": len(parsed.findings),
                    "critical_count": crit_findings,
                    "retry_n": retry_n,
                    "elapsed_s": elapsed,
                    "output_path": str(path),
                },
                output_schema_version=CANONICAL_SCHEMA_VERSION,
                verdict="ACCEPT" if canonical["verdict"] == "approved" else
                        ("REJECT" if canonical["verdict"] == "changes_required" else "N/A"),
            )
        except Exception as e:
            result = {
                "validator": validator,
                "status": "fail",
                "retry_n": retry_n,
                "elapsed_s": elapsed,
                "error": f"validation failed: {type(e).__name__}: {str(e)[:200]}",
                "raw": str(raw)[:300],
            }
            _ledger_emit(
                "validator_failed" if retry_n >= 1 else "validator_retried",
                node="run_validator",
                actor=validator,
                payload={
                    "validator": validator,
                    "retry_n": retry_n,
                    "elapsed_s": elapsed,
                    "error": str(e)[:200],
                },
            )
        return {"results": [result]}
    return run_validator


def _route_after_validator(state: ValidatorState):
    """Retry once on parse-failure. Absorbs validator-retry.py's logic —
    quarantine bad output and re-dispatch. Max retries = 1 per validator.

    IMPORTANT: state["results"] is a reducer that contains results from ALL
    parallel fan-out branches in arbitrary merge order. We must look up the
    result for THIS branch's validator specifically (state["validator"]), not
    blindly take results[-1] (which under concurrent fan-out can belong to a
    different branch and trigger spurious retries on the wrong validator).
    """
    results = state.get("results", [])
    current_validator = state.get("validator")
    if not results or not current_validator:
        return "barrier"
    # Find the latest result for the current validator (reverse-search by name).
    my_result = next(
        (r for r in reversed(results) if r.get("validator") == current_validator),
        None,
    )
    if my_result is None:
        return "barrier"
    if my_result.get("status") == "fail" and my_result.get("retry_n", 0) < 1:
        return [Send("run_validator", {
            "engagement": state["engagement"],
            "iter_n": state["iter_n"],
            "validator": current_validator,
            "retry_n": my_result.get("retry_n", 0) + 1,
            "domain": state.get("domain", ""),
            "invoker_mode": state.get("invoker_mode", "subprocess"),
        })]
    return "barrier"


def _barrier_node(state: ValidatorState) -> dict:
    """Sync barrier after fan-out. No-op; presence forces all parallel branches
    to complete before finalize."""
    results = state.get("results", [])
    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = sum(1 for r in results if r.get("status") == "fail")
    _ledger_emit(
        "barrier_passed",
        node="barrier",
        payload={"ok": ok, "fail": fail, "total": len(results)},
    )
    return {}


def _has_critical_finding(results: list[dict]) -> list[dict]:
    """Return the list of {validator, finding} pairs that carry a critical
    finding. With canonical envelope present we read the normalized
    `canonical.findings[*].severity` — exactly "critical". Falls back to
    raw `findings[*].severity` with synonym set (crit/blocker/severe) for
    on-disk payloads predating canonicalization (e.g., crash-recovery)."""
    legacy_crit_terms = {"critical", "crit", "blocker", "blocking", "severe"}
    hits: list[dict] = []
    for r in results:
        if r.get("status") != "ok":
            continue
        payload = r.get("payload") or {}
        canonical = payload.get("canonical") or {}
        # Preferred: canonical findings (severity is already normalized).
        c_findings = canonical.get("findings") or []
        if c_findings:
            for f in c_findings:
                if (f or {}).get("severity") == "critical":
                    hits.append({"validator": r.get("validator"), "finding": f})
            continue
        # Fallback: raw findings with synonym set (pre-canonical outputs).
        for f in payload.get("findings") or []:
            sev = str((f or {}).get("severity") or "").strip().lower()
            if sev in legacy_crit_terms:
                hits.append({"validator": r.get("validator"), "finding": f})
    return hits


def _critical_check_node(state: ValidatorState) -> dict:
    """pause graph for human directive on critical findings.

    Fires only when ALL of:
      - --interrupt-on-critical was passed (state.interrupt_enabled = True),
      - tier ∈ {M, L} (S-tier is single-iteration; no pause makes sense),
      - at least one validator result carries a finding with severity=critical.

    Otherwise no-op pass-through to finalize. This preserves default behaviour:
    callers without the flag see exactly the pre-Move-4b graph semantics.

    Pattern mirrors adversary_lg.py's _interrupt_apply_directive_node:
    interrupt() with a structured payload, resume via Command(resume={...}),
    delegate canonical human-directive.md write to human-directive.py.
    """
    if not state.get("interrupt_enabled"):
        return {}
    tier = state.get("tier", "")
    if tier not in {"M", "L"}:
        # Silent skip on S-tier — the CLI surfaces the rule; runtime is
        # defense-in-depth in case interrupt_enabled is set programmatically.
        return {}

    results = state.get("results", [])
    crit_hits = _has_critical_finding(results)
    if not crit_hits:
        return {}

    # Build a concise summary for the human (printed in interrupt payload + on stderr).
    summary_lines = [
        f"CRITICAL findings detected by validator_lg.py — iter {state.get('iter_n')}.",
        f"engagement: {state.get('engagement')}  tier: {tier}",
        f"validators flagged: {sorted({h['validator'] for h in crit_hits})}",
        "",
        "Top findings (validator → severity → message):",
    ]
    for h in crit_hits[:10]:
        f = h.get("finding") or {}
        msg = (str(f.get("message") or f.get("issue") or f.get("description") or ""))[:160]
        summary_lines.append(f"  - {h['validator']}: critical — {msg}")
    summary = "\n".join(summary_lines)
    print(summary, file=sys.stderr, flush=True)

    _ledger_emit(
        "critical_check_paused",
        node="critical_check",
        interrupt_state="paused",
        payload={
            "critical_count": len(crit_hits),
            "validators": sorted({h["validator"] for h in crit_hits}),
            "tier": tier,
        },
    )

    directive = interrupt({
        "phase": "critical_findings_pause",
        "engagement": state["engagement"],
        "iter_n": state["iter_n"],
        "tier": tier,
        "critical_count": len(crit_hits),
        "validators": sorted({h["validator"] for h in crit_hits}),
        "options": ["PROCEED", "REJECT", "DIRECTED"],
        "resume_help": (
            "Resume with: python validator_lg.py <eng> --resume-interrupt "
            "<thread_id> --decision PROCEED|REJECT|DIRECTED [--note ...]"
        ),
        "summary": summary,
    })

    # The interrupt() above raises GraphInterrupt and pauses the graph.
    # Execution only reaches this point after Command(resume=...) replays.
    _ledger_emit(
        "critical_check_resumed",
        node="critical_check",
        interrupt_state="resumed",
        payload={"decision": (directive or {}).get("decision") if isinstance(directive, dict) else None},
    )

    if not isinstance(directive, dict) or "decision" not in directive:
        return {"human_directive_result": {
            "status": "fail",
            "error": f"resume payload missing 'decision' key: got {type(directive).__name__}",
        }}

    decision = str(directive.get("decision") or "").upper()
    if decision not in {"PROCEED", "REJECT", "DIRECTED"}:
        return {"human_directive_result": {
            "status": "fail",
            "error": f"invalid decision '{decision}', expected PROCEED|REJECT|DIRECTED",
        }}

    # Write canonical human-directive.md via human-directive.py (same path
    # adversary_lg.py uses, so the two writers stay byte-compatible).
    eng = Path(state["engagement"])
    hd_script = Path(__file__).resolve().parent / "human-directive.py"
    if not hd_script.exists():
        return {
            "human_directive": directive,
            "human_directive_result": {
                "status": "fail",
                "error": f"human-directive.py not found at {hd_script}",
            },
        }
    cmd = [sys.executable, str(hd_script), str(eng), "--decision", decision]
    if directive.get("note"):
        cmd += ["--note", str(directive["note"])]
    if directive.get("reasons"):
        cmd += ["--reasons", str(directive["reasons"])]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            return {
                "human_directive": directive,
                "human_directive_result": {
                    "status": "ok",
                    "decision": decision,
                    "directive_path": str(eng / "human-directive.md"),
                },
            }
        return {
            "human_directive": directive,
            "human_directive_result": {
                "status": "fail",
                "rc": r.returncode,
                "error": (r.stderr or "")[:200],
            },
        }
    except subprocess.TimeoutExpired:
        return {
            "human_directive": directive,
            "human_directive_result": {
                "status": "fail",
                "error": "human-directive.py timed out after 30s",
            },
        }
    except Exception as e:
        return {
            "human_directive": directive,
            "human_directive_result": {"status": "fail", "error": str(e)},
        }


def _finalize_node(state: ValidatorState) -> dict:
    """Write/append validation-log.md with all results."""
    eng = Path(state["engagement"])
    iter_n = state["iter_n"]
    results = state.get("results", [])
    log_path = eng / "validation-log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n## Validator-lg run — iter {iter_n} — {ts}\n"]
    for r in results:
        v = r.get("validator", "?")
        if r.get("status") == "ok":
            lines.append(
                f"- **{v}** — verdict={r.get('verdict')}, findings={r.get('findings_count')}, "
                f"retry={r.get('retry_n')}, elapsed={r.get('elapsed_s')}s "
                f"→ `{r.get('output_path')}`"
            )
        else:
            lines.append(
                f"- **{v}** — FAILED after retry={r.get('retry_n')}: {r.get('error', '?')}"
            )
    # Append (don't overwrite).
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = sum(1 for r in results if r.get("status") == "fail")
    _ledger_emit(
        "phase_completed",
        node="phase:validation_finalize",
        payload={
            "iter_n": iter_n,
            "ok": ok,
            "fail": fail,
            "total": len(results),
            "log_path": str(log_path),
        },
        verdict="ACCEPT" if fail == 0 else "REJECT",
    )
    return {}


# ===========================================================================
# Graph
# ===========================================================================


def build_graph(invoker_cache: Optional[dict] = None, checkpointer=None):
    if invoker_cache is None:
        invoker_cache = {}
    run_validator_node = _make_run_validator_node(invoker_cache)

    builder = StateGraph(ValidatorState)
    builder.add_node("plan", _plan_node)
    builder.add_node("run_validator", run_validator_node)
    builder.add_node("barrier", _barrier_node)
    builder.add_node("critical_check", _critical_check_node)
    builder.add_node("finalize", _finalize_node)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan", _route_after_plan, ["run_validator", "finalize"],
    )
    builder.add_conditional_edges(
        "run_validator", _route_after_validator, ["run_validator", "barrier"],
    )
    # barrier → critical_check → finalize. critical_check is a no-op
    # pass-through when interrupt_enabled is False (default), preserving
    # pre-Move-4b graph semantics for all callers without the flag.
    builder.add_edge("barrier", "critical_check")
    builder.add_edge("critical_check", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


# ===========================================================================
# Checkpointer (shared SQLite DB pattern — separate file from adversary's)
# ===========================================================================

CHECKPOINT_DB = Path(__file__).resolve().parent / ".validator-lg-checkpoints.sqlite"


def make_checkpointer() -> SqliteSaver:
    # check_same_thread=False: LangGraph runs fan-out branches in worker threads.
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    return SqliteSaver(conn)


def thread_id_for(eng: Path, iter_n: int) -> str:
    """Stable thread_id per engagement+iter for the checkpointer."""
    import hashlib
    h = hashlib.sha1(str(eng).encode("utf-8")).hexdigest()[:12]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{h}-iter-{iter_n}-validator-{ts}"


# ===========================================================================
# LangSmith observability hook (mirror adversary_lg.py)
# ===========================================================================


def setup_langsmith() -> str:
    """LangSmith tracing is auto-instrumented by LangGraph when env vars are
    set — this helper detects state and prints a one-line status to stderr
    so the operator can see whether tracing is on.

    Enable with:  LANGSMITH_TRACING=true  +  LANGSMITH_API_KEY=<key>
    Optional:     LANGSMITH_PROJECT=<name>   (defaults to "validator-lg")
    """
    on = (os.environ.get("LANGSMITH_TRACING", "").lower() in {"true", "1"}
          or os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in {"true", "1"})
    if not on:
        return ("LangSmith tracing: OFF  (enable: LANGSMITH_TRACING=true + "
                "LANGSMITH_API_KEY=<key>)")
    if not os.environ.get("LANGSMITH_PROJECT") and not os.environ.get("LANGCHAIN_PROJECT"):
        os.environ["LANGSMITH_PROJECT"] = "validator-lg"
    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT")
    has_key = bool(os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY"))
    if not has_key:
        return (f"LangSmith tracing: ON but LANGSMITH_API_KEY missing — traces will "
                f"NOT upload (project={project})")
    return f"LangSmith tracing: ON  (project={project})"


# ===========================================================================
# Billing note
# ===========================================================================

BILLING_NOTE = """\
Validator invoker billing model

--invoker subprocess  (default — recommended for production)
    Each validator runs as `claude -p --agent <name>` subprocess. This rides
    your existing Claude Code / Anthropic subscription — no separate billing.
    Pre-launches 1 claude process per Send branch (the parallel fan-out cap).
    Validators have full access to engagement files via the subagent's
    Read/Glob/Grep tools.

--invoker mock  (recommended for unit + smoke tests)
    No LLM calls at all. Returns canned satisfied output (or simulated
    failure when VALIDATOR_MOCK_FAIL=name1,name2 is set). Costs nothing.

--invoker api  (opt-in — batch testing / reproducible benchmarks)
    Direct LangChain ChatAnthropic per validator. Needs ANTHROPIC_API_KEY
    env var. Separate billing surface from subscription.

    Reads each validator's agent .md to extract system prompt body
    (everything after the frontmatter block). Respects the `model:` field.

    LIMITATION: api invoker is text-only — no Read/Glob/Grep tools available
    to the LLM. Use only for validators that can judge from engagement/
    directory state passed via prompt, NOT for validators that need to grep
    the broader codebase. In practice: subprocess invoker is correct for
    production; api invoker is for reproducible bench runs where the
    speed-vs-cost trade-off favours API.
"""


# ===========================================================================
# Iteration counter helper
# ===========================================================================


def _read_iter_counter(eng: Path) -> int:
    p = eng / "iteration"
    if p.exists():
        try:
            return int(p.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


# ===========================================================================
# CLI
# ===========================================================================


def _resume_interrupt_main(args) -> int:
    """resume a validator_lg graph paused at critical_check via
    Command(resume={...}). The graph picks up at _critical_check_node,
    validates the directive, invokes human-directive.py, then proceeds to
    finalize.
    """
    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    if not args.resume_interrupt:
        print("ERROR: --resume-interrupt requires THREAD_ID", file=sys.stderr)
        return 2

    # Interrupt requires the checkpointer (a pause has no meaning without it).
    checkpointer = make_checkpointer()
    try:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": args.resume_interrupt}}

        directive_payload = {"decision": args.decision}
        if args.reasons:
            directive_payload["reasons"] = args.reasons
        if args.note:
            directive_payload["note"] = args.note

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

    hdr = final_state.get("human_directive_result") or {}
    if args.json:
        print(json.dumps({
            "status": hdr.get("status"),
            "thread_id": args.resume_interrupt,
            "decision": args.decision,
            "directive_path": hdr.get("directive_path"),
            "error": hdr.get("error"),
        }, ensure_ascii=False, indent=2))
    else:
        if hdr.get("status") == "ok":
            print(f"Resumed. Decision={args.decision}. "
                  f"Wrote: {hdr.get('directive_path')}")
        else:
            print(f"Resume FAILED: {hdr.get('error', '?')}", file=sys.stderr)
            return 1
    return 0 if hdr.get("status") == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LangGraph validator orchestrator — first release",
    )
    parser.add_argument("engagement", nargs="?", help="Path to engagement/ directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--validators", type=str,
                       help="Comma-separated list of validators to run "
                            "(e.g. code-reviewer,security-auditor)")
    group.add_argument("--auto", action="store_true",
                       help="Auto-select validators from criteria.md domain + "
                            "validation-pipeline predicates")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    parser.add_argument("--invoker", choices=["subprocess", "api", "mock"], default="subprocess",
                        help="Validator invocation backend (default: subprocess — see --help-billing)")
    parser.add_argument("--domain", choices=["dev", "design", "marketing"],
                        help="Override domain (default: read from criteria.md frontmatter)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip validators that already have a valid final output "
                             "for this engagement+iter, re-run the rest (missing + failed). "
                             "Artefact-driven; works with or without the checkpointer.")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Run without the SQLite checkpointer (disables LangGraph-native "
                             "state introspection / LangSmith). --resume still works.")
    parser.add_argument("--json", action="store_true",
                        help="Print results as JSON to stdout")
    parser.add_argument("--help-billing", action="store_true",
                        help="Explain the --invoker billing model and exit.")
    # Opt-in native HITL pause on critical findings.
    parser.add_argument("--interrupt-on-critical", action="store_true",
                        help="On M/L tier, pause graph via interrupt() when any "
                             "validator returns severity=critical finding. "
                             "Silently ignored on tier=S. Default off.")
    parser.add_argument("--resume-interrupt", type=str, metavar="THREAD_ID",
                        help="Resume a paused graph by thread_id. Requires "
                             "--decision; optional --note / --reasons.")
    parser.add_argument("--decision", choices=["PROCEED", "REJECT", "DIRECTED"],
                        help="Human directive for --resume-interrupt.")
    parser.add_argument("--note", type=str, default=None,
                        help="Optional note attached to --decision for "
                             "human-directive.md.")
    parser.add_argument("--reasons", type=str, default=None,
                        help="Optional reasons string for --decision (passed "
                             "through to human-directive.py).")
    args = parser.parse_args()

    if args.help_billing:
        print(BILLING_NOTE)
        return 0

    # Resume mode short-circuits — we only resume an interrupted graph; no
    # new validator selection or fan-out happens here.
    if args.resume_interrupt:
        if not args.engagement:
            parser.error("engagement path is required for --resume-interrupt")
        if not args.decision:
            parser.error("--resume-interrupt requires --decision PROCEED|REJECT|DIRECTED")
        return _resume_interrupt_main(args)

    if not args.engagement:
        parser.error("engagement path is required (unless --help-billing)")
    if not args.validators and not args.auto:
        parser.error("one of --validators or --auto is required")
    if args.decision and not args.resume_interrupt:
        parser.error("--decision only meaningful with --resume-interrupt")

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    iter_n = args.iter if args.iter is not None else _read_iter_counter(eng)

    validators = None
    if args.validators:
        validators = [v.strip() for v in args.validators.split(",") if v.strip()]
        invalid = [v for v in validators if v not in VALIDATOR_CONFIG]
        if invalid:
            print(f"ERROR: unknown validators: {invalid}. "
                  f"Known: {sorted(VALIDATOR_CONFIG.keys())}", file=sys.stderr)
            return 2

    # LangSmith status — same pattern as adversary_lg.py. To stderr so --json
    # stdout stays clean.
    print(setup_langsmith(), file=sys.stderr)

    # Initialize event ledger (no-op when lib.ledger import failed).
    # Tier is best-effort read of criteria.md frontmatter; final value
    # propagates through state via _plan_node.
    global _RUN_LEDGER
    if _LEDGER_AVAILABLE:
        try:
            tier_for_ledger = None
            try:
                fm = _read_criteria_frontmatter(eng)
                t = str(fm.get("size", "")).strip().upper()
                if t in {"S", "M", "L"}:
                    tier_for_ledger = t
            except Exception:
                pass
            _RUN_LEDGER = EventLedger(
                eng, agent="validator-lg", tier=tier_for_ledger,
            )
            _RUN_LEDGER.emit(
                "engagement_started",
                node="validator_lg:main",
                payload={
                    "iter_n": iter_n,
                    "invoker_mode": args.invoker,
                    "resume": args.resume,
                    "interrupt_on_critical": bool(args.interrupt_on_critical),
                    "is_resume_interrupt": False,
                },
            )
        except Exception as e:
            print(f"WARN: ledger init failed (continuing without ledger): {e}",
                  file=sys.stderr)
            _RUN_LEDGER = None

    init_state: ValidatorState = {
        "engagement": str(eng),
        "iter_n": iter_n,
        "invoker_mode": args.invoker,
        "resume": args.resume,
        "results": [],
        "interrupt_enabled": bool(args.interrupt_on_critical),
    }
    if validators:
        init_state["validators"] = validators
    if args.domain:
        init_state["domain"] = args.domain

    # interrupt requires a checkpointer; auto-promote even if user
    # passed --no-checkpoint together with --interrupt-on-critical (no pause
    # is possible without one).
    if args.interrupt_on_critical and args.no_checkpoint:
        print("WARN: --interrupt-on-critical requires checkpointer; "
              "ignoring --no-checkpoint.", file=sys.stderr)
        args.no_checkpoint = False

    checkpointer = None if args.no_checkpoint else make_checkpointer()
    thread_id = thread_id_for(eng, iter_n)
    try:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            final_state = graph.invoke(init_state, config)
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

    # detect pause. graph.invoke returns the state at the point of
    # interrupt() with an `__interrupt__` key. We print the resume hint and
    # exit cleanly so caller can react (e.g. surface the pause to a human).
    if isinstance(final_state, dict) and final_state.get("__interrupt__"):
        interrupt_info = final_state.get("__interrupt__")
        # interrupt_info is a list of tuples per LangGraph contract; the
        # payload was the dict we passed to interrupt().
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
                f"python validator_lg.py {eng} --resume-interrupt {thread_id} "
                f"--decision PROCEED|REJECT|DIRECTED [--note ...]"
            ),
            "payload": payload,
        }
        if args.json:
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print(f"PAUSED at critical_check. thread_id={thread_id}",
                  file=sys.stderr)
            print(f"Resume with: {msg['resume_help']}", file=sys.stderr)
        return 0

    results = final_state.get("results", [])
    skipped_done = list(final_state.get("skipped_done_validators", []))

    if not results:
        if skipped_done:
            print(f"All {len(skipped_done)} validator(s) already complete for "
                  f"iter={iter_n}: {', '.join(skipped_done)}. Nothing to re-run.")
            return 0
        if args.auto:
            print("No validators selected (no predicates matched). Nothing to do.")
            return 0
        print("ERROR: no results produced.", file=sys.stderr)
        return 1

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    fail_count = sum(1 for r in results if r.get("status") == "fail")

    if args.json:
        print(json.dumps({
            "engagement": str(eng),
            "iter": iter_n,
            "invoker": args.invoker,
            "resumed": args.resume,
            "skipped_already_done": skipped_done,
            "ok": ok_count,
            "fail": fail_count,
            "results": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Validator-lg run for engagement {eng.name} iter={iter_n} "
              f"(invoker={args.invoker})")
        if skipped_done:
            print(f"  resumed — skipped (already complete): {', '.join(skipped_done)}")
        print(f"  ok={ok_count}  fail={fail_count}")
        print()
        for r in results:
            v = r.get("validator", "?")
            if r.get("status") == "ok":
                print(f"[OK  ] {v}  verdict={r.get('verdict')}  "
                      f"findings={r.get('findings_count')}  ({r.get('elapsed_s')}s)")
                print(f"        -> {r.get('output_path')}")
            else:
                print(f"[FAIL] {v}  retry={r.get('retry_n')}  {r.get('error', '?')}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
