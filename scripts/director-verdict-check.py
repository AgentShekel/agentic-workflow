#!/usr/bin/env python3
"""Director verdict completeness check.

Verifies that director's `acceptance-log.md` verdict explicitly addresses
EVERY consilium signal from `consilium-summary.md`. Closes the
behavioral risk that director rubber-stamps consilium output without
adjudicating.

Required structure in director verdict (M/L tiers):
  ### Adversary findings adjudication
    - Convergent findings — each must have SUSTAINED | OVERRULED marker
    - Cross-family disagreements — each must have SIDED WITH … marker
    - Naive-layer catches — each must have REAL | FALSE_POSITIVE marker
    - Suspicious_too_clean flags — each must have ACKNOWLEDGED marker

Usage:
  python ~/.claude/scripts/director-verdict-check.py engagement/
  python ~/.claude/scripts/director-verdict-check.py engagement/ --json
  python ~/.claude/scripts/director-verdict-check.py engagement/ --iter 2

Exit codes:
  0 — verdict addresses all consilium signals
  1 — verdict missing one or more required adjudications
  2 — invocation error (missing engagement, no consilium-summary, no acceptance-log, etc.)
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

CRITERIA_FRONTMATTER_TIER_RE = re.compile(r"^size\s*:\s*(\S+)", re.MULTILINE)


def read_tier(eng: Path) -> str:
    crit = eng / "criteria.md"
    if not crit.exists():
        return "M"
    text = crit.read_text(encoding="utf-8")
    m = CRITERIA_FRONTMATTER_TIER_RE.search(text)
    if m:
        return m.group(1).strip().strip("\"'").upper()
    return "M"


def read_iter_counter(eng: Path) -> int:
    counter = eng / "iteration"
    if counter.exists():
        try:
            return int(counter.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


def parse_consilium_signals(consilium_text: str) -> dict:
    """Extract signals from consilium-summary.md that must be adjudicated."""
    signals = {
        "convergent": [],   # findings with ≥2 reviewers (high-confidence)
        "cross_family_disagreements": [],
        "naive_catches": [],
        "too_clean": [],
    }

    # Convergent findings — under "## Findings" section, count entries with ≥2 reviewers
    findings_section = re.search(
        r"^##\s+Findings.*?(?=^##\s|\Z)", consilium_text, re.MULTILINE | re.DOTALL
    )
    if findings_section:
        body = findings_section.group(0)
        # Each finding numbered "### N. **SEV** — issue"
        finding_blocks = re.findall(
            r"^###\s+(\d+)\.\s+\*\*(\w+)\*\*\s+—\s+(.+?)(?=^###|\Z)",
            body, re.MULTILINE | re.DOTALL
        )
        for num, sev, body_lines in finding_blocks:
            # "Found by: X, Y (N reviewer(s))"
            found_by = re.search(r"Found by:\s+([^\n]+?)\s*\((\d+)\s+reviewer", body_lines)
            if found_by:
                count = int(found_by.group(2))
                if count >= 2:
                    issue_line = body_lines.strip().split("\n")[0].strip()
                    signals["convergent"].append({
                        "id": f"finding-{num}",
                        "severity": sev.lower(),
                        "issue": issue_line[:80],
                        "found_by": found_by.group(1),
                    })

    # Cross-family disagreements
    cf_section = re.search(
        r"^##\s+Disagreements.*?(?=^##\s|\Z)", consilium_text, re.MULTILINE | re.DOTALL
    )
    if cf_section:
        for line in cf_section.group(0).splitlines():
            # "**[CROSS-FAMILY]** {ra}={va} vs {rb}={vb}"
            m = re.search(r"\*\*\[CROSS-FAMILY\]\*\*\s+(\S+)=(\S+)\s+vs\s+(\S+)=(\S+)", line)
            if m:
                signals["cross_family_disagreements"].append({
                    "reviewer_a": m.group(1),
                    "verdict_a": m.group(2),
                    "reviewer_b": m.group(3),
                    "verdict_b": m.group(4),
                })

    # Naive-layer catches
    nl_section = re.search(
        r"^##\s+Naive-layer catches.*?(?=^##\s|\Z)", consilium_text, re.MULTILINE | re.DOTALL
    )
    if nl_section:
        for line in nl_section.group(0).splitlines():
            m = re.match(r"^-\s+\*\*(\w+)\*\*:\s+(.+)", line)
            if m:
                signals["naive_catches"].append({
                    "severity": m.group(1).lower(),
                    "issue": m.group(2).strip()[:80],
                })

    # Suspicious_too_clean
    tc_section = re.search(
        r"^##\s+Suspicious-too-clean flags.*?(?=^##\s|\Z)", consilium_text, re.MULTILINE | re.DOTALL
    )
    if tc_section:
        m = re.search(r"Reviewer\(s\)\s+returned\s+0\s+findings:\s+([^\n.]+)", tc_section.group(0))
        if m:
            roles = [r.strip() for r in m.group(1).split(",")]
            signals["too_clean"] = roles

    return signals


def parse_director_adjudications(verdict_text: str) -> dict:
    """Extract adjudication markers from director's verdict text."""
    adj = {
        "convergent": [],     # list of {issue/id, marker} where marker in SUSTAINED | OVERRULED
        "cross_family": [],   # list of "SIDED WITH X" or "SPLIT"
        "naive": [],          # list of {issue, marker REAL | FALSE_POSITIVE}
        "too_clean": [],      # list of role names ACKNOWLEDGED
    }

    # Convergent: lines like "- {finding-1...}: SUSTAINED" or "OVERRULED"
    for m in re.finditer(
        r"-\s+(?:\*\*)?(?:finding-\d+|.+?)(?:\*\*)?[:\s]+(SUSTAINED|OVERRULED)\b",
        verdict_text, re.MULTILINE
    ):
        adj["convergent"].append({"marker": m.group(1).upper(), "context": m.group(0)[:120]})

    # Cross-family disagreements: "SIDED WITH X" or "SPLIT"
    for m in re.finditer(
        r"\bSIDED\s+WITH\s+(\S+?)\b|\bSPLIT\b",
        verdict_text, re.IGNORECASE
    ):
        adj["cross_family"].append({"context": m.group(0)})

    # Naive catches: "REAL" or "FALSE_POSITIVE"
    for m in re.finditer(
        r"\b(REAL|FALSE_POSITIVE|FALSE-POSITIVE)\b",
        verdict_text
    ):
        adj["naive"].append({"marker": m.group(1).upper().replace("-", "_")})

    # Too-clean: "ACKNOWLEDGED"
    for m in re.finditer(r"\bACKNOWLEDGED\b", verdict_text):
        adj["too_clean"].append({"context": "ACKNOWLEDGED"})

    return adj


