#!/usr/bin/env python3
"""Regression guard: the lint-on-edit hook never writes over a file that moved under it.

Codex review 2026-10-09 of 412d5b6: fix_touched() read the file once, ran the linter
(seconds), then replaced the file with its own snapshot plus the fix. If another edit
landed meanwhile (five sessions share one checkout), that edit was silently reverted.
Atomic replace prevents truncation, not this.

  A. CONCURRENT EDIT SURVIVES   the file changes while the linter runs: the hook drops
                                its pass and the other edit stays.
  B. QUIET FILE STILL FIXED     no concurrent change: the touched-line fix still lands.

Run standalone or under pytest:
  python test_lint_on_edit_race_regress.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "lint_on_edit.py"
_spec = importlib.util.spec_from_file_location("_lint_on_edit", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

ORIGINAL = "a = 1;\nb = 2\n"
SEMICOLON = [[(5, 6, "", {1})]]  # drop the `;` on row 1, the row the edit touched


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "m.py"

        path.write_bytes(ORIGINAL.encode())
        calls = []

        def racing_check(text):
            if not calls:  # first lint run: another session rewrites row 2 meanwhile
                path.write_bytes(b"a = 1;\nb = 99\n")
            calls.append(text)
            return (SEMICOLON if len(calls) == 1 else []), []

        hook.fix_touched(str(path), {1}, racing_check)
        got = path.read_bytes().decode()
        results.append(check("A: the concurrent edit to row 2 survives", "b = 99" in got, f"file is {got!r}"))

        path.write_bytes(ORIGINAL.encode())
        n = []

        def quiet_check(text):
            n.append(1)
            return (SEMICOLON if len(n) == 1 else []), []

        hook.fix_touched(str(path), {1}, quiet_check)
        got = path.read_bytes().decode()
        results.append(check("B: with no concurrent change the touched-row fix lands",
                             got == "a = 1\nb = 2\n", f"file is {got!r}"))

        # C. the create path (Write of a new file) used to run the linter's own --fix, outside
        #    the guard; it now goes through the same tracked, re-read-before-write path
        path.write_bytes(ORIGINAL.encode())
        calls2 = []

        def racing_create_check(text):
            if not calls2:
                path.write_bytes(b"a = 1;\nb = 99\n")
            calls2.append(text)
            return (SEMICOLON if len(calls2) == 1 else []), []

        results.append(check("C: the hook exposes fix_created()", hasattr(hook, "fix_created")))
        if hasattr(hook, "fix_created"):
            hook.fix_created(str(path), racing_create_check)
            got = path.read_bytes().decode()
            results.append(check("C: a concurrent edit to a just-created file survives", "b = 99" in got, f"{got!r}"))
            path.write_bytes(ORIGINAL.encode())
            m = []
            hook.fix_created(str(path), lambda text: ((m.append(1) or (SEMICOLON if len(m) == 1 else [])), []))
            got = path.read_bytes().decode()
            results.append(check("C: a quiet new file still gets its fixes", got == "a = 1\nb = 2\n", f"{got!r}"))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_lint_on_edit_race():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
