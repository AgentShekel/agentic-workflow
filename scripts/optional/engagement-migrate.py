#!/usr/bin/env python3
"""Migrate a legacy engagement to the current protocol shape.

Adds defaults for fields introduced after the engagement started, so the new
handoff-precheck.py doesn't fail on pre-existing in-flight engagements:

- frontmatter: size (default M), ux_heavy (default false), tools_required (default [])
- engagement/iteration file (default 1, or max(acceptance-log iterations) + 1)
- engagement/validation-outputs/ directory (empty placeholder)

Idempotent: re-running on already-migrated state is a no-op.

Usage:
  python ~/.claude/scripts/engagement-migrate.py [engagement-path]

Defaults to ./engagement.

Exit codes:
  0 — migration applied (or already current)
  1 — engagement not found / unsalvageable
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


def has_frontmatter_field(fm: str, key: str) -> bool:
    return bool(re.search(rf"^{key}\s*:", fm, re.MULTILINE))


def patch_frontmatter(text: str, additions: dict) -> tuple[str, list]:
    """Insert missing fields into frontmatter. Return (new_text, added_keys)."""
    fm_match = re.match(r"^(---\n)(.*?)(\n---\n)", text, re.DOTALL)
    if not fm_match:
        # No frontmatter at all — wrap entire content
        new_fm = "---\n" + "\n".join(f"{k}: {v}" for k, v in additions.items()) + "\n---\n"
        return new_fm + text, list(additions.keys())

    fm_body = fm_match.group(2)
    added = []
    for key, default in additions.items():
        if not has_frontmatter_field(fm_body, key):
            fm_body = fm_body.rstrip() + f"\n{key}: {default}"
            added.append(key)

    new = fm_match.group(1) + fm_body + fm_match.group(3) + text[fm_match.end():]
    return new, added


def migrate_one(eng: Path) -> tuple[bool, list[str]]:
    """Apply migrations to a single engagement directory. Returns (any_changes, action_list)."""
    actions: list[str] = []
    crit = eng / "criteria.md"
    if not crit.exists():
        return False, [f"{eng}/criteria.md missing — refuse to migrate"]

    text = crit.read_text(encoding="utf-8")
    text2, added_keys = patch_frontmatter(text, {
        "size": "M",
        "ux_heavy": "false",
        "tools_required": "[]",
        "protocol_version": "4",
    })
    if added_keys:
        crit.write_text(text2, encoding="utf-8")
        actions.append(f"frontmatter: added {added_keys}")

    counter = eng / "iteration"
    if not counter.exists():
        log = eng / "acceptance-log.md"
        n = 1
        if log.exists():
            iters = re.findall(r"^##\s*Iteration\s+(\d+)", log.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
            if iters:
                n = max(int(x) for x in iters) + 1
        counter.write_text(str(n), encoding="utf-8")
        actions.append(f"created iteration={n}")

    outputs = eng / "validation-outputs"
    if not outputs.exists():
        outputs.mkdir()
        readme = outputs / "README.md"
        readme.write_text(
            "# validation-outputs\n\nJSON output from each validator agent run.\n"
            "Naming: `{validator}-iter-{N}-{YYYYMMDD-HHMMSS}.json`.\n",
            encoding="utf-8",
        )
        actions.append("created validation-outputs/")

    return bool(actions), actions


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("engagement", nargs="?", default="engagement", help="Path to engagement directory (default: ./engagement)")
    p.add_argument("--include-archived", action="store_true", help="Also migrate engagements under engagement-archived/")
    args = p.parse_args()

    if args.include_archived:
        archived_root = Path.cwd() / "engagement-archived"
        if not archived_root.exists():
            print(f"No engagement-archived/ at {archived_root}.")
            return 0
        targets = []
        for dated in archived_root.iterdir():
            if not dated.is_dir():
                continue
            for leaf in dated.iterdir():
                if leaf.is_dir() and (leaf / "criteria.md").exists():
                    targets.append(leaf)
        if not targets:
            print(f"No archived engagements found in {archived_root}.")
            return 0
        for tgt in targets:
            changed, actions = migrate_one(tgt)
            if changed:
                print(f"[MIGRATED] {tgt.relative_to(archived_root)}")
                for a in actions:
                    print(f"  - {a}")
            else:
                print(f"[CURRENT ] {tgt.relative_to(archived_root)}")
        return 0

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        print(f"ERROR: engagement not found: {eng}", file=sys.stderr)
        return 1

    changed, actions = migrate_one(eng)
    if not changed:
        print(f"Engagement already current: {eng} — no migration needed.")
        return 0

    print(f"Migrated {eng}:")
    for a in actions:
        print(f"  - {a}")
    print()
    print("Re-run handoff-precheck after this migration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
