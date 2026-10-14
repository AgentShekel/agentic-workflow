#!/usr/bin/env python3
"""Regression guard — scoped consilium reviewers are shown the finding item schema.

The sonnet / haiku prompts showed `"findings": [...]` with no per-item schema.
sonnet-scoped wrote its own keys and no severity, so all of its findings defaulted to
minor, including duplicates of peer-opus MAJOR findings. adversary_lg's Finding aliases
recover the text, not the severity. The four scoped prompts (marked "tuned, do not
edit") carry the full item schema as a deliberate exception.

  A. ITEM SCHEMA     each scoped prompt, rendered with str.format, shows the item
                     line with severity critical|major|minor, issue, evidence_path,
                     fix_hint under its findings key.
  B. SAME AS PEER    the rendered item line is byte-identical to PROMPT_PASS2_PEER's,
                     so all reviewers are asked for one shape.
  C. KEYS KEPT       Pass-1 prompts still use `preliminary_findings` (Pass1Output reads
                     that key), Pass-2 prompts `findings`; no `[...]` placeholder left.

Reads the prompt constants from the source with ast, so no venv is needed.

Run standalone (harness gate) or under pytest:
  python test_adversary_scoped_schema_regress.py
  python test_adversary_scoped_schema_regress.py --script /tmp/patched-adversary.py
  pytest test_adversary_scoped_schema_regress.py -q
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "adversary_lg.py"
_SCRIPT_OVERRIDE: Path | None = None

ITEM = ('{"severity": "critical"|"major"|"minor", "issue": "...", '
        '"evidence_path": "...", "fix_hint": "..."}')
SCOPED = {
    "PROMPT_PASS1_SONNET": "preliminary_findings",
    "PROMPT_PASS2_SONNET": "findings",
    "PROMPT_PASS1_HAIKU": "preliminary_findings",
    "PROMPT_PASS2_HAIKU": "findings",
}
FMT = {"curated_path": "/c", "engagement": "/e", "role": "r", "iter_n": 1,
       "preliminary_json": "{}", "peer_findings": "(none)"}


def script_path() -> Path:
    return _SCRIPT_OVERRIDE or DEFAULT_SCRIPT


def prompts() -> dict[str, str]:
    tree = ast.parse(script_path().read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.startswith("PROMPT_")
                and isinstance(node.value, ast.Constant)):
            out[node.targets[0].id] = node.value.value
    return out


def rendered(name: str) -> str:
    return prompts()[name].format(**FMT)


def item_block(text: str, key: str) -> str:
    m = re.search(rf'^  "{key}": \[\n(.*?)\n  \],?$', text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def test_scoped_prompts_show_item_schema():
    missing = {n: item_block(rendered(n), k) for n, k in SCOPED.items()
               if item_block(rendered(n), k) != ITEM}
    assert not missing, f"scoped prompts without the item schema: {missing}"


def test_item_line_matches_peer():
    peer = item_block(rendered("PROMPT_PASS2_PEER"), "findings")
    assert peer == ITEM, f"peer item line drifted: {peer!r}"
    for n, k in SCOPED.items():
        assert item_block(rendered(n), k) == peer, n


def test_keys_kept_no_placeholder():
    for n, k in SCOPED.items():
        text = rendered(n)
        assert f'"{k}": [' in text, f"{n} lost its {k} key"
        assert f'"{k}": [...]' not in text, f"{n} still shows a bare [...] for {k}"
        if k == "preliminary_findings":
            assert '"findings": [' not in text.replace('"preliminary_findings": [', ""), \
                f"{n} (Pass 1) must not ask for a final findings list"


def _run_standalone() -> int:
    import traceback

    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except unittest.SkipTest as e:
            skipped += 1
            print(f"  SKIP  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}")
            if isinstance(e, AssertionError):
                print(f"        {str(e)[:400]}")
            else:
                traceback.print_exc()
    tail = f", {skipped} skipped" if skipped else ""
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} passed{tail}  (target: {script_path()})")
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--script" in argv:
        _SCRIPT_OVERRIDE = Path(argv[argv.index("--script") + 1]).resolve()
    sys.exit(_run_standalone())
