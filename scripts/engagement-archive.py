#!/usr/bin/env python3
"""Archive engagement/ to engagement-archived/{date}-{name}/ after ACCEPT.

Deterministic archival — director calls this script as the last action on
ACCEPT verdict. Idempotent: re-running on already-archived state is a no-op.
Collision-safe: if target name exists, suffixes -2, -3, ...

Usage:
  python ~/.claude/scripts/engagement-archive.py [project-root]

Defaults to CWD if project-root not given.

Exit codes:
  0 — archived successfully (or nothing to archive)
  1 — pre-archival sanity check failed (cannot archive yet)
  2 — invocation error / mv failed
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
import shutil
import sys
from datetime import date
from pathlib import Path


def read_engagement_name(criteria_path: Path) -> str | None:
    """Extract engagement name with smart fallback chain.

    Order of precedence:
    1. frontmatter `engagement:` field (canonical)
    2. first H1 in criteria.md (heuristic — strips "Acceptance criteria — " prefix)
    3. parent directory name if ≠ "engagement" (project-naming convention)
    4. None — caller substitutes "unnamed"
    """
    if not criteria_path.exists():
        return None
    text = criteria_path.read_text(encoding="utf-8")

    # 1. Frontmatter
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm:
        m = re.search(r"^engagement\s*:\s*(\S+)", fm.group(1), re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"').strip("'")

    # 2. First H1, strip common prefixes
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()
        # Common patterns: "Acceptance criteria — {name} — {date}" / "Engagement: {name}"
        for pat in [
            r"^Acceptance\s+criteria\s*[—\-:]\s*(.+?)\s*[—\-]\s*\d{4}",
            r"^Engagement\s*[:\-—]\s*(.+)$",
            r"^(.+?)\s*[—\-]\s*\d{4}-\d{2}-\d{2}",
        ]:
            m = re.match(pat, title, re.IGNORECASE)
            if m:
                return slugify(m.group(1))
        return slugify(title)

    # 3. Parent directory name (e.g. /work-projects/my-app/engagement/criteria.md → my-app)
    parent = criteria_path.resolve().parent.parent.name
    if parent and parent != "engagement":
        return slugify(parent)

    return None


def slugify(text: str) -> str:
    """Convert arbitrary text to a safe directory-name slug."""
    s = text.lower().strip()
    s = re.sub(r"[^\wЀ-ӿ\-]+", "-", s)  # keep Latin, Cyrillic, digits, hyphens
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "unnamed"


def has_accept_verdict(acceptance_log: Path) -> bool:
    """Detect ACCEPT verdict with flexibility for legacy and free-form markup."""
    if not acceptance_log.exists():
        return False
    text = acceptance_log.read_text(encoding="utf-8")

    # All these forms count as ACCEPT (legacy + canonical):
    patterns = [
        r"^###\s+Verdict:\s*ACCEPT(?:ED)?",         # canonical: ### Verdict: ACCEPT
        r"^##\s+Verdict\s*\n+\*\*ACCEPTED?\*\*",    # legacy: ## Verdict\n\n**ACCEPTED**
        r"^\*\*ACCEPTED?\*\*",                       # bold ACCEPT(ED)
        r"^Verdict[:\s]+ACCEPT(?:ED)?",              # bare Verdict: ACCEPT
        r"engagement\s+\S+\s+is\s+\*?\*?CLOSED",     # ad-hoc "engagement X is CLOSED"
        r"^##\s+Closed\s*$",                         # heading
        r"engagement\s+is\s+\*?\*?ACCEPT(?:ED)?",    # natural-language ACCEPT
    ]
    for pat in patterns:
        if re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", default=".", help="Project root (default: CWD)")
    p.add_argument("--force", action="store_true", help="Skip sanity checks (use only when intentionally archiving rejected/aborted engagement)")
    p.add_argument("--reason", choices=["accepted", "aborted"], default="accepted", help="Archive reason; 'aborted' implies --force")
    p.add_argument("--secondary", help="Archive engagement-secondary/{domain} instead of primary engagement/")
    args = p.parse_args()

    root = Path(args.root).resolve()
    if args.secondary:
        eng = root / "engagement-secondary" / args.secondary
    else:
        eng = root / "engagement"
    archive_root = root / "engagement-archived"

    if args.reason == "aborted":
        args.force = True

    if not eng.exists():
        print(f"Nothing to archive: {eng} does not exist.")
        return 0

    if not eng.is_dir():
        print(f"ERROR: {eng} is not a directory.", file=sys.stderr)
        return 2

    # Sanity 1: criteria.md exists (this is a real engagement, not a junk dir)
    criteria = eng / "criteria.md"
    if not criteria.exists() and not args.force:
        print(f"ERROR: {criteria} missing — refuse to archive (not a real engagement?). Use --force if intentional.", file=sys.stderr)
        return 1

    # Sanity 2: at least one ACCEPT verdict in acceptance-log
    accept_log = eng / "acceptance-log.md"
    if not has_accept_verdict(accept_log) and not args.force:
        print(f"ERROR: no ACCEPT verdict found in {accept_log} — refuse to archive incomplete engagement. Use --force for aborted engagements.", file=sys.stderr)
        return 1

    # Build target name
    name = read_engagement_name(criteria) or "unnamed"
    today = date.today().isoformat()
    base = f"{today}-{name}"
    if args.reason == "aborted":
        base = f"{base}-aborted"

    archive_root.mkdir(exist_ok=True)
    base_dir = archive_root / base
    base_dir.mkdir(exist_ok=True)

    # For secondary: nest under base_dir/secondary-{domain}/
    # For primary:   place at  base_dir/primary/
    if args.secondary:
        leaf_name = f"secondary-{args.secondary}"
    else:
        leaf_name = "primary"

    target = base_dir / leaf_name
    suffix = 2
    while target.exists():
        target = base_dir / f"{leaf_name}-{suffix}"
        suffix += 1

    try:
        shutil.move(str(eng), str(target))
    except Exception as e:
        print(f"ERROR: archival mv failed: {e}", file=sys.stderr)
        return 2

    src_label = f"engagement-secondary/{args.secondary}" if args.secondary else "engagement"
    print(f"Archived: {src_label}/ → {target.relative_to(root)} (reason={args.reason})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
