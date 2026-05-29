"""Director-side acceptance artefact checks.

Four checks live here:
  - check_acceptance_log_paths: paths cited in acceptance-log.md exist
    (criteria-trace evidence). Delegates to handoff-paths-check.py.
  - check_verdict_canonical: acceptance-log.md uses canonical
    `### Verdict: ACCEPT|REJECT|ABORTED` format; warn on legacy forms.
  - check_human_directive: human-directive.md present + parseable Decision
    line, gated on consilium-summary.md existing.
  - check_director_verdict: delegate to director-verdict-check.py for
    consilium-signal adjudication completeness.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import run


HUMAN_DIRECTIVE_DECISIONS = {"PROCEED_TO_VERDICT", "REJECT_NOW", "DIRECTED_VERDICT"}


def check_acceptance_log_paths(eng: Path, scripts_dir: Path) -> dict:
    """Verify paths cited in acceptance-log.md exist (criteria-trace evidence)."""
    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": "acceptance-log-paths", "status": "skip", "detail": "acceptance-log.md not yet written"}
    text = log.read_text(encoding="utf-8")
    if "Verdict: ACCEPT" not in text:
        return {"name": "acceptance-log-paths", "status": "skip", "detail": "no ACCEPT verdict yet — only relevant after director writes ACCEPT"}
    code, out = run([sys.executable, str(scripts_dir / "handoff-paths-check.py"), str(log), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "acceptance-log-paths", "status": "pass", "detail": f"{data.get('total_cited', 0)} cited paths in ACCEPT verdict exist"}
        missing = [p["path"] for p in data.get("paths", []) if not p.get("exists")]
        return {"name": "acceptance-log-paths", "status": "fail", "detail": f"phantom paths in ACCEPT criteria trace: {missing}"}
    except json.JSONDecodeError:
        return {"name": "acceptance-log-paths", "status": "fail", "detail": f"check script error (exit {code}): {out[:200]}"}


def check_verdict_canonical(eng: Path) -> dict:
    """Acceptance-log must contain canonical `### Verdict: ACCEPT|REJECT|ABORTED`.

    Legacy formats (`**ACCEPTED**`, `# Verdict: ACCEPT — ...`, "engagement is CLOSED")
    are still accepted by archive script for backward compat, but new engagements
    MUST write the canonical form so machine-parsers stay reliable. WARN on legacy.
    """
    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": "verdict-canonical", "status": "skip", "detail": "acceptance-log.md not yet written"}
    text = log.read_text(encoding="utf-8")

    canonical = re.search(r"^###\s+Verdict:\s+(ACCEPT|REJECT|ABORTED)\b", text, re.MULTILINE)
    if canonical:
        return {"name": "verdict-canonical", "status": "pass", "detail": f"canonical verdict found: {canonical.group(1)}"}

    # Detect legacy forms — these still archive (Tier 11.1 flexibility) but signal drift
    legacy_patterns = [
        (r"^\*\*ACCEPTED?\*\*", "**ACCEPTED**"),
        (r"^Verdict[:\s]+ACCEPT(?:ED)?", "Verdict: ACCEPTED"),
        (r"^#\s+Verdict:", "# Verdict (H1 instead of H3)"),
        (r"^##\s+Verdict\s*$", "## Verdict (no body)"),
        (r"engagement\s+\S+\s+is\s+\*?\*?CLOSED", "engagement is CLOSED"),
    ]
    for pat, label in legacy_patterns:
        if re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            return {
                "name": "verdict-canonical",
                "status": "warn",
                "detail": f"legacy verdict format detected ({label}); canonical is `### Verdict: ACCEPT|REJECT|ABORTED`",
                "fix": "Director: write `### Verdict: ACCEPT` (or REJECT / ABORTED) on its own line. Archive still works on legacy, but machine-readability degrades.",
            }

    return {
        "name": "verdict-canonical",
        "status": "fail",
        "detail": "acceptance-log.md exists but no parseable verdict found",
        "fix": "Director must write `### Verdict: ACCEPT|REJECT|ABORTED`.",
    }


def check_human_directive(eng: Path) -> dict:
    """Verify human-directive.md presence and structure for M/L tiers.

    Flow: after consilium-synth.py produces consilium-summary.md, human reads
    it and writes human-directive.md with one of three decisions. Director
    then writes verdict per directive.

    Skipped if consilium-summary.md doesn't exist yet (consilium hasn't run).
    """
    consilium = eng / "consilium-summary.md"
    directive = eng / "human-directive.md"
    log = eng / "acceptance-log.md"

    if not consilium.exists():
        return {"name": "human-directive", "status": "skip", "detail": "consilium-summary.md missing — consilium not yet run"}

    if not directive.exists():
        # If acceptance-log.md exists, director wrote verdict without directive — fail
        if log.exists():
            return {
                "name": "human-directive",
                "status": "fail",
                "detail": "consilium ran but human-directive.md absent AND director already wrote verdict",
                "fix": "Per protocol: human reads consilium-summary.md, writes human-directive.md (PROCEED_TO_VERDICT | REJECT_NOW | DIRECTED_VERDICT), THEN director writes verdict. Director skipped human-judge step.",
            }
        return {"name": "human-directive", "status": "skip", "detail": "consilium done; awaiting human directive (this is normal mid-acceptance)"}

    text = directive.read_text(encoding="utf-8")
    decision_match = re.search(r"^Decision:\s*(\w+)", text, re.MULTILINE)
    if not decision_match:
        return {
            "name": "human-directive",
            "status": "fail",
            "detail": "human-directive.md present but no parseable `Decision:` line",
            "fix": "human-directive.md must include a line `Decision: PROCEED_TO_VERDICT | REJECT_NOW | DIRECTED_VERDICT`.",
        }
    decision = decision_match.group(1).upper().strip()
    if decision not in HUMAN_DIRECTIVE_DECISIONS:
        return {
            "name": "human-directive",
            "status": "fail",
            "detail": f"human-directive.md Decision={decision} not in {sorted(HUMAN_DIRECTIVE_DECISIONS)}",
            "fix": f"Set Decision to one of {sorted(HUMAN_DIRECTIVE_DECISIONS)}.",
        }
    return {"name": "human-directive", "status": "pass", "detail": f"directive present, Decision={decision}"}


def check_director_verdict(eng: Path, scripts_dir: Path) -> dict:
    """Run director-verdict-check.py — verify director adjudicated all consilium signals.

    Skipped if acceptance-log.md doesn't exist yet (director hasn't written) or
    consilium-summary.md doesn't exist (M/L acceptance hasn't run consilium yet).
    """
    checker = scripts_dir / "director-verdict-check.py"
    if not checker.exists():
        return {"name": "director-verdict", "status": "skip", "detail": "director-verdict-check.py not installed"}
    code, out = run([sys.executable, str(checker), str(eng), "--json"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"name": "director-verdict", "status": "skip", "detail": f"checker output unparseable: {out[:160]}"}
    status = data.get("status", "skip")
    if status == "skip":
        return {"name": "director-verdict", "status": "skip", "detail": data.get("detail", "")}
    if status == "fail":
        return {
            "name": "director-verdict",
            "status": "fail",
            "detail": "; ".join(data.get("issues", []))[:200],
            "fix": "Director must mark each consilium signal in acceptance-log.md: SUSTAINED/OVERRULED for convergent, SIDED WITH X for cross-family disagreements, REAL/FALSE_POSITIVE for naive catches, ACKNOWLEDGED for too-clean flags.",
        }
    return {"name": "director-verdict", "status": "pass", "detail": "all consilium signals adjudicated"}
