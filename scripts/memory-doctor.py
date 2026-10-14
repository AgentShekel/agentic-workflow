#!/usr/bin/env python3
"""Validate the auto-memory directory: index, frontmatter, duplicates, secrets.

The memory is one-fact markdown files plus MEMORY.md, the index loaded into every session.
Nothing validated it, and it is exactly where a secret pasted into a fact would be replayed
into every future session. Checks:

  errors    secret-shaped strings (reported by file and pattern, never printed),
            index links to missing files, MEMORY.md over 200 lines (truncated beyond),
            fact files without frontmatter or with a type outside user/feedback/project/
            reference, duplicate `name:` slugs
  warnings  files unreachable from the index through markdown links

  python ~/.claude/scripts/memory-doctor.py [DIR]      report; exit 1 on errors
  python ~/.claude/scripts/memory-doctor.py --hook     SessionStart: reads the payload,
        resolves ~/.claude/projects/<cwd slug>/memory and reports only safety and index
        integrity (secrets, broken index links, oversized index), else silent. Format errors
        stay in the full report: a hook that nags about legacy formatting at every start gets
        tuned out, including the day it reports a secret.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TYPES = {"user", "feedback", "project", "reference"}
DATA_LOGS = {"skill-evolution-log.md", "skill-evolution-meta.md", "skill-rejected-edits.md"}
INDEX_MAX_LINES = 200
LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)\)")
SECRET_PATTERNS = {
    "anthropic key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "openai-style key": r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}",
    "github token": r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}",
    "gitlab token": r"\bglpat-[A-Za-z0-9_-]{15,}",
    "slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "telegram bot token": r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}",
    "aws access key": r"\bAKIA[0-9A-Z]{16}\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "wireguard private key": r"(?i)\bPrivateKey\s*=\s*[A-Za-z0-9+/]{42,43}=",
    "bearer token": r"\bBearer\s+[A-Za-z0-9._~+/-]{30,}",
    "credentials in a URL": r"\b[a-z][a-z0-9+.-]*://[^/\s:@]*:[^@\s/]{6,}@",
    # (?<![A-Za-z]) instead of \b: REDIS_PASSWORD has "_" before the word, which \b does not split.
    "assigned password": r"(?i)(?<![A-Za-z])(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
}


def frontmatter(text: str) -> dict | None:
    """Top-level keys plus metadata.<key> one level down; nested deeper keys are ignored."""
    text = text.lstrip(chr(0xFEFF))
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm, parent, child_indent = {}, "", None
    for line in text[3:end].splitlines():
        m = re.match(r"^(\s*)([\w-]+):\s*(.*)$", line)
        if not m:
            continue
        indent, key, value = len(m.group(1)), m.group(2), m.group(3).strip().strip("'\"")
        if indent == 0:
            parent, child_indent = key, None
            fm[key] = value
        elif parent == "metadata":
            child_indent = indent if child_indent is None else child_indent
            if indent == child_indent:
                fm[key] = value
    return fm


def diagnose(d: Path) -> tuple[list[str], list[str], list[str]]:
    """(severe, errors, warnings). severe is a subset of errors: safety and index integrity, the
    only things the SessionStart hook reports; format errors stay in the full report."""
    severe, errors, warnings = [], [], []

    def bad(msg):
        severe.append(msg)
        errors.append(msg)

    index = d / "MEMORY.md"
    files = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in d.glob("*.md")}
    for name, text in sorted(files.items()):
        for label, pat in SECRET_PATTERNS.items():
            hits = len(re.findall(pat, text))
            if hits:
                bad(f"{name}: {hits} {label}-shaped string(s); move the secret to .env and rotate it")
    if not index.is_file():
        warnings.append(f"{d}: no MEMORY.md, so nothing here is loaded into sessions")
        return severe, errors, warnings
    idx = index.read_text(encoding="utf-8", errors="replace")
    n_lines = len(idx.splitlines())  # a last line without "\n" is still a line
    if n_lines > INDEX_MAX_LINES:
        bad(f"MEMORY.md has {n_lines} lines; it is truncated beyond {INDEX_MAX_LINES}")
    for link in sorted(set(LINK_RE.findall(idx))):
        if not (d / link).is_file():
            bad(f"MEMORY.md links to a missing file: {link}")
    names: dict[str, str] = {}
    for name, text in sorted(files.items()):
        if name == "MEMORY.md" or name in DATA_LOGS:
            continue
        fm = frontmatter(text)
        if fm is None:
            errors.append(f"{name}: no frontmatter (name / description / metadata.type)")
            continue
        if fm.get("type") not in TYPES:
            errors.append(f"{name}: metadata.type {fm.get('type')!r} is not one of {sorted(TYPES)}")
        slug = fm.get("name")
        if slug and slug in names:
            errors.append(f"{name}: duplicate name {slug!r} (also {names[slug]})")
        elif slug:
            names[slug] = name
    seen, todo = set(), [lnk for lnk in LINK_RE.findall(idx) if lnk in files]
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += [lnk for lnk in LINK_RE.findall(files.get(n, "")) if lnk in files]
    for name in sorted(set(files) - seen - {"MEMORY.md"}):
        warnings.append(f"{name}: not reachable from MEMORY.md")
    return severe, errors, warnings


def project_slug(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd.rstrip("/" + chr(92)))


def hook_dir(home: Path) -> Path | None:
    try:
        cwd = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace")).get("cwd") or ""  # UTF-8, any code page
    except (ValueError, AttributeError):
        return None
    if not cwd:
        return None
    # Claude Code replaces every non-alphanumeric character: C:\projects\app -> C--projects-app,
    # C:\Users\x\.claude -> C--Users-x--claude.
    d = home / ".claude" / "projects" / project_slug(cwd) / "memory"
    return d if d.is_dir() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.hook:
        d = Path(args.dir) if args.dir else hook_dir(Path(args.home))
        if d is None:
            return 0
        severe, _, _ = diagnose(d)
        if severe:
            shown = severe[:8] + ([f"... {len(severe) - 8} more"] if len(severe) > 8 else [])
            print("memory-doctor: the auto-memory has problems; fix before relying on it:\n  "
                  + "\n  ".join(shown) + f"\n  (full report: python ~/.claude/scripts/memory-doctor.py {d})")
        return 0
    d = Path(args.dir) if args.dir else Path.home() / ".claude" / "projects" / project_slug(str(Path.cwd())) / "memory"
    _, errors, warnings = diagnose(d)
    for e in errors:
        print(f"ERROR   {e}")
    for w in warnings:
        print(f"warning {w}")
    if not errors and not warnings:
        print(f"ok: {d}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
