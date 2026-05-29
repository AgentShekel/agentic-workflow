#!/usr/bin/env python3
"""LangGraph adversary bridge — drop-in replacement for adversary.py.

Same CLI surface, same output contract, same exit codes as adversary.py.
What changes is the internals: the consilium is a LangGraph StateGraph instead
of a hand-rolled ThreadPoolExecutor.

  - Send-based fan-out over reviewer roles (true parallel execution, handled
    by LangGraph's executor instead of a manual thread pool).
  - codex-informed depends on peer-opus via a conditional edge (was a manual
    two-phase split in adversary.py's run_consilium).
  - --resume is artefact-driven: the plan node scans validation-outputs/ and
    skips reviewer roles that already have a valid final output, re-running
    only the missing AND the failed ones. (L-tier consilium is ~$20-40 /
    10-20 min; losing it to one crashed OR failed reviewer was the pain point.)
    A SqliteSaver checkpointer is still wired — for LangGraph-native state
    introspection and LangSmith tracing — but --resume does not depend on it.
  - Pydantic schemas validate every reviewer output. Replaces the loose
    extract_json + normalize_payload coercion path.
  - Two-pass isolation is preserved exactly: each role node runs Pass 1 on a
    filesystem-curated copy (handoff hidden), then Pass 2 on the full
    engagement. Checkpoint/resume is per-role; additionally, on --resume a role
    whose Pass 1 already completed reuses its preliminary file instead of
    re-spending the Pass-1 LLM call — so a crashed Pass 2 costs only Pass 2.
  - Auto-synth: a multi-role consilium run automatically invokes
    consilium-synth.py at the end so consilium-summary.md is written in the
    same command (M/L acceptance is one atomic step). --no-synth opts out for
    callers that want to inspect outputs before synthesis.

Invoker modes (--invoker, default subprocess):
  subprocess  claude -p / codex exec   — rides existing subscriptions, no
                                          billing change. This is the default
                                          and the tested path.
  api         LangChain ChatAnthropic / ChatOpenAI — needs ANTHROPIC_API_KEY /
                                          OPENAI_API_KEY. Opt-in. See the
                                          billing note printed by --help-billing.
  mock        canned output, no LLM calls — for testing the graph skeleton.

Output files (identical to adversary.py — consilium-synth.py / handoff-precheck.py
consume these unchanged):
  engagement/validation-outputs/{role}-iter-{N}-preliminary-{ts}.json   (Pass 1)
  engagement/validation-outputs/{role}-iter-{N}-{ts}.json               (Pass 2 final)

Exit codes:
  0 — at least one role produced parseable output (or S-tier: nothing to do)
  1 — all roles failed
  2 — invocation error (bad args, missing engagement, missing tools, no venv)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# venv bootstrap — re-exec under the dedicated venv if langgraph is absent.
# Keeps the invocation identical to adversary.py: `python adversary_lg.py ...`.
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
        "adversary_lg.py needs langgraph/langchain. Create the venv:\n"
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
import hashlib
import json
import operator
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

# Append-only event ledger. Optional dependency: graceful no-op
# when lib.ledger import fails (so adversary_lg.py works on stripped installs).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lib.ledger import EventLedger  # noqa: E402
    _LEDGER_AVAILABLE = True
except Exception:
    EventLedger = None  # type: ignore
    _LEDGER_AVAILABLE = False

# Shared claude CLI resolver — single source of the Windows .CMD->.exe logic.
from lib.claude_path import find_claude_cmd  # noqa: E402

_RUN_LEDGER = None  # Optional[EventLedger]; set in main() per invocation.


def _ledger_emit(payload_type: str, **kwargs):
    """No-op when ledger unavailable / unset. Returns event_id on success."""
    if _RUN_LEDGER is None:
        return None
    try:
        return _RUN_LEDGER.emit(payload_type, **kwargs)
    except Exception as e:
        print(f"WARN: ledger emit failed ({payload_type}): {e}", file=sys.stderr)
        return None

# ===========================================================================
# Pydantic schemas — single source of truth for reviewer I/O.
# Replaces adversary.py's extract_json + normalize_payload loose coercion.
# Both subprocess mode (validate scraped stdout) and api mode (validate model
# response) run output through these.
# ===========================================================================

VALID_VERDICTS = {"satisfied", "rework_required", "suspicious_too_clean"}


class Finding(BaseModel):
    """One adversary finding. extra='allow' keeps any reviewer-added keys."""
    model_config = ConfigDict(extra="allow")
    severity: str = "minor"
    issue: str = ""
    evidence_path: str = ""
    fix_hint: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: Any) -> str:
        s = str(v).strip().lower()
        return s if s in {"critical", "major", "minor"} else "minor"


class Pass1Output(BaseModel):
    """Pass-1 preliminary view. No verdict yet (that is Pass 2)."""
    model_config = ConfigDict(extra="allow")
    preliminary_view: str = ""
    expected_deliverables: list[str] = Field(default_factory=list)
    observed_deliverables: list[str] = Field(default_factory=list)
    preliminary_findings: list[Finding] = Field(default_factory=list)
    reviewer_role: str = ""
    iteration: int = 0


class PreliminaryFindingsStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    confirmed: list[str] = Field(default_factory=list)
    resolved: list[str] = Field(default_factory=list)
    superseded: list[str] = Field(default_factory=list)


class Pass2Output(BaseModel):
    """Pass-2 final verdict. The verdict validator preserves adversary.py's
    defensive coercion: an unknown verdict becomes suspicious_too_clean rather
    than crashing the run."""
    model_config = ConfigDict(extra="allow")
    verdict: str = "suspicious_too_clean"
    reviewer_role: str = ""
    iteration: int = 0
    findings: list[Finding] = Field(default_factory=list)
    preliminary_findings_status: PreliminaryFindingsStatus = Field(
        default_factory=PreliminaryFindingsStatus
    )
    summary: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v: Any) -> str:
        s = str(v).strip().lower()
        return s if s in VALID_VERDICTS else "suspicious_too_clean"


# ===========================================================================
# Prompt templates — ported verbatim from adversary.py. These are tuned; do
# not edit content here. {{ }} are literal braces in the JSON schema examples.
# ===========================================================================

PROMPT_PASS1_PEER = """You are an adversarial reviewer in PASS 1 of a two-pass protocol.

CURATED engagement directory: {curated_path}

