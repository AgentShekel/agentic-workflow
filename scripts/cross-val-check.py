#!/usr/bin/env python3
"""Verify cross-validation table verbatim quotes against cited executor reports.

Cross-validation §4a in handoff.md is a table:
  | Contract | Specialist A — claim (verbatim) | Specialist B — claim (verbatim) | Verdict |

Each "verbatim" cell contains a quote attributed to a specialist's report:
  dev-backend-engineer.md L42: "returns 201 + {id, name}"

This script extracts those (file, line, quote) triples and verifies the quote
actually exists in the cited file at-or-near the cited line. If any quote is
missing or mismatched, the cross-validation is presumed fabricated.

Usage:
  python ~/.claude/scripts/cross-val-check.py engagement/handoff.md
  python ~/.claude/scripts/cross-val-check.py engagement/handoff.md --json

Exit codes:
  0 — all quotes verified present in cited reports
  1 — at least one phantom quote
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

# Match patterns like:
#  dev-backend-engineer.md L42: "returns 201"
#  executor-reports/dev-frontend-engineer.md L18: "expects 201, body {id, name}"
QUOTE_RE = re.compile(
    r"""
    (?:executor-reports/)?           # optional prefix
    ([\w\-./]+\.md)                  # filename (group 1)
    \s+L(\d+)                         # line number (group 2)
    \s*:\s*                           # separator
    [\"“]([^\"”\n]+)[\"”]  # quoted text (group 3)
    """,
    re.VERBOSE,
)


def extract_quotes(handoff_text: str) -> list[dict]:
    """Find all (file, line, quote) triples inside §4a cross-validation table."""
    # Locate §4a block
    m = re.search(r"^###\s*4a\..*?(?=^###\s|^##\s|\Z)", handoff_text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    block = m.group(0)
    quotes = []
    for match in QUOTE_RE.finditer(block):
        quotes.append({
            "file": match.group(1),
            "line": int(match.group(2)),
            "quote": match.group(3).strip(),
        })
    return quotes


def verify_quote(eng: Path, q: dict) -> dict:
    """Check the quote text actually appears at-or-near the cited line in the cited file."""
    # Resolve file under engagement/executor-reports/ first, then bare path
    candidates = [
        eng / "executor-reports" / q["file"],
        eng / q["file"],
        eng.parent / q["file"],
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        return {**q, "status": "fail", "reason": "cited file not found", "candidates_checked": [str(c) for c in candidates]}

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return {**q, "status": "fail", "reason": f"read error: {e}"}

    # Allow ±2 lines tolerance for off-by-one in line numbering
    line_idx = q["line"] - 1
    window_start = max(0, line_idx - 2)
    window_end = min(len(lines), line_idx + 3)
    window = "\n".join(lines[window_start:window_end])

    quote_text = q["quote"]
    # Loose match — strip extra whitespace, compare normalized
    norm_quote = re.sub(r"\s+", " ", quote_text).strip()
    norm_window = re.sub(r"\s+", " ", window).strip()

    if norm_quote in norm_window:
        return {**q, "status": "pass", "reason": "quote found in window ±2 lines"}

    # Try fuzzy: at least 5 consecutive words match
    words = norm_quote.split()
    if len(words) >= 5:
        for i in range(len(words) - 4):
            ngram = " ".join(words[i:i+5])
            if ngram in norm_window:
                return {**q, "status": "partial", "reason": f"5-word ngram '{ngram[:40]}…' matched but full quote not exact"}

    return {**q, "status": "fail", "reason": "quote not found in cited file at L{} ±2".format(q["line"])}


def main() -> int:
    p = argparse.ArgumentParser(description="Verify cross-validation §4a verbatim quotes")
    p.add_argument("handoff", help="Path to engagement/handoff.md")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    handoff = Path(args.handoff)
    if not handoff.exists():
        print(f"ERROR: handoff not found: {handoff}", file=sys.stderr)
        return 2

    eng = handoff.parent
    text = handoff.read_text(encoding="utf-8")

    quotes = extract_quotes(text)
    if not quotes:
        msg = "No verbatim quotes found in §4a (or section absent). N/A — pass."
        if args.json:
            print(json.dumps({"status": "pass", "quotes": [], "message": msg}))
        else:
            print(msg)
        return 0

    results = [verify_quote(eng, q) for q in quotes]
    fail = [r for r in results if r["status"] == "fail"]
    partial = [r for r in results if r["status"] == "partial"]

    if args.json:
        print(json.dumps({
            "status": "fail" if fail else ("partial" if partial else "pass"),
            "fail_count": len(fail),
            "partial_count": len(partial),
            "quotes": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Cross-validation §4a — {len(quotes)} quotes checked")
        print()
        for r in results:
            mark = {"pass": "[OK  ]", "partial": "[~~~ ]", "fail": "[FAIL]"}[r["status"]]
            print(f"{mark} {r['file']} L{r['line']}: \"{r['quote'][:60]}…\"")
            if r["status"] != "pass":
                print(f"       {r['reason']}")
        print()
        if fail:
            print(f"VERDICT: FAIL — {len(fail)} phantom quote(s). Cross-validation table fabricated.")
        elif partial:
            print(f"VERDICT: PARTIAL — {len(partial)} quote(s) loose-match only. Verify by hand.")
        else:
            print("VERDICT: PASS — all quotes verified.")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
