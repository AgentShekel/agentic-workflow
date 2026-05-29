"""Multi-iteration discipline checks: counter, structure, freshness, ack.

Four checks live here:
  - check_iteration_counter: engagement/iteration file agrees with
    acceptance-log.md sections.
  - check_executor_iteration_structure: for iter >= 2, every executor-report
    must have `## Iteration N` heading (catches silent overwrites).
  - check_validator_output_freshness: for iter >= 2, validator-outputs must
    include at least one file from the current iteration.
  - check_specialist_criteria_ack: every executor-report opens with a
    Criteria acknowledgement section listing crit-N items.
"""

from __future__ import annotations

import re
from pathlib import Path


def check_iteration_counter(eng: Path) -> dict:
    """The iteration counter file must agree with acceptance-log.md sections."""
    counter = eng / "iteration"
    log = eng / "acceptance-log.md"

    if not counter.exists():
        # First handoff — counter expected = 1
        if not log.exists():
            return {"name": "iteration-counter", "status": "skip", "detail": "first handoff (no counter file yet, no acceptance-log yet — protocol allows missing counter on iter-1 first submit)"}
        return {
            "name": "iteration-counter", "status": "fail",
            "detail": "engagement/iteration file missing but acceptance-log.md exists",
            "fix": "Create engagement/iteration with current iter number per §iteration-counter.",
        }

    try:
        n = int(counter.read_text(encoding="utf-8").strip())
    except Exception as e:
        return {"name": "iteration-counter", "status": "fail", "detail": f"engagement/iteration not parseable as int: {e}"}

    if log.exists():
        log_iters = re.findall(r"^##\s*Iteration\s+(\d+)", log.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
        seen = sorted({int(x) for x in log_iters})
        # Counter should equal max(seen) + 1 (about to submit) OR equal max(seen) (latest already-rejected iter)
        if seen:
            expected = {max(seen), max(seen) + 1}
            if n not in expected:
                return {
                    "name": "iteration-counter", "status": "fail",
                    "detail": f"counter={n} but acceptance-log iterations={seen}; expected {expected}",
                    "fix": "Sync engagement/iteration to match latest acceptance-log iteration number (or +1 for new submission).",
                }
    return {"name": "iteration-counter", "status": "pass", "detail": f"counter={n}"}


def check_executor_iteration_structure(eng: Path) -> dict:
    """For iter >= 2, every executor-report must have a `## Iteration N` heading
    matching the current iteration. Catches silent overwrites of prior work."""
    counter_path = eng / "iteration"
    if not counter_path.exists():
        return {"name": "executor-iteration-structure", "status": "skip", "detail": "iter counter missing — first iteration"}
    try:
        n = int(counter_path.read_text(encoding="utf-8").strip())
    except Exception:
        return {"name": "executor-iteration-structure", "status": "skip", "detail": "iter counter unparseable"}
    if n < 2:
        return {"name": "executor-iteration-structure", "status": "skip", "detail": f"iter={n}, no iteration structure required yet"}

    reports_dir = eng / "executor-reports"
    if not reports_dir.exists():
        return {"name": "executor-iteration-structure", "status": "skip", "detail": "no executor-reports yet"}

    missing = []
    for report in reports_dir.glob("*.md"):
        text = report.read_text(encoding="utf-8")
        # Look for ANY iteration heading >= 2 (lead may have done iter 2 fix)
        has_iter_n = re.search(rf"^##\s*Iteration\s+{n}\b", text, re.MULTILINE | re.IGNORECASE)
        # Also require iter-1 marker (proves the file isn't a single-iteration silent overwrite)
        has_iter_1 = re.search(r"^##\s*Iteration\s+1\b", text, re.MULTILINE | re.IGNORECASE)
        if not has_iter_n or not has_iter_1:
            missing.append(report.name)

    if missing:
        return {
            "name": "executor-iteration-structure",
            "status": "fail",
            "detail": f"executor-reports missing `## Iteration {n}` (and/or `## Iteration 1`) heading: {missing}",
            "fix": "Append `## Iteration N` headings to each executor-report; do not silently overwrite prior iterations.",
        }
    return {"name": "executor-iteration-structure", "status": "pass", "detail": f"all executor-reports have iter-{n} structure"}


def check_validator_output_freshness(eng: Path) -> dict:
    """For iter >= 2, validator-outputs must contain at least one file with
    iter-N matching current iteration. Catches lead who forgot to re-run validators
    after rework, leaving stale iter-1 outputs as evidence."""
    counter_path = eng / "iteration"
    if not counter_path.exists():
        return {"name": "validator-output-freshness", "status": "skip", "detail": "iter counter missing — first iteration"}
    try:
        n = int(counter_path.read_text(encoding="utf-8").strip())
    except Exception:
        return {"name": "validator-output-freshness", "status": "skip", "detail": "iter counter unparseable"}
    if n < 2:
        return {"name": "validator-output-freshness", "status": "skip", "detail": f"iter={n}, freshness only meaningful from iter 2+"}

    outputs_dir = eng / "validation-outputs"
    if not outputs_dir.exists():
        return {"name": "validator-output-freshness", "status": "skip", "detail": "validation-outputs/ missing"}

    files = list(outputs_dir.glob("*.json"))
    if not files:
        return {"name": "validator-output-freshness", "status": "skip", "detail": "no validator output files"}

    # File names follow pattern: {validator}-iter-{N}-{ts}.json
    iter_pat = re.compile(r"-iter-(\d+)-")
    has_current_iter = False
    stale_only = []
    for f in files:
        m = iter_pat.search(f.name)
        if m and int(m.group(1)) == n:
            has_current_iter = True
        else:
            stale_only.append(f.name)

    if not has_current_iter:
        return {
            "name": "validator-output-freshness",
            "status": "fail",
            "detail": f"iter={n} but all validator-outputs are from prior iterations: {[f.name for f in files][:5]}",
            "fix": "Re-run validators for current iteration; capture new outputs as {validator}-iter-{N}-{timestamp}.json.",
        }

    return {"name": "validator-output-freshness", "status": "pass", "detail": f"validator outputs include iter-{n} files"}


def check_specialist_criteria_ack(eng: Path) -> dict:
    """Each executor-report must have a 'Criteria acknowledgement' section
    with at least one bullet. Catches specialists who skipped reading criteria.md."""
    reports_dir = eng / "executor-reports"
    if not reports_dir.exists() or not list(reports_dir.glob("*.md")):
        return {"name": "specialist-criteria-ack", "status": "skip", "detail": "no executor-reports yet"}

    missing = []
    for report in reports_dir.glob("*.md"):
        text = report.read_text(encoding="utf-8")
        # Headers like:
        #   ## Criteria acknowledgement
        #   ### Criteria acknowledgement
        #   ## Criteria
        #   ## Criterion mapping
        ack_pat = r"^#{2,4}\s*(Criteria(?:\s+acknowledgement|\s+addressed|\s+mapping)?|Criterion(?:\s+\w+)?)"
        if not re.search(ack_pat, text, re.MULTILINE | re.IGNORECASE):
            missing.append(report.name)
            continue
        # At least one bullet that mentions "crit-N" OR "criterion"
        bullets = re.findall(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", text, re.MULTILINE)
        has_crit_ref = any(re.search(r"\b(?:crit-?\d+|criterion\s*\d+|done[- ]when|criteria\.md)", b, re.IGNORECASE) for b in bullets)
        if not has_crit_ref:
            missing.append(f"{report.name} (section present, but no crit-N reference in bullets)")

    if missing:
        return {
            "name": "specialist-criteria-ack",
            "status": "fail",
            "detail": f"executor-reports without Criteria acknowledgement: {missing}",
            "fix": "Each specialist's report must open with `## Criteria acknowledgement` listing crit-N items their work addresses (per Engagement-mode contract).",
        }
    return {"name": "specialist-criteria-ack", "status": "pass", "detail": f"all {len(list(reports_dir.glob('*.md')))} executor-reports have criteria-ack"}
