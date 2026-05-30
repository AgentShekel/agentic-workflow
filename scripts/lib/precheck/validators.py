"""Validator-output checks: JSON sanity, verdicts, methodology, trace schema.

Two checks live here:
  - check_validator_outputs: every validator named in validation-log.md has
    a JSON output file with parseable JSON + verdict + (for numerical
    validators) methodology declaration. The biggest single check in
    handoff-precheck: ~130 lines including in-function constants.
  - check_trace_schema: delegate to trace-schema-check.py for ux_heavy
    traces/*.json validation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import run


# Validators that are recommended but not strictly required — missing output -> warn, not fail
OPTIONAL_VALIDATORS = {"test-reviewer", "documentation-reviewer", "prompt-reviewer", "feasibility-assessor"}


def check_validator_outputs(eng: Path) -> dict:
    """Every validator named in validation-log.md must have a JSON output file."""
    log = eng / "validation-log.md"
    if not log.exists():
        return {"name": "validator-outputs", "status": "skip", "detail": "validation-log.md not present"}
    text = log.read_text(encoding="utf-8")

    # Find every '### {name}' block. Validator agent names are lowercase-hyphenated
    # (code-reviewer, security-auditor, skeptic, ...); filtering to name.islower()
    # excludes prose section headings like "### Phase 6a" / "### Transport note"
    # that the bare regex would otherwise mis-count as phantom validators.
    blocks = [
        name
        for name in re.findall(
            r"^###\s+(?P<name>[\w\-./]+).*?(?=^###\s|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if name.islower()
    ]
    if not blocks:
        return {"name": "validator-outputs", "status": "skip", "detail": "no validators logged yet"}

    outputs_dir = eng / "validation-outputs"
    if not outputs_dir.exists():
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": f"{len(blocks)} validators logged but engagement/validation-outputs/ missing entirely — runs unverifiable",
            "fix": "Lead must capture each validator's JSON return into validation-outputs/{name}-iter-N-{timestamp}.json.",
        }

    # For each validator name, expect at least one matching output file
    files = list(outputs_dir.glob("*.json"))
    missing_critical = []
    missing_optional = []
    for name in set(blocks):
        if not any(f.name.startswith(name) for f in files):
            if name in OPTIONAL_VALIDATORS:
                missing_optional.append(name)
            else:
                missing_critical.append(name)

    if missing_critical:
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": f"required validators logged without output file: {missing_critical}",
            "fix": "Capture missing validator JSON returns into validation-outputs/.",
        }
    if missing_optional:
        return {
            "name": "validator-outputs",
            "status": "warn",
            "detail": f"optional validators logged without output file: {missing_optional} (not blocking, but recommended)",
            "fix": "Optional validators (test-reviewer, prompt-reviewer, etc.): capture if you ran them.",
        }

    # Sanity: each output file is parseable JSON AND has structural fields
    bad_json = []
    no_verdict = []
    bad_verdict = []
    no_methodology = []
    # Validator verdicts (methodology validators) + adversary verdicts (consilium roles).
    # Updated 2026-05-09 after agent-grep audit: collected ALL status values used by validator
    # agents (security, accessibility, code-reviewer, completeness, feasibility, pre/post-deploy,
    # test-reviewer, interview-checker, etc). Each validator emits ONE of these.
    valid_verdicts = {
        # Approval-style validators
        "approved", "approved_with_suggestions",
        # Rework-needed style
        "changes_required", "needs_improvement", "needs_more",
        # Hard block
        "blocked",
        # Binary check style
        "pass", "passed", "fail", "failed", "clean",
        # Coverage / gating
        "complete", "warning", "not_verifiable",
        # Adversary verdicts (consilium roles)
        "satisfied", "rework_required", "suspicious_too_clean",
        # canonical verdicts (validator_lg.canonicalize_validator_output)
        "approved_with_caveats", "suspicious", "skipped",
    }
    # Validators where methodology declaration is OBLIGATORY (numerical / formula-driven)
    methodology_required = {
        "accessibility-validator", "performance-validator", "security-auditor",
        "ux-review", "anti-pattern-detector",
    }
    # Adversary roles emit a different schema (preliminary/2-pass) — distinguish for checks
    adversary_roles = {
        "peer-opus", "codex-blind", "codex-informed", "sonnet-scoped", "haiku-scoped",
    }
    for f in files:
        # Skip Pass-1 preliminary files — they don't have a verdict (intentional)
        if "-preliminary-" in f.name:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            bad_json.append(f.name)
            continue
        verdict = data.get("verdict") or data.get("status")
        if verdict is None:
            no_verdict.append(f.name)
        elif str(verdict).lower() not in valid_verdicts:
            bad_verdict.append(f"{f.name}: verdict={verdict!r}")
        # Methodology declaration check — only for validators where it matters
        # Skip for adversary roles (their schema has _two_pass / _invocation instead)
        validator_name = data.get("validator", "") or data.get("reviewer_role", "") or f.stem.split("-iter-")[0]
        if validator_name in adversary_roles:
            continue
        if validator_name in methodology_required:
            if not data.get("methodology") and not data.get("metrics", {}).get("methodology"):
                no_methodology.append(f.name)

    problems = []
    warnings = []
    if bad_json:
        problems.append(f"unparseable JSON: {bad_json}")
    if no_verdict:
        problems.append(f"missing 'verdict' (or 'status') field: {no_verdict}")
    if bad_verdict:
        problems.append(f"invalid verdict values: {bad_verdict}")
    if no_methodology:
        warnings.append(f"missing 'methodology' field (formula/standard): {no_methodology}")

    if problems:
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": "; ".join(problems),
            "fix": "Each validator-output JSON needs a recognized 'verdict' (or 'status'): approved | approved_with_caveats | changes_required | blocked | satisfied | rework_required | suspicious | skipped (full vocabulary in validation-pipeline skill + validator_lg canonical map).",
        }
    if warnings:
        return {
            "name": "validator-outputs",
            "status": "warn",
            "detail": "; ".join(warnings),
            "fix": "Add 'methodology' field to numerical/formula-driven validator outputs (e.g. 'WCAG 2.1 luminance ratio 4.5:1'). Director needs this for re-run convergence.",
        }

    return {"name": "validator-outputs", "status": "pass", "detail": f"{len(set(blocks))} validators, {len(files)} output files, all valid JSON with verdict + methodology"}


def check_trace_schema(eng: Path, scripts_dir: Path, ux_heavy: str) -> dict:
    """Validate trace JSON files against schema. Skipped if ux_heavy=false or no traces."""
    if ux_heavy not in {"true", "minor"}:
        return {"name": "trace-schema", "status": "skip", "detail": f"ux_heavy={ux_heavy}, traces not applicable"}
    traces_dir = eng / "traces"
    if not traces_dir.exists() or not list(traces_dir.rglob("*.json")):
        if ux_heavy == "true":
            return {"name": "trace-schema", "status": "fail", "detail": "ux_heavy=true requires traces/ but none present"}
        return {"name": "trace-schema", "status": "skip", "detail": f"no traces (ux_heavy={ux_heavy} permits)"}
    code, out = run([sys.executable, str(scripts_dir / "trace-schema-check.py"), str(traces_dir), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "trace-schema", "status": "pass", "detail": f"{data.get('total', 0)} traces valid"}
        bad = [f["file"] for f in data.get("files", []) if f.get("status") == "fail"]
        return {
            "name": "trace-schema",
            "status": "fail",
            "detail": f"{data.get('fail_count')} traces violate schema: {bad}",
            "fix": "Conform traces to engagement-protocol §Trace JSON schema (action/selector/expected/observed/verdict).",
        }
    except json.JSONDecodeError:
        return {"name": "trace-schema", "status": "fail", "detail": f"trace-schema-check error: {out[:200]}"}
