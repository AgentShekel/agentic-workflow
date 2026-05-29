#!/usr/bin/env python3
"""
Lint a proposed or existing skill for collisions with the rest of the portfolio.

Checks:
  1. Required frontmatter fields (name, description, domain)
  2. Valid domain value (one of the allowed set)
  3. Name collision with existing skill folders
  4. Trigger-phrase overlap with existing skills (Jaccard similarity on keywords)

Usage:
    # Lint a SKILL.md file (existing or draft)
    python lint_skill.py --file path/to/SKILL.md

    # Lint a proposed skill inline
    python lint_skill.py --name my-skill --domain meta --description "Does X..."

    # Lint ALL existing skills in ~/.claude/skills/ (for portfolio health check)
    python lint_skill.py --all

Exit codes:
    0 — clean
    1 — warnings only (overlap above threshold)
    2 — errors (missing field, collision, invalid domain)
"""

import argparse
import re
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"
VALID_DOMAINS = {"marketing", "dev", "design", "meta"}

OVERLAP_WARN = 0.30
STOPWORDS = {
    "this", "that", "with", "from", "when", "used", "use", "uses", "using",
    "skill", "skills", "task", "tasks", "tool", "tools", "work", "works",
    "create", "creates", "design", "designs", "build", "builds", "ready",
    "through", "which", "where", "about", "also", "into", "based",
    "работа", "работы", "например", "через", "можно", "нужно", "после",
    "перед", "будет", "чтобы", "можно", "этого", "этот", "этом", "этой",
}


def extract_field(block, field):
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


def extract_keywords(text):
    if not text:
        return set()
    tokens = re.findall(r'[a-zа-я0-9-]{4,}', text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_other_skills(exclude_folder=None):
    """Read frontmatter of all existing skills, optionally excluding one folder."""
    out = []
    if not SKILLS_DIR.exists():
        return out
    for d in SKILLS_DIR.iterdir():
        if not d.is_dir() or d.name == exclude_folder:
            continue
        smd = d / "SKILL.md"
        if not smd.exists():
            continue
        fm = parse_frontmatter(smd)
        if fm:
            out.append(fm)
    return out


def lint(name, description, domain, folder_hint=None):
    errors, warnings = [], []

    folder_name = folder_hint or (name.replace("ckm:", "").strip() if name else None)

    if not name:
        errors.append("missing frontmatter field: name")
    if not description:
        errors.append("missing frontmatter field: description")
    if not domain:
        errors.append(
            f"missing frontmatter field: domain (add one of: {sorted(VALID_DOMAINS)})"
        )
    elif domain not in VALID_DOMAINS:
        errors.append(
            f"invalid domain: {domain!r} (valid: {sorted(VALID_DOMAINS)})"
        )

    if folder_name:
        for other_dir in SKILLS_DIR.iterdir() if SKILLS_DIR.exists() else []:
            if not other_dir.is_dir():
                continue
            if other_dir.name == folder_name and other_dir.name != folder_hint:
                errors.append(
                    f"name collision: folder '{other_dir.name}' already exists"
                )

    if description:
        kw = extract_keywords(description)
        if kw:
            matches = []
            for other in load_other_skills(exclude_folder=folder_hint):
                other_kw = extract_keywords(other.get("description"))
                sim = jaccard(kw, other_kw)
                if sim >= OVERLAP_WARN:
                    matches.append((other["folder"], sim))
            matches.sort(key=lambda x: -x[1])
            for other_name, sim in matches[:3]:
                warnings.append(
                    f"trigger overlap {sim:.0%} with existing skill '{other_name}' "
                    f"(check if purposes really differ)"
                )

    return errors, warnings


def print_report(target, errors, warnings):
    if errors:
        print(f"[FAIL] {target}")
        for e in errors:
            print(f"   error: {e}")
    elif warnings:
        print(f"[WARN] {target}")
    else:
        print(f"[ OK ] {target}")
    for w in warnings:
        print(f"   warn: {w}")


def main():
    parser = argparse.ArgumentParser(description="Lint a skill for portfolio collisions.")
    parser.add_argument("--file", help="Path to SKILL.md to lint")
    parser.add_argument("--name", help="Skill name (use with --description)")
    parser.add_argument("--description", help="Skill description text")
    parser.add_argument("--domain", help="Skill domain slug")
    parser.add_argument("--all", action="store_true", help="Lint all existing skills")
    args = parser.parse_args()

    total_errors = 0
    total_warnings = 0

    if args.all:
        for d in sorted(SKILLS_DIR.iterdir()):
            if not d.is_dir():
                continue
            smd = d / "SKILL.md"
            if not smd.exists():
                continue
            fm = parse_frontmatter(smd)
            if not fm:
                print_report(d.name, ["no parsable frontmatter"], [])
                total_errors += 1
                continue
            errors, warnings = lint(
                fm.get("name"), fm.get("description"), fm.get("domain"),
                folder_hint=d.name,
            )
            print_report(d.name, errors, warnings)
            total_errors += len(errors)
            total_warnings += len(warnings)

    elif args.file:
        path = Path(args.file).expanduser().resolve()
        fm = parse_frontmatter(path)
        if not fm:
            print(f"[FAIL] {path}: no parsable frontmatter", file=sys.stderr)
            sys.exit(2)
        folder = path.parent.name
        errors, warnings = lint(
            fm.get("name"), fm.get("description"), fm.get("domain"),
            folder_hint=folder,
        )
        print_report(folder, errors, warnings)
        total_errors = len(errors)
        total_warnings = len(warnings)

    elif args.name:
        errors, warnings = lint(args.name, args.description, args.domain)
        print_report(args.name, errors, warnings)
        total_errors = len(errors)
        total_warnings = len(warnings)

    else:
        parser.print_help()
        sys.exit(2)

    print()
    print(f"summary: {total_errors} error(s), {total_warnings} warning(s)")
    if total_errors:
        sys.exit(2)
    if total_warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
