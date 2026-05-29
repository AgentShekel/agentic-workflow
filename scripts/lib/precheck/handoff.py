"""Handoff.md content checks: structure, cited paths, cross-val, §7, slot lang.

Five checks live here:
  - check_handoff_paths: delegate to handoff-paths-check.py.
  - check_handoff_sections: required numbered sections present.
  - check_cross_val_quotes: delegate to cross-val-check.py for §4a verbatim
    quotes verification.
  - check_self_acceptance_thinness: §7 has tagged concerns at threshold count.
  - check_slot_language: ban "slot N of M" / "last attempt" / "final round"
    language anywhere in text artefacts; counter is informational only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import run


# Required numbered sections in handoff.md (M/L baseline). S-tier subset
# computed inline in check_handoff_sections.
REQUIRED_HANDOFF_SECTIONS = {
    1: r"^##\s*1\.\s*Diff\s*summary",
    2: r"^##\s*2\.\s*Deliverable",
    3: r"^##\s*3\.\s*Criteria\s*trace",
    4: r"^##\s*4\.\s*Executor\s*reports",
    5: r"^##\s*5\.\s*Validation\s*log",
    7: r"^##\s*7\.\s*Self-acceptance",
    8: r"^##\s*8\.\s*Deploy",
    11: r"^##\s*11\.\s*Known\s*deferrals",
}

UX_HEAVY_SECTION_6 = r"^##\s*6\.\s*Exercised"


# Banned phrases that pressure premature accepts. Escalation must be
# root-cause based, not counter-based; the counter is informational only.
SLOT_LANGUAGE_PATTERNS = [
    r"(?i)\bslot\s+\d+\s*(?:of|/)\s*\d+\b",
    r"(?i)\biteration\s+\d+\s*(?:of|/)\s*\d+\b",
    r"(?i)\blast\s+(?:attempt|round|iteration|chance)\b",
    r"(?i)\bfinal\s+(?:round|attempt|iteration)\b",
    r"(?i)\bout\s+of\s+(?:retries|attempts|iterations)\b",
    r"(?i)\bburning\s+(?:iteration|round|budget)\b",
    r"(?i)\biteration\s+budget\s+(?:exhausted|used\s+up)\b",
    r"(?i)\bпоследн(?:ий|яя|ее)\s+(?:попытк|итераци|раунд|шанс)",
    r"(?i)\bкруги?\s+(?:закончил|исчерпан)",
]

SCANNED_FILES = ["handoff.md", "acceptance-log.md", "scope-sync.md", "validation-log.md"]

# Lines that legitimately cite the ban itself (quoting protocol) -> context-aware skip
SLOT_QUOTE_HINTS = re.compile(
    r"(?i)("
    r"^\s*>"                              # markdown blockquote
    r"|banned"
    r"|forbidden"
    r"|запрещ"
    r"|don'?t\s+(?:write|use)"
    r"|do\s+NOT\s+(?:write|use)"
    r"|anti[- ]?pattern"
    r"|not\s+allowed"
    r"|example\s+of\s+slot"
    r"|пример\s+slot"
    r")"
)


def check_handoff_paths(eng: Path, scripts_dir: Path) -> dict:
    handoff = eng / "handoff.md"
    if not handoff.exists():
        return {"name": "handoff-paths", "status": "skip", "detail": "handoff.md not yet written"}
    code, out = run([sys.executable, str(scripts_dir / "handoff-paths-check.py"), str(handoff), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "handoff-paths", "status": "pass", "detail": f"{data.get('total_cited', 0)} cited paths exist"}
        missing = [p["path"] for p in data.get("paths", []) if not p.get("exists")]
        return {"name": "handoff-paths", "status": "fail", "detail": f"missing paths: {missing}"}
    except json.JSONDecodeError:
        return {"name": "handoff-paths", "status": "fail", "detail": f"check script error (exit {code}): {out[:200]}"}


def check_handoff_sections(eng: Path, size: str = "M") -> dict:
    handoff = eng / "handoff.md"
    if not handoff.exists():
        return {"name": "handoff-sections", "status": "skip", "detail": "handoff.md not yet written"}
    text = handoff.read_text(encoding="utf-8")

    # S-tier: only §1 + §2 (deliverables/criteria-trace can be merged) + §5 + §7 required
    if size == "S":
        s_required = {1: REQUIRED_HANDOFF_SECTIONS[1], 2: REQUIRED_HANDOFF_SECTIONS[2],
                      5: REQUIRED_HANDOFF_SECTIONS[5], 7: REQUIRED_HANDOFF_SECTIONS[7]}
        missing = [f"§{n}" for n, pat in s_required.items()
                   if not re.search(pat, text, re.MULTILINE | re.IGNORECASE)]
        if missing:
            return {"name": "handoff-sections", "status": "fail",
                    "detail": f"S-tier missing minimum sections: {missing}",
                    "fix": "S-tier needs only §1 (Diff), §2 (Deliverables+criteria-trace inline), §5 (Validation log), §7 (Self-acceptance >=1 concern)."}
        return {"name": "handoff-sections", "status": "pass",
                "detail": f"S-tier minimum sections present (§1, §2, §5, §7); ux_heavy={size}"}

    missing = []
    for n, pat in REQUIRED_HANDOFF_SECTIONS.items():
        if not re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            missing.append(f"§{n}")

    # Docs diff §9 mandatory for size M/L when src/ touched
    docs_pat = r"^##\s*9\.\s*Docs\s*diff"
    if size in {"M", "L"} and re.search(r"src/", text):
        if not re.search(docs_pat, text, re.MULTILINE | re.IGNORECASE):
            missing.append("§9 (Docs diff, mandatory for size=M/L when src/ touched)")

    # ux_heavy -> §6 mandatory for minor and true
    crit_path = eng / "criteria.md"
    ux_heavy = "false"
    if crit_path.exists():
        crit_text = crit_path.read_text(encoding="utf-8")
        m = re.search(r"^ux_heavy\s*:\s*(true|false|minor)", crit_text, re.MULTILINE | re.IGNORECASE)
        if m:
            ux_heavy = m.group(1).lower()
    if ux_heavy in {"true", "minor"} and not re.search(UX_HEAVY_SECTION_6, text, re.MULTILINE | re.IGNORECASE):
        missing.append(f"§6 (Exercised, required for ux_heavy={ux_heavy})")

    if missing:
        return {"name": "handoff-sections", "status": "fail", "detail": f"missing sections: {missing}"}
    return {"name": "handoff-sections", "status": "pass", "detail": f"all required sections present (ux_heavy={ux_heavy})"}


def check_cross_val_quotes(eng: Path, scripts_dir: Path, size: str) -> dict:
    """Verify §4a verbatim quotes exist in cited files. Skipped for size=S."""
    handoff = eng / "handoff.md"
    if not handoff.exists():
        return {"name": "cross-val-quotes", "status": "skip", "detail": "handoff.md not yet written"}
    if size == "S":
        return {"name": "cross-val-quotes", "status": "skip", "detail": "size=S, cross-val table not required"}
    code, out = run([sys.executable, str(scripts_dir / "cross-val-check.py"), str(handoff), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "cross-val-quotes", "status": "pass", "detail": f"{len(data.get('quotes', []))} quotes verified"}
        if data.get("status") == "partial":
            return {"name": "cross-val-quotes", "status": "pass", "detail": f"{data.get('partial_count')} loose-matches; verify by hand if pivotal"}
        return {
            "name": "cross-val-quotes",
            "status": "fail",
            "detail": f"phantom quotes: {data.get('fail_count')}",
            "fix": "Each §4a verbatim quote must exist verbatim in cited executor-report at-or-near cited line.",
        }
    except json.JSONDecodeError:
        return {"name": "cross-val-quotes", "status": "fail", "detail": f"cross-val-check error: {out[:200]}"}


def check_self_acceptance_thinness(eng: Path, size: str) -> dict:
    """§7 must have a concerns sublist with criteria-tagged items.

    Per engagement-protocol §7b:
      Format: '1. [crit-N | non-criteria | scope-creep] {concern}: {body}'
      Threshold: S=1, M=2, L=2.
      Tag distribution: at least one crit-N OR scope-creep tag (non-criteria capped at 1).
    """
    handoff = eng / "handoff.md"
    if not handoff.exists():
        return {"name": "self-acceptance-thinness", "status": "skip", "detail": "handoff.md not yet written"}
    text = handoff.read_text(encoding="utf-8")
    m = re.search(r"^##\s*7\.\s*Self-acceptance.*?(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not m:
        return {"name": "self-acceptance-thinness", "status": "fail", "detail": "§7 block missing"}
    block = m.group(0)

    # Pull only tagged concerns; older format (no tag) treated as non-criteria
    concern_lines = re.findall(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", block, re.MULTILINE)
    concern_lines = [c for c in concern_lines if not c.strip().startswith(("$", "`", "{"))]

    crit_tagged = sum(1 for c in concern_lines if re.search(r"\[crit-\d+\]", c, re.IGNORECASE))
    non_crit_tagged = sum(1 for c in concern_lines if "[non-criteria]" in c.lower())
    scope_creep_tagged = sum(1 for c in concern_lines if "[scope-creep]" in c.lower())
    untagged = len(concern_lines) - crit_tagged - non_crit_tagged - scope_creep_tagged

    threshold = 1 if size == "S" else 2

    if len(concern_lines) < threshold:
        return {
            "name": "self-acceptance-thinness",
            "status": "fail",
            "detail": f"§7 has {len(concern_lines)} concerns, threshold {threshold} for size={size}",
            "fix": f"Add concerns until >={threshold} per protocol §7b.",
        }

    if crit_tagged == 0 and scope_creep_tagged == 0:
        return {
            "name": "self-acceptance-thinness",
            "status": "fail",
            "detail": f"§7 concerns ducked criteria entirely (0 crit-N, 0 scope-creep, {non_crit_tagged} non-criteria, {untagged} untagged)",
            "fix": "At least one concern must be tagged [crit-N] OR [scope-creep] per §7b. Non-criteria filler doesn't count.",
        }

    if non_crit_tagged > 1:
        return {
            "name": "self-acceptance-thinness",
            "status": "fail",
            "detail": f"§7 has {non_crit_tagged} [non-criteria] concerns (cap is 1)",
            "fix": "Replace extra [non-criteria] concerns with [crit-N] or [scope-creep] tagged ones.",
        }

    return {
        "name": "self-acceptance-thinness",
        "status": "pass",
        "detail": f"{len(concern_lines)} concerns ({crit_tagged} crit, {scope_creep_tagged} scope-creep, {non_crit_tagged} non-criteria, {untagged} untagged), threshold {threshold} for size={size}",
    }


def check_slot_language(eng: Path) -> dict:
    """Scan text artefacts for banned slot/last-attempt language.

    Slot language pressures premature accepts. Per protocol, escalation is
    root-cause based, not counter-based. Counter is informational only.
    Context-aware: lines quoting the protocol's ban itself are skipped.
    """
    findings = []
    for fname in SCANNED_FILES:
        f = eng / fname
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            # Skip lines that legitimately quote/explain the ban
            if SLOT_QUOTE_HINTS.search(line):
                continue
            for pat in SLOT_LANGUAGE_PATTERNS:
                if re.search(pat, line):
                    findings.append(f"{fname}:L{line_no}: {line.strip()[:80]}")
                    break
    if findings:
        return {
            "name": "slot-language",
            "status": "fail",
            "detail": f"slot/last-attempt language: {findings[:5]}{' ...' if len(findings) > 5 else ''}",
            "fix": "Slot language banned per protocol. Counter is informational; escalation is root-cause based. Rephrase or remove.",
        }
    return {"name": "slot-language", "status": "pass", "detail": "no banned slot/last-attempt language"}