This is a curated copy of the real engagement. The following are PHYSICALLY ABSENT from this view:
- handoff.md (producer's claims and framing)
- acceptance-log.md (prior verdicts)
- consilium-summary.md (other reviewers' aggregations)
- human-directive.md (human's direction to director)
- validation-outputs/ (validator outputs and other adversaries' findings)

You DO have access to:
- {curated_path}/criteria.md (what was asked)
- {curated_path}/scope-sync.md (if present — scope clarifications, dangerous-op approvals)
- {curated_path}/plan.md (lead's plan, if present)
- {curated_path}/executor-reports/ (specialists' work logs)
- {curated_path}/screens/ + {curated_path}/traces/ (UX evidence, if ux_heavy)
- {curated_path}/specs/, tasks/, brand/, design-system/, ui/ (domain-specific)
- The actual codebase via Read/Grep (specialists' reports reference paths to src/)

DO NOT attempt to access the original engagement path or any path matching `*/handoff.md`,
`*/acceptance-log.md`, `*/consilium-summary.md`, `*/human-directive.md`,
`*/validation-outputs/*` — that defeats the protocol's contamination guard. If you accidentally
load such a file, stop and re-read criteria from the curated path.

YOUR TASK:
1. Read criteria.md as the original requester would.
2. Inspect executor-reports/ to see what specialists claim to have done.
3. Use Read/Grep to verify against actual codebase / artefacts.
4. Form your OWN preliminary view: what should exist, what you observe, gaps.

OUTPUT: Single JSON to stdout, nothing else. Schema:

{{
  "preliminary_view": "<1-3 lines summary of state as you see it>",
  "expected_deliverables": ["<list of what should exist per criteria>"],
  "observed_deliverables": ["<list of what you actually found>"],
  "preliminary_findings": [
    {{
      "severity": "critical"|"major"|"minor",
      "issue": "<1-line description>",
      "evidence_path": "<file:line or section reference>",
      "fix_hint": "<what should change>"
    }}
  ],
  "reviewer_role": "{role}",
  "iteration": {iter_n},
  "pass": 1
}}

Do NOT output a verdict yet — that comes in Pass 2 after reading producer's handoff.
"""

PROMPT_PASS2_PEER = """You are an adversarial reviewer in PASS 2 of a two-pass protocol.

In Pass 1 (working from a curated view that hid producer's handoff), you formed this preliminary opinion:

{preliminary_json}

NOW you have access to the FULL engagement at: {engagement}

YOUR TASK:
1. Read {engagement}/handoff.md (producer's claims and self-attestation).
2. Compare producer's claims against your Pass-1 preliminary findings.
3. For each preliminary finding, classify:
   - CONFIRMED: producer's handoff doesn't address it → still a finding
   - RESOLVED: producer's handoff actually addresses it (you missed evidence in Pass 1)
   - SUPERSEDED: producer's handoff reframes the issue in a way that changes severity
4. Identify NEW issues that only handoff content reveals:
   - Phantom paths (handoff cites paths that don't exist)
   - Fabricated quotes (handoff quotes things not in source)
   - Lazy execution: TODO/FIXME, placeholders, hidden-tab "fixes"
   - Format-only compliance (Goodhart): structural fields filled but content empty
   - Filler self-acceptance ("looks fine" is not a concern)
   - Architectural blind spots producer rationalized past

OUTPUT: Single JSON, schema:

{{
  "verdict": "satisfied" | "rework_required" | "suspicious_too_clean",
  "reviewer_role": "{role}",
  "iteration": {iter_n},
  "pass": 2,
  "preliminary_findings_status": {{
    "confirmed": ["<finding from preliminary that handoff did NOT address>"],
    "resolved": ["<finding from preliminary that handoff actually addressed>"],
    "superseded": ["<finding reframed by handoff>"]
  }},
  "findings": [
    {{"severity": "critical"|"major"|"minor", "issue": "...", "evidence_path": "...", "fix_hint": "..."}}
  ],
  "framing_contamination_signal": "<none | weak | strong: did handoff change your mind on something material?>",
  "summary": "<1 line overall verdict rationale>"
}}

Verdict guide:
- "rework_required" if any CONFIRMED critical/major finding survives, or major NEW finding emerged
- "satisfied" if all preliminary findings RESOLVED and only minor NEW issues
- "suspicious_too_clean" if preliminary was empty AND handoff revealed nothing — flag the suspicious cleanliness
"""

PROMPT_PASS2_CODEX_INFORMED = """You are an adversarial reviewer in PASS 2, INFORMED variant.

In Pass 1 (curated view, no handoff), you formed this preliminary opinion:

{preliminary_json}

Additionally, peer reviewer (Anthropic Opus) produced findings on the same engagement:

{peer_findings}

NOW you have access to the FULL engagement at: {engagement}

YOUR TASK:
1. Read {engagement}/handoff.md.
2. Update your preliminary findings (CONFIRMED / RESOLVED / SUPERSEDED) per Pass-1 vs handoff.
3. Compare to peer findings — do NOT duplicate peer findings; focus on COMPLEMENT.
4. Hunt for cross-family blind spots: patterns Anthropic-trained models systematically miss, rationalize past, or accept without question. Examples:
   - Security patterns Anthropic models default to "looks safe" (e.g., specific OWASP categories)
   - Code style assumptions baked into Claude's training the codebase doesn't follow
   - Markdown/doc conventions Claude assumes universal
   - Test claims accepted without inspecting actual tests
   - Anything that "feels right" because of training-data alignment

OUTPUT: Single JSON, schema:

{{
  "verdict": "satisfied" | "rework_required" | "suspicious_too_clean",
  "reviewer_role": "codex-informed",
  "iteration": {iter_n},
  "pass": 2,
  "preliminary_findings_status": {{
    "confirmed": [...], "resolved": [...], "superseded": [...]
  }},
  "findings": [
    {{"severity": "critical"|"major"|"minor", "issue": "...", "evidence_path": "...", "fix_hint": "..."}}
  ],
  "complements_peer": "<1-2 lines: which gaps you're filling that peer missed>",
  "summary": "<1 line>"
}}

If you found nothing peer missed AND you genuinely scanned for cross-family gaps → "satisfied".
If your scan was shallow or rushed → "suspicious_too_clean".
"""

PROMPT_PASS1_SONNET = """You are a SCOPED reviewer in PASS 1 of two-pass protocol. Your role is "average human reading criteria for the first time" — common-sense check, not architectural review.

CURATED engagement: {curated_path}

You CANNOT see handoff.md, acceptance-log.md, consilium-summary.md, validation-outputs/.

YOUR SCOPE (only these):
1. Read {curated_path}/criteria.md as a non-expert would: what does plain wording ask for?
2. Inspect executor-reports/ and actual deliverables: do they correspond to plain criteria wording?
3. Skip: deep architecture, security analysis, code style, micro-optimizations.

OUTPUT JSON:
{{
  "preliminary_view": "<1-3 lines>",
  "expected_deliverables": [...],
  "observed_deliverables": [...],
  "preliminary_findings": [...],
  "reviewer_role": "sonnet-scoped",
  "iteration": {iter_n},
  "pass": 1
}}

Stay in your scope.
"""

PROMPT_PASS2_SONNET = """You are a SCOPED reviewer in PASS 2.

Your Pass-1 preliminary view (formed from criteria + artefacts only):
{preliminary_json}

NOW you have full engagement at {engagement}, including handoff.md.

TASK: Read handoff.md. Does producer's claim match plain criteria wording?
Catch smart-model rationalizations:
- Criteria say "dark mode toggle" but only light theme implemented — peer may rationalize "implementable later", you say "criteria say IT, IT is missing".
- Criteria say "deploy to staging" but no deploy log — you say "where is the proof?".

OUTPUT JSON:
{{
  "verdict": "satisfied" | "rework_required" | "suspicious_too_clean",
  "reviewer_role": "sonnet-scoped",
  "iteration": {iter_n},
  "pass": 2,
  "preliminary_findings_status": {{"confirmed": [...], "resolved": [...], "superseded": [...]}},
  "findings": [...],
  "summary": "<1 line>"
}}
"""

PROMPT_PASS1_HAIKU = """You are a NAIVE reviewer in PASS 1. Find OBVIOUS mismatches.

CURATED engagement: {curated_path}

You CANNOT see handoff.md, acceptance-log.md, consilium-summary.md, validation-outputs/.

YOUR SCOPE (only obvious things):
1. Read {curated_path}/criteria.md.
2. Look at executor-reports/ and actual deliverables.
3. Spot OBVIOUS mismatches: typos in deliverable names, missing chunks, count mismatches (criteria says "3 components", you find 2), version mismatches (criteria says "v2", deliverable is v1), name mismatches (criteria "checkout button", report "submit button").

SKIP: architecture, security, performance, style.

OUTPUT JSON:
{{
  "preliminary_view": "<1 line — does plain criteria match obvious deliverables?>",
  "preliminary_findings": [...],
  "reviewer_role": "haiku-scoped",
  "iteration": {iter_n},
  "pass": 1
}}

Be fast and direct.
"""

PROMPT_PASS2_HAIKU = """You are a NAIVE reviewer in PASS 2.

Your Pass-1 preliminary findings:
{preliminary_json}

NOW you have full engagement at {engagement}.

TASK: Read handoff.md briefly. Does producer's handoff have obvious mismatches?
- Counts in §2 don't match criteria §"Done when"
- Names in handoff differ from criteria
- Sections claimed but content thin/empty
- Typos in product/feature names

OUTPUT JSON:
{{
  "verdict": "satisfied" | "rework_required" | "suspicious_too_clean",
  "reviewer_role": "haiku-scoped",
  "iteration": {iter_n},
  "pass": 2,
  "preliminary_findings_status": {{"confirmed": [...], "resolved": [...], "superseded": [...]}},
  "findings": [...],
  "summary": "<1 line>"
}}

Found nothing obvious in handoff and Pass-1 was clean → "satisfied".
"""

# ===========================================================================
# Role configuration — same roles, models, prompts, timeouts as adversary.py.
# ===========================================================================

ROLE_CONFIG: dict[str, dict] = {
    "peer-opus": {
        "engine": "claude",
        "model": "claude-opus-4-7",
        "prompt_pass1": PROMPT_PASS1_PEER,
        "prompt_pass2": PROMPT_PASS2_PEER,
        "needs_peer_findings": False,
        "timeout_s": 900,
    },
    "codex-blind": {
        "engine": "codex",
        "model": None,
        "prompt_pass1": PROMPT_PASS1_PEER,
        "prompt_pass2": PROMPT_PASS2_PEER,
        "needs_peer_findings": False,
        "timeout_s": 900,
    },
    "codex-informed": {
        "engine": "codex",
        "model": None,
        "prompt_pass1": PROMPT_PASS1_PEER,
        "prompt_pass2": PROMPT_PASS2_CODEX_INFORMED,
        "needs_peer_findings": True,
        "timeout_s": 900,
    },
    "sonnet-scoped": {
        "engine": "claude",
        "model": "claude-sonnet-4-6",
        "prompt_pass1": PROMPT_PASS1_SONNET,
        "prompt_pass2": PROMPT_PASS2_SONNET,
        "needs_peer_findings": False,
        "timeout_s": 600,
    },
    "haiku-scoped": {
        "engine": "claude",
        "model": "claude-haiku-4-5-20251001",
        "prompt_pass1": PROMPT_PASS1_HAIKU,
        "prompt_pass2": PROMPT_PASS2_HAIKU,
        "needs_peer_findings": False,
        "timeout_s": 300,
    },
}

# Files / dirs physically excluded from the curated Pass-1 view.
RESTRICTED_FILES = {
    "handoff.md",
    "acceptance-log.md",
    "consilium-summary.md",
    "human-directive.md",
}
RESTRICTED_DIRS = {"validation-outputs"}

CONSILIUM = {
    "S": [],
    "M": ["peer-opus"],
    "L": ["peer-opus", "codex-blind", "codex-informed", "sonnet-scoped", "haiku-scoped"],
}

# ===========================================================================
# Engagement helpers — ported verbatim from adversary.py. The output-file
# naming MUST stay byte-identical: consilium-synth.py and handoff-precheck.py
# parse these names with regexes.
# ===========================================================================


def read_iter_counter(eng: Path) -> int:
    counter = eng / "iteration"
    if counter.exists():
        try:
            return int(counter.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


def find_peer_findings(eng: Path, iter_n: int) -> str:
    """Locate latest peer-opus Pass-2 output for current iteration; return JSON text."""
    outputs = eng / "validation-outputs"
    if not outputs.exists():
        return ""
    # Exclude preliminary files — only the final Pass-2 output carries findings.
    candidates = sorted(
        p for p in outputs.glob(f"peer-opus-iter-{iter_n}-*.json")
        if "-preliminary-" not in p.name
    )
    if not candidates:
        return ""
    return candidates[-1].read_text(encoding="utf-8")


def ensure_outputs_dir(eng: Path) -> Path:
    outputs = eng / "validation-outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    return outputs


def write_output(eng: Path, role: str, iter_n: int, payload: dict, *, suffix: str = "") -> Path:
    """Write adversary output JSON. Naming identical to adversary.py.

    suffix='' for final (Pass 2): {role}-iter-{N}-{ts}.json
    suffix='preliminary' for Pass 1: {role}-iter-{N}-preliminary-{ts}.json
    """
    outputs = ensure_outputs_dir(eng)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if suffix:
        out_path = outputs / f"{role}-iter-{iter_n}-{suffix}-{ts}.json"
    else:
        out_path = outputs / f"{role}-iter-{iter_n}-{ts}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def prepare_curated_view(eng: Path) -> Path:
    """Copy engagement to a temp dir, excluding restricted files and dirs.

    Pass 1 receives this curated path so it physically cannot read producer's
    handoff, prior verdicts, other reviewers' outputs, or the aggregator.
    Caller must clean up via cleanup_curated().
    """
    tmpdir = Path(tempfile.mkdtemp(prefix=f"adversary-curated-{eng.name}-"))
    curated = tmpdir / eng.name

    def ignore(src_dir: str, names: list[str]) -> list[str]:
        if Path(src_dir).resolve() == eng.resolve():
            return [n for n in names if n in RESTRICTED_FILES or n in RESTRICTED_DIRS]
        return []

    shutil.copytree(eng, curated, ignore=ignore)
    return curated


def cleanup_curated(curated: Path) -> None:
    try:
        parent = curated.parent
        if parent.name.startswith("adversary-curated-"):
            shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        pass


# ===========================================================================
# JSON extraction + Pydantic validation.
# extract_json is ported verbatim. The new bit is feeding the parsed dict
# through the Pydantic schemas so a malformed reviewer output surfaces as a
# validation problem rather than a silent None / loose coercion.
# ===========================================================================


def extract_json(text: str) -> Optional[dict]:
    """Find first balanced JSON object in text. Returns parsed dict or None."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


# ===========================================================================
# Model invokers — the swappable layer. subprocess is the default and rides
# existing subscriptions (no billing change). api uses LangChain model classes
# and needs API keys. mock is for testing the graph without LLM calls.
# Every invoker returns (returncode, stdout, stderr, elapsed_s) so the parsing
# path downstream is uniform.
# ===========================================================================


def find_codex_cmd() -> Optional[str]:
    """Locate Codex CLI executable (ported verbatim from adversary.py)."""
    explicit = os.environ.get("CODEX_CMD")
    if explicit:
        resolved = shutil.which(explicit)
        if resolved:
            return resolved
        if Path(explicit).exists():
            return explicit
    resolved = shutil.which("codex")
    if resolved:
        return resolved
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        win_path = Path(local_app) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if win_path.exists():
            return str(win_path)
    for candidate in [
        Path.home() / ".local" / "bin" / "codex",
        Path("/usr/local/bin/codex"),
        Path("/opt/homebrew/bin/codex"),
    ]:
        if candidate.exists():
            return str(candidate)
    return None


class Invoker:
    """Base invoker interface."""
    name = "base"

    def invoke(self, role: str, config: dict, prompt: str) -> tuple[int, str, str, float]:
        raise NotImplementedError


class SubprocessInvoker(Invoker):
    """Default. Shells out to `claude -p` / `codex exec` — rides the user's
    existing Claude Code + ChatGPT subscriptions. No API keys, no extra
    billing. This is the path adversary.py used."""
    name = "subprocess"

    def _invoke_claude(self, prompt: str, model: str, timeout_s: int) -> tuple[int, str, str]:
        claude = find_claude_cmd()
        if not claude:
            return 127, "", "claude CLI not found in PATH; install Claude Code CLI"
        cmd = [claude, "-p", prompt, "--model", model]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout_s)
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"timeout after {timeout_s}s"
        except Exception as e:
            return 99, "", f"invocation error: {e}"

    def _invoke_codex(self, prompt: str, timeout_s: int) -> tuple[int, str, str]:
        codex = find_codex_cmd()
        if not codex:
            return 127, "", (
                "codex CLI not found. Install via `npm install -g @openai/codex` and "
                "authenticate via `codex auth` (uses ChatGPT subscription) or set "
                "OPENAI_API_KEY for API-key auth."
            )
        for variant in ([codex, "exec", prompt], [codex, prompt]):
            try:
                r = subprocess.run(variant, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout_s)
                if r.returncode == 2 and "usage" in (r.stderr or "").lower():
                    continue
                return r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                return 124, "", f"timeout after {timeout_s}s"
            except Exception as e:
                return 99, "", f"invocation error: {e}"
        return 1, "", "all codex invocation variants failed"

    def invoke(self, role: str, config: dict, prompt: str) -> tuple[int, str, str, float]:
        t0 = time.time()
        if config["engine"] == "claude":
            rc, stdout, stderr = self._invoke_claude(prompt, config["model"], config["timeout_s"])
        else:
            rc, stdout, stderr = self._invoke_codex(prompt, config["timeout_s"])
        return rc, stdout, stderr, round(time.time() - t0, 1)


class ApiInvoker(Invoker):
    """Opt-in. Uses LangChain ChatAnthropic / ChatOpenAI — needs API keys
    (ANTHROPIC_API_KEY / OPENAI_API_KEY), a separate billing surface from the
    subscriptions the subprocess invoker rides. Imports are lazy so a missing
    langchain-anthropic / langchain-openai does not break subprocess mode.

    Codex roles map to ChatOpenAI; set ADVERSARY_OPENAI_MODEL to the model you
    want (the ChatGPT-subscription restriction on explicit model names does not
    apply on the API-key path)."""
    name = "api"

    def __init__(self) -> None:
        self._anthropic: Any = None
        self._openai: Any = None

    def _get_anthropic(self, model: str):
        if self._anthropic is None or self._anthropic[0] != model:
            from langchain_anthropic import ChatAnthropic
            self._anthropic = (model, ChatAnthropic(model=model, max_tokens=8000))
        return self._anthropic[1]

    def _get_openai(self):
        if self._openai is None:
            from langchain_openai import ChatOpenAI
            model = os.environ.get("ADVERSARY_OPENAI_MODEL")
            if not model:
                raise RuntimeError(
                    "api invoker: codex roles need ADVERSARY_OPENAI_MODEL set "
                    "(e.g. a GPT model id available on your OpenAI API key)."
                )
            self._openai = ChatOpenAI(model=model)
        return self._openai

    def invoke(self, role: str, config: dict, prompt: str) -> tuple[int, str, str, float]:
        t0 = time.time()
        try:
            if config["engine"] == "claude":
                llm = self._get_anthropic(config["model"])
            else:
                llm = self._get_openai()
            resp = llm.invoke(prompt)
            content = resp.content if isinstance(resp.content, str) else json.dumps(resp.content)
            return 0, content, "", round(time.time() - t0, 1)
        except Exception as e:
            return 99, "", f"api invocation error: {e}", round(time.time() - t0, 1)


class MockInvoker(Invoker):
    """Testing only. Returns canned, schema-valid JSON without any LLM call, so
    the graph wiring (fan-out, dependency edge, checkpointer, output writing)
    can be exercised for free. ADVERSARY_MOCK_SLEEP adds a per-call delay so
    parallel execution is observable on the wall clock. ADVERSARY_MOCK_FAIL is a
    comma-separated role list that returns non-JSON so those roles fail (for
    testing the failed-role resume path)."""
    name = "mock"

    def invoke(self, role: str, config: dict, prompt: str) -> tuple[int, str, str, float]:
        t0 = time.time()
        sleep_s = float(os.environ.get("ADVERSARY_MOCK_SLEEP", "0") or "0")
        if sleep_s:
            time.sleep(sleep_s)
        fail_roles = {r.strip() for r in os.environ.get("ADVERSARY_MOCK_FAIL", "").split(",") if r.strip()}
        if role in fail_roles:
            return 1, "(simulated failure — not JSON)", "mock fail", round(time.time() - t0, 1)
        is_pass1 = "PASS 1" in prompt
        if is_pass1:
            payload = {
                "preliminary_view": f"[mock] {role} preliminary view",
                "expected_deliverables": ["[mock] expected"],
                "observed_deliverables": ["[mock] observed"],
                "preliminary_findings": [],
                "reviewer_role": role,
                "iteration": 0,
                "pass": 1,
            }
        else:
            payload = {
                "verdict": "satisfied",
                "reviewer_role": role,
                "iteration": 0,
                "pass": 2,
                "preliminary_findings_status": {"confirmed": [], "resolved": [], "superseded": []},
                "findings": [],
                "summary": f"[mock] {role} satisfied",
            }
        return 0, json.dumps(payload), "", round(time.time() - t0, 1)


def make_invoker(mode: str) -> Invoker:
    mode = (mode or "subprocess").lower()
    if mode == "subprocess":
        return SubprocessInvoker()
    if mode == "api":
        return ApiInvoker()
    if mode == "mock":
        return MockInvoker()
    raise ValueError(f"unknown invoker mode: {mode}")


# ===========================================================================
# Two-pass core — the per-role unit of work. Equivalent to adversary.py's
# run_role(), but invoker-parameterised and Pydantic-validated. Runs inside a
# single graph node, so the two passes are atomic from the graph's POV.
# ===========================================================================


def _save_raw_for_debug(eng: Path, role: str, iter_n: int, label: str,
                        stdout: str, stderr: str) -> Path:
    outputs = ensure_outputs_dir(eng)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = outputs / f"{role}-iter-{iter_n}-{label}-{ts}.raw.txt"
    raw_path.write_text(f"# stdout\n{stdout}\n\n# stderr\n{stderr}\n", encoding="utf-8")
    return raw_path


def _invoke_with_retry(invoker: Invoker, role: str, config: dict, prompt: str,
                       attempts: int = 2) -> tuple[Optional[dict], int, str, str, float]:
    """Invoke + extract JSON, retrying transient no-JSON failures in-node.

    Returns (parsed_dict_or_None, rc, stdout, stderr, elapsed_s). Graceful: on
    final failure returns None rather than raising — preserves adversary.py's
    one-role-fails-others-continue degradation.
    """
    last: tuple[int, str, str, float] = (99, "", "no attempt made", 0.0)
    for _ in range(max(1, attempts)):
        rc, stdout, stderr, elapsed = invoker.invoke(role, config, prompt)
        parsed = extract_json(stdout)
        if parsed is not None:
            return parsed, rc, stdout, stderr, elapsed
        last = (rc, stdout, stderr, elapsed)
    return None, last[0], last[1], last[2], last[3]


def _find_existing_preliminary(eng: Path, role: str, iter_n: int) -> Optional[tuple[dict, Path]]:
    """Locate an existing Pass-1 preliminary file for this role+iter.

    Used by --resume: if Pass 1 already ran and wrote its preliminary output,
    a re-run of the role (because Pass 2 crashed) reuses it instead of
    re-spending the Pass-1 LLM call. Returns (parsed_dict, path) or None.
    """
    outputs = eng / "validation-outputs"
    if not outputs.exists():
        return None
    candidates = sorted(outputs.glob(f"{role}-iter-{iter_n}-preliminary-*.json"))
    if not candidates:
        return None
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
        return data, candidates[-1]
    except Exception:
        return None


def _find_completed_roles(eng: Path, iter_n: int) -> set[str]:
    """Roles that already have a VALID Pass-2 final output for this iter.

    This is what powers --resume: a role with a valid final is done (its file
    stays on disk for consilium-synth); a role with no valid final — whether it
    never ran (crash) or ran and failed (no final written) — is re-dispatched.
    Artefact-driven, so it naturally covers both the crash and the failed-role
    case without depending on the LangGraph checkpoint blob.
    """
    done: set[str] = set()
    outputs = eng / "validation-outputs"
    if not outputs.exists():
        return done
    for f in outputs.glob(f"*-iter-{iter_n}-*.json"):
        if "-preliminary-" in f.name:
            continue
        m = re.match(rf"^(.+)-iter-{iter_n}-", f.name)
        if not m:
            continue
        role = m.group(1)
        if role not in ROLE_CONFIG:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("verdict", "")).lower() in VALID_VERDICTS:
            done.add(role)
    return done


def run_two_pass(role: str, eng: Path, iter_n: int, invoker: Invoker, *,
                 resume: bool = False) -> dict:
    """Run one reviewer role through the two-pass protocol.

    Pass 1: curated copy (handoff hidden) -> preliminary findings.
    Pass 2: full engagement + preliminary injected -> final verdict.

    Returns a result dict in the same shape adversary.py's run_role returned:
      {role, status: ok|fail|skip, verdict?, findings_count?, output_path?,
       preliminary_path?, elapsed_s?, delta_signal?, error?}
    """
    config = ROLE_CONFIG[role]

    # ---- Pass 1: preliminary view from a filesystem-curated copy ----
    # Resume optimisation: on --resume, if Pass 1 already wrote a preliminary
    # file for this role+iter, reuse it instead of re-spending the LLM call.
    # A crashed Pass 2 therefore costs only Pass 2, not the (up to 900s) Pass-1
    # call. Gated on `resume` so a normal run is always fresh (no stale reuse).
    prelim_reused = False
    reused = _find_existing_preliminary(eng, role, iter_n) if resume else None
    if reused is not None:
        preliminary_full, prelim_path = reused
        preliminary = {k: v for k, v in preliminary_full.items() if k != "_invocation"}
        elapsed1, rc1 = 0.0, 0
        prelim_reused = True
    else:
        curated: Optional[Path] = None
        try:
            curated = prepare_curated_view(eng)
            prompt1 = config["prompt_pass1"].format(
                curated_path=str(curated), role=role, iter_n=iter_n,
            )
            preliminary, rc1, stdout1, stderr1, elapsed1 = _invoke_with_retry(
                invoker, role, config, prompt1,
            )
            if not preliminary:
                raw_path = _save_raw_for_debug(eng, role, iter_n, "pass1", stdout1, stderr1)
                return {
                    "role": role,
                    "status": "fail",
                    "error": f"Pass 1 produced no JSON (rc={rc1}, elapsed={elapsed1}s); raw at {raw_path.name}",
                    "raw_path": str(raw_path),
                }
            # Structural validation (lenient — keep raw dict, attach warning on failure).
            try:
                Pass1Output.model_validate(preliminary)
            except Exception as e:
                preliminary.setdefault("_validation_warning", f"pass1 schema: {e}")
            preliminary_payload = {
                **preliminary,
                "_invocation": {
                    "engine": config["engine"],
                    "model": config["model"],
                    "elapsed_s": elapsed1,
                    "returncode": rc1,
                    "pass": 1,
                    "curated_path": str(curated),
                    "invoker": invoker.name,
                },
            }
            prelim_path = write_output(eng, role, iter_n, preliminary_payload, suffix="preliminary")
        finally:
            if curated is not None:
                cleanup_curated(curated)

    # ---- Pass 2: full engagement, finalize verdict ----
    peer_findings = ""
    if config["needs_peer_findings"]:
        peer_findings = find_peer_findings(eng, iter_n)
        if not peer_findings:
            return {
                "role": role,
                "status": "fail",
                "error": "Pass 2 needs peer-opus output but none found for current iteration; run peer-opus first",
                "preliminary_path": str(prelim_path),
            }

    prompt2 = config["prompt_pass2"].format(
        engagement=str(eng),
        role=role,
        iter_n=iter_n,
        preliminary_json=json.dumps(preliminary, ensure_ascii=False, indent=2),
        peer_findings=peer_findings or "(none)",
    )
    parsed2, rc2, stdout2, stderr2, elapsed2 = _invoke_with_retry(
        invoker, role, config, prompt2,
    )
    if not parsed2:
        raw_path = _save_raw_for_debug(eng, role, iter_n, "pass2", stdout2, stderr2)
        return {
            "role": role,
            "status": "fail",
            "error": f"Pass 2 produced no JSON (rc={rc2}, elapsed={elapsed2}s); raw at {raw_path.name}",
            "raw_path": str(raw_path),
            "preliminary_path": str(prelim_path),
        }

    # Pydantic validation — this replaces normalize_payload. Verdict coercion
    # (unknown -> suspicious_too_clean) lives in the Pass2Output validator.
    model = Pass2Output.model_validate(parsed2)

    prelim_findings_count = len(preliminary.get("preliminary_findings", []))
    final_findings_count = len(model.findings)
    delta_signal = "n/a"
    if prelim_findings_count > 0 or final_findings_count > 0:
        if final_findings_count == 0 and prelim_findings_count > 0:
            delta_signal = "all_resolved"
        elif abs(final_findings_count - prelim_findings_count) <= 1:
            delta_signal = "stable"
        elif final_findings_count > prelim_findings_count * 2:
            delta_signal = "handoff_revealed_more"
        else:
            delta_signal = "shifted"

    payload = {
        "verdict": model.verdict,
        "reviewer_role": role,           # force known value, do not trust LLM self-report
        "iteration": iter_n,             # force known value
        "findings": [f.model_dump() for f in model.findings],
        "summary": model.summary,
        "preliminary_findings_status": model.preliminary_findings_status.model_dump(),
        "_invocation": {
            "engine": config["engine"],
            "model": config["model"],
            "elapsed_s_pass1": elapsed1,
            "elapsed_s_pass2": elapsed2,
            "returncode_pass1": rc1,
            "returncode_pass2": rc2,
            "pass": 2,
            "invoker": invoker.name,
        },
        "_two_pass": {
            "preliminary_findings_count": prelim_findings_count,
            "final_findings_count": final_findings_count,
            "delta_signal": delta_signal,
            "preliminary_path": prelim_path.name,
            "pass1_reused": prelim_reused,
        },
    }
    out_path = write_output(eng, role, iter_n, payload)
    return {
        "role": role,
        "status": "ok",
        "verdict": payload["verdict"],
        "findings_count": final_findings_count,
        "output_path": str(out_path),
        "preliminary_path": str(prelim_path),
        "elapsed_s": round(elapsed1 + elapsed2, 1),
        "delta_signal": delta_signal,
    }


# ===========================================================================
# LangGraph consilium graph.
#
#   START -> plan        (on --resume: drops roles that already have a valid
#                         final output; the rest — missing OR failed — stay)
#   plan  --conditional--> Send(run_role, ...) x N   (phase-1 roles, parallel)
#         --conditional--> Send(run_role_p2, ...)    (codex-informed only, when
#                                                     phase-1 is empty)
#         --conditional--> finalize                  (nothing pending)
#   run_role -> barrier
#   barrier --conditional--> Send(run_role_p2, ...)  (codex-informed, L-tier)
#           --conditional--> note_skipped_ci         (no peer-opus output)
#           --conditional--> finalize                (no codex-informed needed)
#   run_role_p2 -> finalize
#   note_skipped_ci -> finalize
#   finalize -> END
#
# run_role and run_role_p2 are the SAME function under two node names — this
# keeps the codex-informed second wave from looping back through barrier.
# ===========================================================================


class ConsiliumState(TypedDict, total=False):
    engagement: str
    iter_n: int
    tier: str
    roles: list[str]
    resume: bool
    phase1_roles: list[str]
    needs_codex_informed: bool
    skipped_done_roles: list[str]
    # Per-role Send payloads carry these scratch keys:
    role: str
    peer_findings: str
    # Reducer key — every role node appends here, results merge across the fan-out.
    results: Annotated[list[dict], operator.add]
    # Auto-synth output: consilium-synth.py JSON result if it ran.
    synth_result: dict
    # native HITL via interrupt():
    # Whether to pause for human directive after auto-synth.
    interrupt_enabled: bool
    # Captured human directive once resumed (from Command(resume=...)).
    human_directive: dict
    # human_directive_result: outcome of human-directive.py invocation.
    human_directive_result: dict


def _plan_node(state: ConsiliumState) -> dict:
    """Decide which roles to dispatch. On --resume, roles that already have a
    valid final output are skipped; everything else (never-ran OR failed) is
    pending."""
    roles = list(state.get("roles", []))
    resume = bool(state.get("resume", False))
    eng = Path(state["engagement"])
    iter_n = state["iter_n"]

    done = _find_completed_roles(eng, iter_n) if resume else set()
    skipped = sorted(done & set(roles))
    pending = [r for r in roles if r not in done]

    phase1 = [r for r in pending if r != "codex-informed"]
    needs_ci = "codex-informed" in pending
    return {
        "phase1_roles": phase1,
        "needs_codex_informed": needs_ci,
        "skipped_done_roles": skipped,
    }


def _route_after_plan(state: ConsiliumState):
    phase1 = state.get("phase1_roles", [])
    eng = state["engagement"]
    iter_n = state["iter_n"]
    if phase1:
        return [
            Send("run_role", {"role": r, "engagement": eng, "iter_n": iter_n, "peer_findings": ""})
            for r in phase1
        ]
    # No phase-1 roles to run. codex-informed may still be pending — a lone
    # --role codex-informed, or a --resume where everything else is already done.
    if state.get("needs_codex_informed"):
        pf = find_peer_findings(Path(eng), iter_n)
        return [Send("run_role_p2", {
            "role": "codex-informed", "engagement": eng, "iter_n": iter_n, "peer_findings": pf,
        })]
    return "finalize"


def _barrier_node(state: ConsiliumState) -> dict:
    # Fan-in join point. Nothing to compute; routing happens in the conditional edge.
    return {}


def _route_after_barrier(state: ConsiliumState):
    if not state.get("needs_codex_informed"):
        return "finalize"
    eng = state["engagement"]
    iter_n = state["iter_n"]
    # peer-opus findings may come from this run OR a prior run (--resume where
    # peer-opus was already done) — check the file on disk, not just this run's
    # results. No file -> peer-opus is genuinely unavailable -> skip.
    pf = find_peer_findings(Path(eng), iter_n)
    if not pf:
        return "note_skipped_ci"
    return [Send("run_role_p2", {
        "role": "codex-informed", "engagement": eng, "iter_n": iter_n, "peer_findings": pf,
    })]


def _note_skipped_ci_node(state: ConsiliumState) -> dict:
    return {"results": [{
        "role": "codex-informed",
        "status": "skip",
        "error": "peer-opus failed; codex-informed cannot run without peer findings",
    }]}


def _make_finalize_node(auto_synth: bool):
    """Finalize. By default invokes consilium-synth.py at the end of a multi-
    role run so M/L acceptance is one atomic LangGraph command instead of two
    manual steps. --no-synth opts out for callers that want to inspect outputs
    or re-synth manually.

    Auto-synth is skipped when:
      - --no-synth was passed (auto_synth=False)
      - no role produced an ok result (nothing to synthesise)
      - the run was a single-role (--role X) standalone invocation — tier=S
        is set by main() for those, and they aren't part of a consilium
      - consilium-synth.py is not on disk next to this script

    M-tier (single peer-opus) DOES auto-synth: even with one reviewer,
    consilium-summary.md is what the director reads in the human-judge step.
    """
    def finalize_node(state: ConsiliumState) -> dict:
        if not auto_synth:
            return {}
        results = state.get("results", [])
        ok_results = [r for r in results if r.get("status") == "ok"]
        if not ok_results:
            return {}
        # Synth only for consilium runs (M/L). Standalone --role X sets tier=S
        # in main() and is not part of a consilium — skip.
        tier = state.get("tier", "")
        if tier not in {"M", "L"}:
            return {}
        eng = Path(state["engagement"])
        iter_n = state["iter_n"]
        synth_script = Path(__file__).resolve().parent / "consilium-synth.py"
        if not synth_script.exists():
            return {"synth_result": {
                "status": "skipped",
                "reason": f"consilium-synth.py not found at {synth_script}",
            }}
        try:
            r = subprocess.run(
                [sys.executable, str(synth_script), str(eng),
                 "--iter", str(iter_n), "--json"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            if r.returncode == 0:
                try:
                    data = json.loads(r.stdout)
                    # Normalize natural verdict to ledger schema
                    # (mirror of per-role mapping in _make_run_role_node).
                    _agg = data.get("aggregate_verdict")
                    _ledger_verdict = {
                        "satisfied": "ACCEPT",
                        "rework_required": "REJECT",
                        "suspicious_too_clean": "REJECT",
                    }.get(_agg, "N/A")
                    _ledger_emit(
                        "consilium_synth_completed",
                        node="finalize",
                        payload={
                            "summary_path": data.get("summary_path"),
                            "aggregate_verdict": _agg,
                            "unique_findings": data.get("unique_findings"),
                            "tier": tier,
                        },
                        verdict=_ledger_verdict,
                    )
                    return {"synth_result": {
                        "status": "ok",
                        "summary_path": data.get("summary_path"),
                        "aggregate_verdict": data.get("aggregate_verdict"),
                        "rationale": data.get("rationale"),
                        "unique_findings": data.get("unique_findings"),
                        "cross_family_disagreements": data.get("cross_family_disagreements"),
                    }}
                except Exception:
                    _ledger_emit(
                        "consilium_synth_completed",
                        node="finalize",
                        payload={"status": "ok_unparsed", "tier": tier},
                    )
                    return {"synth_result": {"status": "ok", "raw": (r.stdout or "")[:200]}}
            return {"synth_result": {
                "status": "fail",
                "rc": r.returncode,
                "error": (r.stderr or "")[:200],
            }}
        except subprocess.TimeoutExpired:
            return {"synth_result": {
                "status": "fail",
                "error": "consilium-synth.py timed out after 60s",
            }}
        except Exception as e:
            return {"synth_result": {"status": "fail", "error": str(e)}}
    return finalize_node


def _present_node(state: ConsiliumState) -> dict:
    """invoke consilium-present.py to format chat-ready summary.

    Runs only when interrupt is enabled AND synth produced a summary. Output
    goes to stderr so JSON stdout stays clean. The actual interrupt happens
    in the next node — this one just makes sure the human has something to
    read before being asked for a directive.
    """
    if not state.get("interrupt_enabled"):
        return {}
    synth = state.get("synth_result") or {}
    if synth.get("status") != "ok":
        # Nothing meaningful to present. Interrupt-apply still runs so caller
        # can decide.
        return {}
    eng = Path(state["engagement"])
    present_script = Path(__file__).resolve().parent / "consilium-present.py"
    if not present_script.exists():
        print(f"WARN: consilium-present.py not found at {present_script}",
              file=sys.stderr)
        return {}
    try:
        r = subprocess.run(
            [sys.executable, str(present_script), str(eng)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode == 0 and r.stdout:
            # The decision-menu output is meant for the operator. Goes to
            # stderr so it shows up without polluting --json stdout.
            print("\n" + "=" * 70, file=sys.stderr)
            print("CONSILIUM SUMMARY (chat-ready) — review before resuming:",
                  file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(r.stdout, file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)
        else:
            print(f"WARN: consilium-present.py rc={r.returncode}: "
                  f"{(r.stderr or '')[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("WARN: consilium-present.py timed out", file=sys.stderr)
    except Exception as e:
        print(f"WARN: consilium-present.py error: {e}", file=sys.stderr)
    return {}


def _interrupt_apply_directive_node(state: ConsiliumState) -> dict:
    """native HITL pause via interrupt() + apply directive on resume.

    Pattern: graph pauses at interrupt(); operator runs:

        python adversary_lg.py engagement/ --resume-interrupt <thread_id> \\
            --decision PROCEED|REJECT|DIRECTED [--reasons ...] [--note ...]

    The resume invocation feeds the directive payload back via
    Command(resume={"decision": ..., ...}). This node receives that payload,
    invokes human-directive.py to write the canonical engagement/human-directive.md
    file, and emits human_directive_result.

    Without --interrupt, the node is a no-op (the graph never reaches it
    because the routing edge skips this branch).
    """
    if not state.get("interrupt_enabled"):
        return {}

    _ledger_emit(
        "interrupt_paused",
        node="apply_directive",
        interrupt_state="paused",
        payload={
            "tier": state.get("tier"),
            "synth_summary": (state.get("synth_result") or {}).get("summary_path"),
            "aggregate_verdict": (state.get("synth_result") or {}).get("aggregate_verdict"),
        },
    )

    # Native interrupt — graph pauses here. On resume, `directive` holds
    # whatever caller passed via Command(resume=...).
    directive = interrupt({
        "phase": "human_directive_required",
        "engagement": state["engagement"],
        "iter_n": state["iter_n"],
        "tier": state.get("tier"),
        "synth_summary": (state.get("synth_result") or {}).get("summary_path"),
        "options": ["PROCEED", "REJECT", "DIRECTED"],
        "resume_help": (
            "Resume with: python adversary_lg.py <eng> --resume-interrupt "
            "<thread_id> --decision PROCEED|REJECT|DIRECTED "
            "[--reasons ...] [--note ...] [--address ...] [--override ...]"
        ),
    })

    _ledger_emit(
        "interrupt_resumed",
        node="apply_directive",
        interrupt_state="resumed",
        payload={"decision": (directive or {}).get("decision") if isinstance(directive, dict) else None},
    )

    # `directive` is the payload from Command(resume=...). Validate minimally.
    if not isinstance(directive, dict) or "decision" not in directive:
        return {"human_directive_result": {
            "status": "fail",
            "error": f"resume payload missing 'decision' key: got {type(directive).__name__}",
        }}

    decision = directive.get("decision", "").upper()
    if decision not in {"PROCEED", "REJECT", "DIRECTED"}:
        return {"human_directive_result": {
            "status": "fail",
            "error": f"invalid decision '{decision}', expected PROCEED|REJECT|DIRECTED",
        }}

    # Invoke human-directive.py to write engagement/human-directive.md.
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
    if directive.get("reasons"):
        cmd += ["--reasons", str(directive["reasons"])]
    if directive.get("note"):
        cmd += ["--note", str(directive["note"])]
    if directive.get("address"):
        cmd += ["--address", str(directive["address"])]
    if directive.get("override"):
        cmd += ["--override", str(directive["override"])]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            _ledger_emit(
                "human_directive_received",
                node="apply_directive",
                payload={
                    "decision": decision,
                    "directive_path": str(eng / "human-directive.md"),
                },
                verdict=decision if decision in {"PROCEED", "REJECT", "DIRECTED"} else None,
            )
            return {
                "human_directive": directive,
                "human_directive_result": {
                    "status": "ok",
                    "decision": decision,
                    "directive_path": str(eng / "human-directive.md"),
                    "stdout": (r.stdout or "")[:200],
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


def _route_after_finalize(state: ConsiliumState):
    """If --interrupt is enabled AND tier is M/L, present summary and pause
    for human directive. Otherwise, end the graph.

    Defense-in-depth: interrupt only makes sense for consilium runs (M/L) that
    produced a synth output. Single-role runs (tier=S, --role) have nothing to
    present and no consilium adjudication for the human to decide on. The CLI
    gates this via parser.error, but check again here in case interrupt_enabled
    is set programmatically (LangGraph invoke with custom init_state)."""
    if not state.get("interrupt_enabled"):
        return END
    tier = state.get("tier", "")
    if tier not in {"M", "L"}:
        return END
    return "present"


def _make_run_role_node(invoker: Invoker, resume: bool = False):
    """Role node. Receives a Send payload with {role, engagement, iter_n,
    peer_findings}. Runs the two-pass protocol, appends one result to the
    shared `results` list. Graceful: failures return a status:fail dict, never
    raise — so a crashed reviewer does not abort the other branches.

    `resume` is threaded down to run_two_pass: a role re-run because its Pass 2
    crashed will reuse an already-written Pass-1 preliminary file."""

    def run_role_node(state: ConsiliumState) -> dict:
        role = state["role"]
        eng = Path(state["engagement"])
        iter_n = state["iter_n"]
        tier = state.get("tier", "")
        config = ROLE_CONFIG.get(role)
        if config is None:
            _ledger_emit(
                "consilium_role_completed",
                node=f"consilium:{role}",
                actor=role,
                payload={"role": role, "status": "fail", "iter_n": iter_n,
                         "error": f"unknown role: {role}"},
                verdict="REJECT",
            )
            return {"results": [{"role": role, "status": "fail", "error": f"unknown role: {role}"}]}
        # codex-informed routed here directly (lone --role) still needs peer findings.
        if config["needs_peer_findings"] and not state.get("peer_findings"):
            pf = find_peer_findings(eng, iter_n)
            if not pf:
                _ledger_emit(
                    "consilium_role_completed",
                    node=f"consilium:{role}",
                    actor=role,
                    payload={"role": role, "status": "fail", "iter_n": iter_n,
                             "error": "missing peer-opus output"},
                    verdict="REJECT",
                )
                return {"results": [{
                    "role": role, "status": "fail",
                    "error": "Pass 2 needs peer-opus output but none found; run peer-opus first",
                }]}
        _ledger_emit(
            "consilium_started",
            node=f"consilium:{role}",
            actor=role,
            payload={"role": role, "iter_n": iter_n, "tier": tier,
                     "engine": config.get("engine"), "model": config.get("model")},
        )
        try:
            result = run_two_pass(role, eng, iter_n, invoker, resume=resume)
        except Exception as e:  # last-resort guard — keep the fan-out alive
            result = {"role": role, "status": "fail", "error": f"unexpected error: {e}"}
        # Build completion payload from whichever fields run_two_pass populated.
        _completion_payload = {
            "role": role,
            "status": result.get("status", "unknown"),
            "iter_n": iter_n,
        }
        for _k in ("verdict", "findings_count", "elapsed_s", "delta_signal", "error",
                   "output_path", "preliminary_path"):
            if _k in result:
                _completion_payload[_k] = result[_k]
        # Map two-pass verdict → canonical ledger verdict (ACCEPT/REJECT/DIRECTED/N/A).
        if result.get("status") == "ok":
            _v = result.get("verdict")
            if _v == "satisfied":
                _ledger_verdict = "ACCEPT"
            elif _v in ("rework_required", "suspicious_too_clean"):
                _ledger_verdict = "REJECT"
            else:
                _ledger_verdict = "N/A"
        elif result.get("status") == "fail":
            _ledger_verdict = "REJECT"
        else:
            _ledger_verdict = "N/A"
        _ledger_emit(
            "consilium_role_completed",
            node=f"consilium:{role}",
            actor=role,
            payload=_completion_payload,
            verdict=_ledger_verdict,
        )
        return {"results": [result]}

    return run_role_node


def build_graph(invoker: Invoker, checkpointer, resume: bool = False,
                auto_synth: bool = True):
    """Compile the consilium graph with the given invoker and checkpointer.

    auto_synth=True (default) makes the finalize node invoke consilium-synth.py
    at the end of a multi-role run, so M/L acceptance is one atomic command.

    The `present` + `interrupt_apply_directive` branch is wired in but only
    activated when state.interrupt_enabled is True (set by --interrupt CLI flag).
    On activation: graph pauses at interrupt(), operator resumes with directive
    via Command(resume={...}) — see _interrupt_apply_directive_node docstring.
    """
    run_role_node = _make_run_role_node(invoker, resume)
    finalize_node = _make_finalize_node(auto_synth)

    builder = StateGraph(ConsiliumState)
    builder.add_node("plan", _plan_node)
    builder.add_node("run_role", run_role_node)
    builder.add_node("run_role_p2", run_role_node)  # same fn, second graph position
    builder.add_node("barrier", _barrier_node)
    builder.add_node("note_skipped_ci", _note_skipped_ci_node)
    builder.add_node("finalize", finalize_node)
    # optional HITL pause-and-resume branch.
    builder.add_node("present", _present_node)
    builder.add_node("interrupt_apply_directive", _interrupt_apply_directive_node)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan", _route_after_plan, ["run_role", "run_role_p2", "finalize"],
    )
    builder.add_edge("run_role", "barrier")
    builder.add_conditional_edges(
        "barrier", _route_after_barrier, ["run_role_p2", "note_skipped_ci", "finalize"],
    )
    builder.add_edge("run_role_p2", "finalize")
    builder.add_edge("note_skipped_ci", "finalize")
    # route either to END (default) or through HITL branch.
    builder.add_conditional_edges(
        "finalize", _route_after_finalize, ["present", END],
    )
    builder.add_edge("present", "interrupt_apply_directive")
    builder.add_edge("interrupt_apply_directive", END)

    return builder.compile(checkpointer=checkpointer)


# ===========================================================================
# Checkpointer
# ===========================================================================

CHECKPOINT_DB = Path(__file__).resolve().parent / ".adversary-lg-checkpoints.sqlite"


def make_checkpointer() -> SqliteSaver:
    # check_same_thread=False: LangGraph runs fan-out branches in worker threads.
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    return SqliteSaver(conn)


def thread_id_for(eng: Path, iter_n: int, label: str) -> str:
    # Unique per invocation. Resume is artefact-driven (plan node), not
    # checkpoint-replay, so the thread_id does not need to be stable.
    digest = hashlib.sha1(str(eng).encode("utf-8")).hexdigest()[:12]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{digest}-iter-{iter_n}-{label}-{ts}"


def setup_langsmith() -> str:
    """Make LangSmith tracing first-class: detect the env config, default a
    project name when tracing is on, and return a one-line status the operator
    can see. Tracing itself is auto-instrumented by LangGraph when the env vars
    are set — there is no code to write, the gap was that it was invisible and
    undocumented. This makes it visible.

    Enable with:  LANGSMITH_TRACING=true  +  LANGSMITH_API_KEY=<key>
    Optional:     LANGSMITH_PROJECT=<name>   (defaults to "adversary-lg")
    """
    on = (os.environ.get("LANGSMITH_TRACING", "").lower() in {"true", "1"}
          or os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in {"true", "1"})
    if not on:
        return ("LangSmith tracing: OFF  (enable: LANGSMITH_TRACING=true + "
                "LANGSMITH_API_KEY=<key>)")
    if not os.environ.get("LANGSMITH_PROJECT") and not os.environ.get("LANGCHAIN_PROJECT"):
        os.environ["LANGSMITH_PROJECT"] = "adversary-lg"
    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT")
    has_key = bool(os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY"))
    if not has_key:
        return (f"LangSmith tracing: ON but LANGSMITH_API_KEY missing — traces will "
                f"NOT upload (project={project})")
    return f"LangSmith tracing: ON  (project={project})"


# ===========================================================================
# CLI — drop-in surface compatible with adversary.py, plus the new flags.
# ===========================================================================

BILLING_NOTE = """\
Invoker billing model
=====================

--invoker subprocess  (DEFAULT)
    Shells out to `claude -p` and `codex exec`. Rides your existing Claude Code
    and ChatGPT subscriptions. No API keys, no metered API billing. This is the
    same model adversary.py used — switching to adversary_lg.py changes nothing
    about cost or auth.

--invoker api  (OPT-IN)
    Uses LangChain ChatAnthropic / ChatOpenAI. Calls go through the metered
    APIs and require:
      ANTHROPIC_API_KEY   — for peer-opus, sonnet-scoped, haiku-scoped
      OPENAI_API_KEY      — for codex-blind, codex-informed
      ADVERSARY_OPENAI_MODEL — the GPT model id to use for codex roles
    This is a separate billing surface from your subscriptions. You only need
    it if you want native async, structured-output, retry/fallback at the model
    layer. The graph, checkpointer and Pydantic validation all work the same on
    either invoker — the choice is purely auth + billing.

--invoker mock
    No LLM calls at all. For testing the graph wiring.
"""


def _resume_interrupted(args) -> int:
    """resume a graph paused at interrupt() with a human directive.

    Replays via Command(resume={...}). The graph picks up at
    _interrupt_apply_directive_node, validates the directive, invokes
    human-directive.py to write engagement/human-directive.md, and ends.
    """
    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    # interrupt requires the checkpointer (we already gated this in main).
    checkpointer = make_checkpointer()
    try:
        # We don't need an invoker for the resume path (no role nodes will run),
        # but build_graph requires one. Use mock — cheapest, no LLM call.
        invoker = make_invoker("mock")
        graph = build_graph(invoker, checkpointer, resume=False, auto_synth=True)
        config = {"configurable": {"thread_id": args.resume_interrupt}}

        directive_payload = {"decision": args.decision}
        if args.reasons:
            directive_payload["reasons"] = args.reasons
        if args.note:
            directive_payload["note"] = args.note
        if args.address:
            directive_payload["address"] = args.address
        if args.override:
            directive_payload["override"] = args.override

        final_state = graph.invoke(Command(resume=directive_payload), config)
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
            print("Next: director runs acceptance per human-directive.md.")
        else:
            print(f"Resume FAILED: {hdr.get('error', '?')}", file=sys.stderr)
            return 1
    return 0 if hdr.get("status") == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LangGraph adversary bridge — drop-in replacement for adversary.py",
    )
    parser.add_argument("engagement", nargs="?", help="Path to engagement/ directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--role", choices=list(ROLE_CONFIG.keys()),
                       help="Run a single adversary role")
    group.add_argument("--consilium", choices=["S", "M", "L"],
                       help="Run preset consilium for tier")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    parser.add_argument("--json", action="store_true",
                        help="Print results as JSON to stdout (in addition to file outputs)")
    parser.add_argument("--invoker", choices=["subprocess", "api", "mock"],
                        default=os.environ.get("ADVERSARY_INVOKER", "subprocess"),
                        help="Model invocation backend (default: subprocess — see --help-billing)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume: skip reviewer roles that already have a valid final output "
                             "for this engagement+iter, re-run the rest — both the missing (crashed) "
                             "and the failed ones. A re-run role reuses its pass-1 preliminary if present.")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Run without the SQLite checkpointer (disables LangGraph-native state "
                             "introspection / LangSmith). --resume still works — it is artefact-driven.")
    parser.add_argument("--no-synth", action="store_true",
                        help="Skip the auto-synth finalize step. By default a multi-role consilium "
                             "run (M/L) automatically invokes consilium-synth.py on completion, so "
                             "consilium-summary.md is written in the same command. --no-synth "
                             "restores the older two-step flow.")
    parser.add_argument("--interrupt", action="store_true",
                        help="pause after auto-synth for native HITL via interrupt(). "
                             "Graph runs roles → synth → presents chat summary to stderr → pauses. "
                             "Operator resumes with: --resume-interrupt <thread_id> "
                             "--decision PROCEED|REJECT|DIRECTED [--reasons ...] [--note ...] "
                             "[--address ...] [--override ...]. On resume, the directive is written "
                             "to engagement/human-directive.md by invoking human-directive.py.")
    parser.add_argument("--resume-interrupt", metavar="THREAD_ID",
                        help="Resume an interrupted graph by thread_id (printed when graph paused). "
                             "Requires --decision; optional --reasons, --note, --address, --override.")
    parser.add_argument("--decision", choices=["PROCEED", "REJECT", "DIRECTED"],
                        help="Human directive decision (used with --resume-interrupt).")
    parser.add_argument("--reasons",
                        help="Reasons string (used with --resume-interrupt --decision REJECT).")
    parser.add_argument("--note",
                        help="Optional note for director (any decision).")
    parser.add_argument("--address",
                        help="Mandatory addresses (used with --decision DIRECTED).")
    parser.add_argument("--override",
                        help="Override instructions (used with --decision DIRECTED).")
    parser.add_argument("--help-billing", action="store_true",
                        help="Explain the --invoker billing model and exit.")
    args = parser.parse_args()

    if args.help_billing:
        print(BILLING_NOTE)
        return 0

    if not args.engagement:
        parser.error("engagement path is required (unless --help-billing)")

    # resume-interrupt is its own short path — no need for --role/--consilium.
    if args.resume_interrupt:
        if not args.decision:
            parser.error("--resume-interrupt requires --decision PROCEED|REJECT|DIRECTED")
        if args.decision == "REJECT" and not args.reasons:
            parser.error("--decision REJECT requires --reasons '<short reason>'")
        if args.decision == "DIRECTED" and not (args.address or args.override):
            parser.error("--decision DIRECTED requires --address and/or --override")
        return _resume_interrupted(args)

    if not args.role and not args.consilium:
        parser.error("one of --role or --consilium is required")

    # --interrupt only valid for consilium runs (single-role doesn't synth).
    if args.interrupt and not args.consilium:
        parser.error("--interrupt requires --consilium {M|L} (single-role doesn't pause)")
    if args.interrupt and args.no_synth:
        parser.error("--interrupt and --no-synth are incompatible (interrupt presents synth output)")
    if args.interrupt and args.no_checkpoint:
        parser.error("--interrupt requires the SQLite checkpointer (--no-checkpoint disables resume)")

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    iter_n = args.iter if args.iter is not None else read_iter_counter(eng)

    if args.role:
        roles = [args.role]
        tier = "S"  # tier is irrelevant for single-role runs; not used downstream
        label = args.role
    else:
        tier = args.consilium
        roles = list(CONSILIUM[tier])
        label = f"consilium-{tier}"

    # Initialize event ledger (no-op when lib.ledger import failed).
    global _RUN_LEDGER
    if _LEDGER_AVAILABLE:
        try:
            _RUN_LEDGER = EventLedger(
                eng, agent="adversary-lg", tier=tier if tier in {"S", "M", "L"} else None,
            )
            _RUN_LEDGER.emit(
                "engagement_started",
                node="adversary_lg:main",
                payload={
                    "iter_n": iter_n,
                    "mode": "consilium" if args.consilium else "single-role",
                    "tier": tier,
                    "roles": roles,
                    "invoker": args.invoker,
                    "resume": args.resume,
                    "interrupt": bool(args.interrupt),
                    "auto_synth": not args.no_synth,
                },
            )
        except Exception as e:
            print(f"WARN: ledger init failed (continuing without ledger): {e}",
                  file=sys.stderr)
            _RUN_LEDGER = None

    try:
        invoker = make_invoker(args.invoker)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # LangSmith tracing is auto-instrumented by LangGraph when its env vars are
    # set — surface the state so it is not a silent mystery. stderr keeps --json
    # stdout clean.
    print(setup_langsmith(), file=sys.stderr)

    checkpointer = None if args.no_checkpoint else make_checkpointer()
    try:
        graph = build_graph(invoker, checkpointer, resume=args.resume,
                            auto_synth=not args.no_synth)
        config = {"configurable": {"thread_id": thread_id_for(eng, iter_n, label)}}

        # Always a fresh invoke — resume is artefact-driven (the plan node scans
        # validation-outputs/), not checkpoint-replay. Works with or without the
        # checkpointer.
        init_state: ConsiliumState = {
            "engagement": str(eng),
            "iter_n": iter_n,
            "tier": tier,
            "roles": roles,
            "resume": args.resume,
            "results": [],
            "interrupt_enabled": bool(args.interrupt),
        }
        final_state = graph.invoke(init_state, config)
        # if --interrupt was set, the graph paused at interrupt().
        # Detect by presence of an __interrupt__ key OR absence of human_directive_result.
        if args.interrupt:
            paused = bool(final_state.get("__interrupt__"))
            no_directive = "human_directive_result" not in final_state
            if paused or no_directive:
                thread_id = config["configurable"]["thread_id"]
                print("\n" + "=" * 70, file=sys.stderr)
                print("GRAPH PAUSED for human directive (HITL pause).", file=sys.stderr)
                print(f"  thread_id: {thread_id}", file=sys.stderr)
                print("  Resume command:", file=sys.stderr)
                print(f"    python {Path(__file__).name} {eng} "
                      f"--resume-interrupt {thread_id} "
                      f"--decision PROCEED|REJECT|DIRECTED [...]", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                if args.json:
                    print(json.dumps({
                        "status": "paused",
                        "thread_id": thread_id,
                        "engagement": str(eng),
                        "iter": iter_n,
                        "synth": final_state.get("synth_result"),
                    }, ensure_ascii=False, indent=2))
                return 0
    finally:
        if checkpointer is not None:
            try:
                checkpointer.conn.close()
            except Exception:
                pass

    results: list[dict] = list(final_state.get("results", []))
    skipped_done: list[str] = list(final_state.get("skipped_done_roles", []))

    # Nothing ran this invocation.
    if not results:
        if skipped_done:
            # --resume where every requested role already had a valid final.
            print(f"All {len(skipped_done)} role(s) already complete for iter={iter_n}: "
                  f"{', '.join(skipped_done)}. Nothing to re-run.")
            print("Next: synthesize via `python ~/.claude/scripts/consilium-synth.py engagement/`")
            return 0
        if tier == "S" and args.consilium:
            print("S-tier: no adversary required. Skipping.")
            return 0
        print("No reviewer produced output.", file=sys.stderr)
        return 1

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    fail_count = sum(1 for r in results if r.get("status") == "fail")
    skip_count = sum(1 for r in results if r.get("status") == "skip")

    synth = final_state.get("synth_result")

    if args.json:
        payload = {
            "engagement": str(eng),
            "iter": iter_n,
            "invoker": invoker.name,
            "resumed": args.resume,
            "skipped_already_done": skipped_done,
            "ok": ok_count,
            "fail": fail_count,
            "skip": skip_count,
            "results": results,
        }
        if synth:
            payload["synth"] = synth
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Adversary run for engagement {eng.name} iter={iter_n} (invoker={invoker.name})")
        if skipped_done:
            print(f"  resumed — skipped (already complete): {', '.join(skipped_done)}")
        print(f"  ok={ok_count}  fail={fail_count}  skip={skip_count}")
        print()
        marks = {"ok": "[OK  ]", "fail": "[FAIL]", "skip": "[SKIP]"}
        for r in results:
            mark = marks.get(r.get("status", ""), "[????]")
            line = f"{mark} {r.get('role', '?')}"
            if r.get("status") == "ok":
                line += f"  verdict={r.get('verdict')}  findings={r.get('findings_count')}  ({r.get('elapsed_s')}s)"
                line += f"\n        -> {r.get('output_path')}"
            else:
                line += f"  {r.get('error', '')}"
            print(line)
        print()
        if synth and synth.get("status") == "ok":
            print(f"Synth: aggregate_verdict={synth.get('aggregate_verdict')}  "
                  f"unique_findings={synth.get('unique_findings')}")
            if synth.get("rationale"):
                print(f"       rationale: {synth['rationale']}")
            print(f"       -> {synth.get('summary_path')}")
        elif synth and synth.get("status") == "fail":
            print(f"Synth FAILED: {synth.get('error', '?')}")
            print("Next: try `python ~/.claude/scripts/consilium-synth.py engagement/` manually")
        else:
            # synth was skipped (single role, no ok results, --no-synth, etc.)
            print("Next: synthesize via `python ~/.claude/scripts/consilium-synth.py engagement/`")

    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