def check_completeness(signals: dict, adj: dict) -> dict:
    """Check that adjudications cover all signals; return diagnostics."""
    issues = []
    pass_marks = []

    # Convergent: each must have SUSTAINED or OVERRULED somewhere
    if signals["convergent"]:
        if len(adj["convergent"]) < len(signals["convergent"]):
            issues.append(
                f"convergent findings: {len(signals['convergent'])} signals, "
                f"only {len(adj['convergent'])} SUSTAINED/OVERRULED markers in verdict"
            )
        else:
            pass_marks.append(f"convergent: {len(adj['convergent'])}/{len(signals['convergent'])} adjudicated")

    # Cross-family: each must have SIDED WITH or SPLIT
    if signals["cross_family_disagreements"]:
        if len(adj["cross_family"]) < len(signals["cross_family_disagreements"]):
            issues.append(
                f"cross-family disagreements: {len(signals['cross_family_disagreements'])} signals, "
                f"only {len(adj['cross_family'])} SIDED WITH/SPLIT markers"
            )
        else:
            pass_marks.append(f"cross-family: {len(adj['cross_family'])}/{len(signals['cross_family_disagreements'])} adjudicated")

    # Naive catches: each must have REAL or FALSE_POSITIVE
    if signals["naive_catches"]:
        if len(adj["naive"]) < len(signals["naive_catches"]):
            issues.append(
                f"naive-layer catches: {len(signals['naive_catches'])} signals, "
                f"only {len(adj['naive'])} REAL/FALSE_POSITIVE markers"
            )
        else:
            pass_marks.append(f"naive: {len(adj['naive'])}/{len(signals['naive_catches'])} adjudicated")

    # Too-clean: each role must have ACKNOWLEDGED
    if signals["too_clean"]:
        if len(adj["too_clean"]) < len(signals["too_clean"]):
            issues.append(
                f"too-clean flags: {len(signals['too_clean'])} reviewer(s), "
                f"only {len(adj['too_clean'])} ACKNOWLEDGED markers"
            )
        else:
            pass_marks.append(f"too-clean: {len(adj['too_clean'])}/{len(signals['too_clean'])} acknowledged")

    return {
        "complete": not issues,
        "issues": issues,
        "pass_marks": pass_marks,
        "signal_counts": {
            "convergent": len(signals["convergent"]),
            "cross_family": len(signals["cross_family_disagreements"]),
            "naive": len(signals["naive_catches"]),
            "too_clean": len(signals["too_clean"]),
        },
        "adjudication_counts": {
            "convergent": len(adj["convergent"]),
            "cross_family": len(adj["cross_family"]),
            "naive": len(adj["naive"]),
            "too_clean": len(adj["too_clean"]),
        },
    }


