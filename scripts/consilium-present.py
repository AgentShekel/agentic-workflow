#!/usr/bin/env python3
"""Format consilium-summary.md as chat-ready summary with decision menu.

For chat-driven supreme-judge flow: after consilium-synth.py writes
consilium-summary.md, this script outputs a compact human-readable summary
WITH the decision menu, ready to paste into chat. Coordinating agent invokes
this rather than dumping the full markdown summary.

Output is plain text (no markdown headers) so it renders cleanly in any chat.

Usage:
  python ~/.claude/scripts/consilium-present.py engagement/
  python ~/.claude/scripts/consilium-present.py engagement/ --max-findings 5
  python ~/.claude/scripts/consilium-present.py engagement/ --no-menu

Exit codes:
  0 — summary printed
  1 — consilium-summary.md missing (run consilium-synth.py first)
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
import re
import sys
from pathlib import Path


def read_iter_counter(eng: Path) -> int:
    counter = eng / "iteration"
    if counter.exists():
        try:
            return int(counter.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


def read_tier(eng: Path) -> str:
    crit = eng / "criteria.md"
    if not crit.exists():
        return "M"
    text = crit.read_text(encoding="utf-8")
    m = re.search(r"^size\s*:\s*(\S+)", text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip("\"'").upper()
    return "M"


def parse_summary(text: str) -> dict:
    """Extract structured info from consilium-summary.md."""
    result = {
        "aggregate_verdict": "",
        "rationale": "",
        "reviewer_count": 0,
        "reviewer_lines": [],
        "findings": [],
        "cross_family_disagreements": [],
        "intra_family_disagreements": [],
        "naive_catches": [],
        "too_clean": [],
        "stats_lines": [],
    }

    # Aggregate verdict + rationale
    m = re.search(r"\*\*Aggregate verdict:\*\*\s*(\S+)", text)
    if m:
        result["aggregate_verdict"] = m.group(1)
    m = re.search(r"\*\*Rationale:\*\*\s*(.+)", text)
    if m:
        result["rationale"] = m.group(1).strip()

    # Reviewer roster
    roster_match = re.search(
        r"##\s+Reviewer roster.*?\n\|.*?\n\|.*?\n((?:\|.*\n)+)",
        text, re.DOTALL,
    )
    if roster_match:
        for row in roster_match.group(1).strip().split("\n"):
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) >= 5:
                # | reviewer | tier | verdict | findings | summary |
                reviewer, rtier, verdict, count, summary = cells[:5]
                result["reviewer_lines"].append({
                    "reviewer": reviewer, "tier": rtier, "verdict": verdict,
                    "count": count, "summary": summary,
                })
        result["reviewer_count"] = len(result["reviewer_lines"])

    # Findings (with severity + reviewer attribution)
    findings_section = re.search(
        r"##\s+Findings.*?(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL,
    )
    if findings_section:
        body = findings_section.group(0)
        # Each "### N. **SEV** — issue"
        for m in re.finditer(
            r"^###\s+(\d+)\.\s+\*\*(\w+)\*\*\s+—\s+(.+?)\n((?:.*\n)*?)(?=^###|\Z)",
            body, re.MULTILINE,
        ):
            num, sev, issue, body_lines = m.groups()
            found_by = re.search(r"Found by:\s+([^\n]+?)\s*\((\d+)\s+reviewer", body_lines)
            evidence = re.search(r"Evidence:\s+`([^`]+)`", body_lines)
            result["findings"].append({
                "id": f"finding-{num}",
                "severity": sev.lower(),
                "issue": issue.strip(),
                "found_by": found_by.group(1) if found_by else "?",
                "reviewer_count": int(found_by.group(2)) if found_by else 1,
                "evidence": evidence.group(1) if evidence else None,
            })

    # Disagreements
    dis_match = re.search(
        r"##\s+Disagreements.*?(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL,
    )
    if dis_match:
        for line in dis_match.group(0).splitlines():
            cf = re.search(
                r"\*\*\[CROSS-FAMILY\]\*\*\s+(\S+)=(\S+)\s+vs\s+(\S+)=(\S+)", line,
            )
            if cf:
                result["cross_family_disagreements"].append({
                    "ra": cf.group(1), "va": cf.group(2),
                    "rb": cf.group(3), "vb": cf.group(4),
                })
                continue
            intra = re.search(
                r"\[intra-family\]\s+(\S+)=(\S+)\s+vs\s+(\S+)=(\S+)", line,
            )
            if intra:
                result["intra_family_disagreements"].append({
                    "ra": intra.group(1), "va": intra.group(2),
                    "rb": intra.group(3), "vb": intra.group(4),
                })

    # Naive-layer catches
    nl_match = re.search(
        r"##\s+Naive-layer catches.*?(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL,
    )
    if nl_match:
        for line in nl_match.group(0).splitlines():
            m = re.match(r"^-\s+\*\*(\w+)\*\*:\s+(.+)", line)
            if m:
                result["naive_catches"].append({
                    "severity": m.group(1).lower(),
                    "issue": m.group(2).strip(),
                })

    # Too-clean
    tc_match = re.search(
        r"##\s+Suspicious-too-clean flags.*?(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL,
    )
    if tc_match:
        m = re.search(r"Reviewer\(s\)\s+returned\s+0\s+findings:\s+([^\n.]+)", tc_match.group(0))
        if m:
            result["too_clean"] = [r.strip() for r in m.group(1).split(",")]

    # Statistics block
    stats_match = re.search(
        r"##\s+Statistics.*?(?=^##\s|\Z|---)", text, re.MULTILINE | re.DOTALL,
    )
    if stats_match:
        for line in stats_match.group(0).splitlines():
            line = line.strip()
            if line.startswith("- "):
                result["stats_lines"].append(line[2:])

    return result


def render_chat_summary(eng: Path, iter_n: int, tier: str, parsed: dict,
                        max_findings: int = 8, include_menu: bool = True) -> str:
    """Render parsed consilium as chat-ready text."""
    lines: list[str] = []
    lines.append(f"Consilium synthesis ready ({tier}-tier, iter {iter_n}):")
    lines.append("")

    # Aggregate verdict
    if parsed["aggregate_verdict"]:
        verdict_emoji = {
            "satisfied": "✓",
            "rework_required": "✗",
            "director_review_required": "?",
            "suspicious_too_clean": "?",
        }.get(parsed["aggregate_verdict"], "•")
        lines.append(f"  {verdict_emoji} Aggregate: {parsed['aggregate_verdict']}")
        if parsed["rationale"]:
            lines.append(f"     ({parsed['rationale']})")
        lines.append("")

    # Reviewers brief
    if parsed["reviewer_lines"]:
        lines.append(f"  Reviewers ({parsed['reviewer_count']}):")
        for r in parsed["reviewer_lines"]:
            verdict_short = {
                "satisfied": "OK",
                "rework_required": "REWORK",
                "suspicious_too_clean": "TOO-CLEAN",
            }.get(r["verdict"], r["verdict"])
            lines.append(f"    - {r['reviewer']:<18} → {verdict_short:<10} ({r['count']} findings)")
        lines.append("")

    # Critical findings (top by severity + reviewer count)
    if parsed["findings"]:
        critical_first = sorted(
            parsed["findings"],
            key=lambda f: (
                {"critical": 0, "major": 1, "minor": 2}.get(f["severity"], 3),
                -f["reviewer_count"],
            ),
        )
        shown = critical_first[:max_findings]
        lines.append(f"  Findings ({len(parsed['findings'])} unique, showing top {len(shown)}):")
        for f in shown:
            sev_short = f["severity"].upper()
            evidence_str = f" @ {f['evidence']}" if f.get("evidence") else ""
            convergent = " [CONVERGENT]" if f["reviewer_count"] >= 2 else ""
            lines.append(f"    [{sev_short}] {f['id']}: {f['issue']}{evidence_str}{convergent}")
            lines.append(f"           found by: {f['found_by']}")
        if len(parsed["findings"]) > max_findings:
            lines.append(f"    ... ({len(parsed['findings']) - max_findings} more — see consilium-summary.md)")
        lines.append("")

    # Cross-family disagreements (highest priority signal)
    if parsed["cross_family_disagreements"]:
        lines.append(f"  ⚠️  CROSS-FAMILY DISAGREEMENTS ({len(parsed['cross_family_disagreements'])}) — manual verification recommended:")
        for d in parsed["cross_family_disagreements"]:
            lines.append(f"    - {d['ra']}={d['va']} vs {d['rb']}={d['vb']}")
        lines.append("")

    # Naive-layer catches
    if parsed["naive_catches"]:
        lines.append(f"  Naive-layer catches ({len(parsed['naive_catches'])}) — only Sonnet/Haiku flagged:")
        for c in parsed["naive_catches"][:5]:
            lines.append(f"    [{c['severity'].upper()}] {c['issue']}")
        if len(parsed["naive_catches"]) > 5:
            lines.append(f"    ... ({len(parsed['naive_catches']) - 5} more)")
        lines.append("")

    # Too-clean flags
    if parsed["too_clean"]:
        lines.append(f"  Too-clean flags: {', '.join(parsed['too_clean'])}")
        lines.append("")

    # Stats
    if parsed["stats_lines"]:
        lines.append("  Statistics:")
        for s in parsed["stats_lines"][:5]:
            lines.append(f"    - {s}")
        lines.append("")

    lines.append(f"  Full detail: {eng}/consilium-summary.md")

    if include_menu:
        lines.append("")
        lines.append("  Your verdict — paste back ONE of:")
        lines.append("")
        lines.append("    PROCEED                — director writes formal verdict per consilium")
        lines.append("    REJECT: <reasons>      — minimal REJECT, lead reworks per your reasons")
        lines.append("    DIRECTED: <constraints>— director constrained by your specifics")
        lines.append("                              (e.g. \"address finding-1; SIDED WITH codex-blind on auth\")")
        lines.append("")
        lines.append("  Aliases: GO/OK = PROCEED, NO/RW = REJECT, MIXED/PARTIAL = DIRECTED.")
        lines.append("  Coordinating agent will invoke human-directive.py to scaffold the file.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Format consilium-summary.md as chat-ready summary")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--max-findings", type=int, default=8,
                        help="Max findings to show inline (default 8; rest reference summary file)")
    parser.add_argument("--no-menu", action="store_true",
                        help="Skip the decision menu at the end (just summary)")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    summary = eng / "consilium-summary.md"
    if not summary.exists():
        print(f"ERROR: {summary} not found. Run consilium-synth.py first.", file=sys.stderr)
        return 1

    iter_n = args.iter if args.iter is not None else read_iter_counter(eng)
    tier = read_tier(eng)
    text = summary.read_text(encoding="utf-8")
    parsed = parse_summary(text)

    print(render_chat_summary(eng, iter_n, tier, parsed,
                              max_findings=args.max_findings,
                              include_menu=not args.no_menu))
    return 0


if __name__ == "__main__":
    sys.exit(main())
