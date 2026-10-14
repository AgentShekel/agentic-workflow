#!/usr/bin/env python3
"""Print the digest a verdict is bound to.

An acceptance verdict approves specific content. `handoff-precheck.py`'s
`handoff-digest` check enforces that binding; this script is how the acceptor
obtains the value to record, so nobody has to hand-compute a sha256 or guess
which normalization was used.

The digest covers `handoff.md` only, normalized for whitespace shape and
nothing else (see `lib/precheck/common.normalize_for_digest`). It catches a
changed handoff, not a changed screenshot.

Usage:
  python ~/.claude/scripts/handoff-digest.py engagement/
  python ~/.claude/scripts/handoff-digest.py engagement/ --json
  python ~/.claude/scripts/handoff-digest.py engagement/ --bare

Default output is the line to paste into the `## Iteration N` section of
acceptance-log.md, next to the verdict:

  handoff-sha256: <64 hex chars>

Exit codes:
  0 — digest computed and printed
  1 — engagement exists but has no handoff.md yet
  2 — invocation error (path missing)
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.precheck import handoff_digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the handoff digest an acceptance verdict binds to")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--bare", action="store_true",
                        help="Print the bare hex digest with no label")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    digest = handoff_digest(eng)
    if digest is None:
        if args.json:
            print(json.dumps({"status": "no-handoff", "engagement": str(eng),
                              "digest": None,
                              "detail": "handoff.md not present"}, ensure_ascii=False))
        else:
            print(f"ERROR: {eng / 'handoff.md'} not present — nothing to bind a verdict to",
                  file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"status": "ok", "engagement": str(eng), "digest": digest,
                          "line": f"handoff-sha256: {digest}"}, ensure_ascii=False))
    elif args.bare:
        print(digest)
    else:
        print(f"handoff-sha256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
