#!/usr/bin/env python3
"""Verify all paths cited in handoff.md actually exist on disk.

Phantom paths in §6 Exercised (lead claims `traces/iter-2/quarter.json:45` but
the file doesn't exist) are a hallucination class no human review reliably
catches. This script greps every `engagement/...` path reference, runs `ls`,
returns missing list.

Cross-repo (donor→host) engagements: a transplant keeps engagement/ in the donor repo but
cites build-target paths that live in a DIFFERENT host repo. Pass --build-target-root <host>
(or declare `build_target_root: <path>` inside the artefact) so those paths resolve against
the host repo too — a path existing in EITHER root is not a phantom path.

Usage:
  python ~/.claude/scripts/handoff-paths-check.py engagement/handoff.md
  python ~/.claude/scripts/handoff-paths-check.py engagement/handoff.md --json
  python ~/.claude/scripts/handoff-paths-check.py engagement/handoff.md --build-target-root /path/to/host-repo

Exit codes:
  0 — all paths exist
  1 — at least one path missing (handoff is incomplete)
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
import json
import re
import sys
from pathlib import Path

# Match path-like strings in markdown:
#  - `engagement/screens/iter-2/dark/dashboard.png`
#  - engagement/traces/iter-2/quarter.json:45-52
#  - `engagement/specs/tech-spec.md`
#  - src/components/X.tsx (project-relative paths)
# Conservatively: 2+ segments separated by /, ending in extension OR last segment.
PATH_PATTERN = re.compile(
    r"""
    (?:
        `([^`\n]+?)`         # backtick-quoted path
      |
        (?<![\w/])            # not preceded by alphanum or slash
        (
          engagement/[\w./\-]+   # engagement-rooted
          |
          (?:src|tests|app|lib|scripts|hooks|agents|skills)/[\w./\-]+  # common project roots
        )
    )
    """,
    re.VERBOSE,
)

# Ignore noise: section anchors, URLs, code keywords, etc.
IGNORE_SUBSTRINGS = (
    "://", "http:", "https:", "{", "}", "<", ">", "$ARGUMENTS",
    "...",  # ellipsis in pseudo-paths
    "*",    # globs in examples
    "?",
)

# Skip lines that look like negative examples / illustrations (not real evidence)
SKIP_LINE_HINTS = re.compile(
    r"(?i)("
    r"например[,:]?|"
    r"e\.g\.|"
    r"for example|"
    r"такие как|"
    r"NOT\s+create|"
    r"do\s+not\s+create|"
    r"forbidden|"
    r"запрещ|"
    r"out-of-whitelist|"
    r"rogue|"
    r"placeholder|"
    r"шаблон[ \-:]|"
    r"template[ \-:]"
    r")"
)

# Strip line-suffix like `:45-52` or `:45`
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")

# Post-ACCEPT archive destination: engagement-protocol §"Engagement archival"
# creates engagement-archived/{YYYY-MM-DD}-{name}/ only AFTER the manager
# verdict, never at handoff time. A handoff that cites it (e.g. "will move to
# engagement-archived/...") is forward-looking, not a phantom-evidence path.
# Per skill-evolution signal #2 (2026-05-28 S field test).
FUTURE_PATH_PATTERN = re.compile(r"^engagement-archived?(?:/|$)")

# A cited `a/b`-shaped token is treated as an existence-checkable path ONLY if its
# first segment is a recognized project/engagement root. This excludes git-ref
# tokens (`feature/redesign-impl`), template-relative refs (`pages/article.html`
# that actually live under `frontend/templates/`), and other slug-like strings the
# checker cannot resolve against the project root — it must NOT false-flag those as
# "missing". Root-anchored evidence paths (engagement/…, frontend/…, api/…, src/…)
# are still fully checked, so genuine phantom-evidence detection is unaffected.
# Field signal: an L-tier redesign-impl engagement — handoff-paths REJECTed
# `feature/redesign-impl` (a branch) + bare `pages/*.html` (template-relative) as
# missing, forcing the lead to reword a correct handoff.
KNOWN_ROOTS = frozenset({
    "engagement", "engagement-archived",
    # group(2) project roots (keep in sync with PATH_PATTERN)
    "src", "tests", "test", "app", "lib", "scripts", "hooks", "agents", "skills",
    # common backend / web / data roots seen across the projects
    "api", "backend", "frontend", "clients", "alembic", "docs", "var",
    "static", "public", "templates", "services", "core", "internal",
    "pkg", "cmd", "packages", "components", "config",
})


def extract_paths(handoff_text: str) -> list[str]:
    paths: set[str] = set()
    for line in handoff_text.splitlines():
        # Skip example / "do NOT create" lines — they cite paths illustratively, not as evidence
        if SKIP_LINE_HINTS.search(line):
            continue
        for m in PATH_PATTERN.finditer(line):
            raw = (m.group(1) or m.group(2) or "").strip()
            if not raw:
                continue
            if any(s in raw for s in IGNORE_SUBSTRINGS):
                continue
            clean = LINE_SUFFIX.sub("", raw)
            if clean.startswith("./"):
                clean = clean[2:]
            if clean.startswith("#") or " " in clean:
                continue
            if "/" not in clean:
                continue
            # Skip schema placeholders {iteration}, {N}, etc.
            if re.search(r"\{[\w\-_]+\}", clean):
                continue
            # Skip the post-ACCEPT archive destination — created after handoff,
            # not a phantom path (skill-evolution signal #2, 2026-05-28).
            if FUTURE_PATH_PATTERN.match(clean):
                continue
            # Only existence-check root-anchored paths; non-anchored tokens (git
            # refs, template-relative refs) are skipped rather than false-flagged.
            # Field signal: an L-tier redesign-impl engagement.
            if clean.split("/", 1)[0].lower() not in KNOWN_ROOTS:
                continue
            paths.add(clean)
    return sorted(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that all paths cited in a markdown artefact exist")
    parser.add_argument("path", help="Path to handoff.md OR acceptance-log.md OR any markdown file with cited paths")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    parser.add_argument("--root", help="Project root for relative paths (default: file's parent's parent)")
    parser.add_argument(
        "--build-target-root",
        help="Cross-repo (donor→host) allowance: a SECOND root to also resolve cited paths "
             "against (the host/build-target repo). A path that exists in EITHER root is not a "
             "phantom path. May also be declared in the artefact itself as a "
             "`build_target_root: <path>` line (or `<!-- build_target_root: <path> -->`).",
    )
    args = parser.parse_args()

    handoff_path = Path(args.path)
    if not handoff_path.exists():
        print(f"ERROR: file not found: {handoff_path}", file=sys.stderr)
        return 2

    text = handoff_path.read_text(encoding="utf-8")

    # Resolve project root: if handoff is `<project>/engagement/handoff.md`,
    # root is `<project>`. Override via --root.
    if args.root:
        root = Path(args.root).resolve()
    else:
        root = handoff_path.resolve().parent.parent

    # Cross-repo build-target root (host repo). A transplant engagement keeps engagement/
    # in the DONOR repo but cites build-target paths that live in the HOST repo; resolving
    # those only against the donor root false-fired "phantom path" on a legitimate ACCEPT
    # (recorded in the skill-evolution log). CLI arg wins;
    # else honour a `build_target_root:` declaration inside the artefact.
    bt_root = None
    if args.build_target_root:
        bt_root = Path(args.build_target_root).resolve()
    else:
        m = re.search(r"^\s*(?:<!--\s*)?build_target_root\s*:\s*(\S+)", text, re.MULTILINE)
        if m:
            decl = m.group(1).strip().strip('"').strip("'").rstrip("-").strip()
            cand = Path(decl)
            bt_root = (cand if cand.is_absolute() else (root / cand)).resolve()

    cited = extract_paths(text)
    results = []
    missing_count = 0

    for rel in cited:
        full = root / rel
        exists = full.exists()
        resolved_via = "primary" if exists else None
        if not exists and bt_root is not None:
            alt = bt_root / rel
            if alt.exists():
                exists = True
                full = alt
                resolved_via = "build_target"
        if not exists:
            missing_count += 1
        results.append({
            "path": rel,
            "resolved": str(full),
            "exists": exists,
            "resolved_via": resolved_via,
        })

    if args.json:
        print(json.dumps({
            "handoff": str(handoff_path),
            "root": str(root),
            "build_target_root": str(bt_root) if bt_root else None,
            "total_cited": len(cited),
            "missing_count": missing_count,
            "status": "fail" if missing_count else "pass",
            "paths": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Handoff: {handoff_path}")
        print(f"Root:    {root}")
        print(f"Cited paths: {len(cited)}, missing: {missing_count}")
        print()
        for r in results:
            mark = "[OK  ]" if r["exists"] else "[MISS]"
            print(f"{mark} {r['path']}")
        print()
        if missing_count:
            print(f"VERDICT: FAIL — {missing_count} cited path(s) do not exist. Handoff is INCOMPLETE.")
        else:
            print("VERDICT: PASS — all cited paths exist on disk.")

    return 1 if missing_count else 0


if __name__ == "__main__":
    sys.exit(main())
