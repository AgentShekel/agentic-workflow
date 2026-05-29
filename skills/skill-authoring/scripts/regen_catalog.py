#!/usr/bin/env python3
"""
Regenerate ~/.claude/SKILLS.md from frontmatter of all skills.

Reads every ~/.claude/skills/*/SKILL.md, extracts `name`, `description`, `domain`
from YAML frontmatter, and rewrites the auto-generated section in SKILLS.md.

The auto section is delimited by:
    <!-- SKILLS_INDEX:START -->
    ...auto-generated content...
    <!-- SKILLS_INDEX:END -->

Everything outside those markers is preserved. If markers are missing, the
script exits with an error message — add them manually to SKILLS.md first.

Usage:
    python regen_catalog.py

Exit codes:
    0 — regenerated successfully
    1 — SKILLS.md missing or markers not found
    2 — one or more skills missing `domain:` field (catalog still written, warning only)
"""

import re
import sys
from pathlib import Path
from datetime import date

SKILLS_DIR = Path.home() / ".claude" / "skills"
CATALOG_PATH = Path.home() / ".claude" / "SKILLS.md"

START_MARKER = "<!-- SKILLS_INDEX:START -->"
END_MARKER = "<!-- SKILLS_INDEX:END -->"

DOMAINS = {
    "marketing": ("A. Marketing", "Marketing-director orchestrates SEO, AI visibility, Yandex analytics, semantic drift."),
    "dev":       ("B. Development", "Dev-director runs feature lifecycle: specs, code, QA, infrastructure, project management."),
    "design":    ("C. Design",  "Design-director covers brand, design system, UI, assets, presentations."),
    "meta":      ("D. Meta",    "System maintenance: skill creation, testing, prompt engineering."),
}


def extract_field(block, field):
    """Extract a scalar or pipe-block value from YAML frontmatter text."""
    m = re.search(rf'^{field}:\s*\|\s*\n((?:[ \t]+.*\n?)+)', block, re.MULTILINE)
    if m:
        lines = [ln.strip() for ln in m.group(1).splitlines()]
        return " ".join(ln for ln in lines if ln)
    m = re.search(rf'^{field}:\s*(.+?)$', block, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return None


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    return {
        "name": extract_field(block, "name"),
        "description": extract_field(block, "description"),
        "domain": extract_field(block, "domain"),
        "folder": path.parent.name,
    }


def short_description(desc, max_len=140):
    if not desc:
        return ""
    first = re.split(r'(?<=[.!?])\s', desc, maxsplit=1)[0]
    if len(first) > max_len:
        first = first[:max_len].rsplit(" ", 1)[0] + "…"
    return first


def build_index(skills):
    by_domain = {}
    unassigned = []
    for s in skills:
        d = s.get("domain")
        if d in DOMAINS:
            by_domain.setdefault(d, []).append(s)
        else:
            unassigned.append(s)

    lines = []
    for key, (title, subtitle) in DOMAINS.items():
        entries = sorted(by_domain.get(key, []), key=lambda x: x["folder"])
        if not entries:
            continue
        lines.append("")
        lines.append(f"### {title} ({len(entries)})")
        lines.append("")
        lines.append(subtitle)
        lines.append("")
        for e in entries:
            lines.append(f"- `{e['folder']}` — {short_description(e['description'])}")

    if unassigned:
        lines.append("")
        lines.append(f"### WARN Unassigned ({len(unassigned)})")
        lines.append("")
        lines.append(
            "Missing `domain:` in frontmatter. Add one of: "
            + ", ".join(DOMAINS.keys())
        )
        lines.append("")
        for e in sorted(unassigned, key=lambda x: x["folder"]):
            lines.append(f"- `{e['folder']}`")

    return "\n".join(lines)


def main():
    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog not found: {CATALOG_PATH}", file=sys.stderr)
        sys.exit(1)

    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md)
        if fm:
            skills.append(fm)

    index_md = build_index(skills)

    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'({re.escape(START_MARKER)}).*?({re.escape(END_MARKER)})',
        re.DOTALL,
    )
    if not pattern.search(catalog):
        print(
            f"ERROR: markers not found in {CATALOG_PATH}.\n"
            f"Add these around the domains section before running:\n"
            f"  {START_MARKER}\n"
            f"  {END_MARKER}",
            file=sys.stderr,
        )
        sys.exit(1)

    today = date.today().isoformat()
    count_valid = sum(1 for s in skills if s.get("domain") in DOMAINS)
    unassigned_count = len(skills) - count_valid

    new_block = (
        f"{START_MARKER}\n"
        f"<!-- AUTO-GENERATED: regenerate via `python ~/.claude/skills/skill-authoring/scripts/regen_catalog.py` -->\n"
        f"<!-- Last regenerated: {today} | Skills: {len(skills)} -->\n"
        f"{index_md}\n\n"
        f"{END_MARKER}"
    )

    new_catalog = pattern.sub(new_block, catalog)
    CATALOG_PATH.write_text(new_catalog, encoding="utf-8")

    print(f"[ok] {CATALOG_PATH} regenerated")
    print(f"     {len(skills)} skills total, {count_valid} with valid domain")
    if unassigned_count:
        print(f"[warn] {unassigned_count} skills missing/invalid domain:")
        for s in skills:
            if s.get("domain") not in DOMAINS:
                print(f"       - {s['folder']}  domain={s.get('domain')!r}")
        sys.exit(2)


if __name__ == "__main__":
    main()