def get_iteration_verdict_block(log_text: str, iter_n: int) -> str:
    """Extract the verdict block for a specific iteration."""
    pattern = rf"^##\s*Iteration\s+{iter_n}\b.*?(?=^##\s+Iteration\s+\d+|\Z)"
    m = re.search(pattern, log_text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(0)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Director verdict completeness check")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    tier = read_tier(eng)
    if tier == "S":
        # S has no director phase, no consilium, no adjudication required
        result = {
            "engagement": str(eng),
            "tier": "S",
            "status": "skip",
            "detail": "S-tier has no director phase; verdict completeness check N/A",
        }
        print(json.dumps(result, indent=2) if args.json else f"[SKIP] S-tier: no director phase, check N/A")
        return 0

    iter_n = args.iter if args.iter is not None else read_iter_counter(eng)

    consilium_path = eng / "consilium-summary.md"
    log_path = eng / "acceptance-log.md"

    if not consilium_path.exists():
        result = {
            "engagement": str(eng), "tier": tier, "iter": iter_n,
            "status": "skip",
            "detail": "consilium-summary.md not present; run consilium-synth.py first",
        }
        print(json.dumps(result, indent=2) if args.json
              else f"[SKIP] consilium-summary.md missing — run consilium-synth.py first")
        return 0

    if not log_path.exists():
        result = {
            "engagement": str(eng), "tier": tier, "iter": iter_n,
            "status": "skip",
            "detail": "acceptance-log.md not present; director hasn't written verdict yet",
        }
        print(json.dumps(result, indent=2) if args.json
              else f"[SKIP] acceptance-log.md missing — director hasn't written verdict yet")
        return 0

    consilium_text = consilium_path.read_text(encoding="utf-8")
    log_text = log_path.read_text(encoding="utf-8")
    verdict_block = get_iteration_verdict_block(log_text, iter_n) or log_text

    signals = parse_consilium_signals(consilium_text)
    adj = parse_director_adjudications(verdict_block)
    result = check_completeness(signals, adj)
    result["engagement"] = str(eng)
    result["tier"] = tier
    result["iter"] = iter_n
    result["status"] = "pass" if result["complete"] else "fail"

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["complete"]:
            print(f"[PASS] director verdict addresses all consilium signals (tier={tier}, iter={iter_n})")
            for mark in result["pass_marks"]:
                print(f"  - {mark}")
        else:
            print(f"[FAIL] director verdict incomplete (tier={tier}, iter={iter_n})")
            for issue in result["issues"]:
                print(f"  - {issue}")
            print()
            print("Director must explicitly mark each consilium signal:")
            print("  - Convergent findings: SUSTAINED or OVERRULED")
            print("  - Cross-family disagreements: SIDED WITH <reviewer> or SPLIT")
            print("  - Naive-layer catches: REAL or FALSE_POSITIVE")
            print("  - Suspicious_too_clean flags: ACKNOWLEDGED")

    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
