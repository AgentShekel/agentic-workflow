#!/usr/bin/env python3
"""Regression guard — adversary_lg finalize visibility + non-blocking subprocesses.

Pins the fix for F2, the consilium "synth/finalize hang" that bit twice:

Both times the roles completed and wrote FINALs, the finalizer produced no output,
the conductor read that as "consilium never ran" and substituted a fabricated
cross-family signal.

Root cause was two-part and both parts are asserted here:

  A. a headless subprocess waits on stdin even when it has a prompt argument, so
     every subprocess.run must pass stdin=DEVNULL AND a timeout (static, AST);
  B. the operator needs the FINAL count BEFORE the (slow) synth step, so a stalled
     or killed run still reads as "roles ran, N FINALs written" (live subprocess).

B is a real end-to-end run against --invoker mock: no API calls, no network, but
the actual graph, the actual finalize node and the actual synth subprocess.

Run standalone (harness gate) or under pytest:
  python test_adversary_finalize_regress.py
  python test_adversary_finalize_regress.py --script /tmp/patched-adversary.py
  pytest test_adversary_finalize_regress.py -q
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "adversary_lg.py"
_SCRIPT_OVERRIDE: Path | None = None

# The mock consilium is a few seconds; anything near this cap means the hang is back.
RUN_TIMEOUT_S = 240

SIGNAL_RE = re.compile(r"iter (\d+): (\d+) role FINAL\(s\) on disk before synth")


def script_path() -> Path:
    return _SCRIPT_OVERRIDE or DEFAULT_SCRIPT


def interpreter() -> str:
    """Python that already has langgraph.

    adversary_lg self-bootstraps into .venv-adversary-lg, but only finds it next
    to itself — a throwaway copy under /tmp (what the gate runs for the red pass)
    would exit 2 instead of failing the assertion. Resolve the venv from the REAL
    script dir so copies run under the same interpreter as the original.
    """
    return venv_python() or sys.executable


class _NoVenv(unittest.SkipTest):
    """The live-consilium tests need the adversary venv, which is built on the first live run
    and is not in the repo. Absent = SKIP, never FAIL: a fresh clone has no venv, and a
    suite that goes red over a missing optional dependency teaches the reader to ignore it.
    Subclasses unittest.SkipTest so pytest honours it too."""


def venv_python() -> str | None:
    """The interpreter that already has langgraph, or None if the venv was never built."""
    for rel in ("Scripts/python.exe", "bin/python"):
        cand = DEFAULT_SCRIPT.parent / ".venv-adversary-lg" / rel
        if cand.exists():
            return str(cand)
    return None


def _run_consilium(extra_args: list[str]) -> tuple[int, str, str]:
    """One live mock consilium in a throwaway engagement dir."""
    if venv_python() is None:
        raise _NoVenv(
            "adversary venv absent — build scripts/.venv-adversary-lg from "
            "scripts/requirements-adversary-lg.txt to exercise the live path")
    with tempfile.TemporaryDirectory() as td:
        eng = Path(td) / "eng"
        eng.mkdir()
        cmd = [interpreter(), str(script_path()), str(eng),
               "--consilium", "M", "--invoker", "mock", "--no-checkpoint", *extra_args]
        # `from lib.claude_path import ...` is unguarded, so a copy outside the
        # scripts dir cannot import it. Point the child at the real one, otherwise
        # a red run fails on ImportError instead of on the assertion under test.
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(
            p for p in (str(DEFAULT_SCRIPT.parent), os.environ.get("PYTHONPATH", "")) if p)}
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env,
                               stdin=subprocess.DEVNULL, timeout=RUN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"consilium did not terminate within {RUN_TIMEOUT_S}s — the F2 hang is back"
            )
        return r.returncode, r.stdout, r.stderr


# ------------------------------------------------------------------ A. static

def test_every_subprocess_run_is_non_blocking():
    """No subprocess.run without stdin= and timeout=.

    The bootstrap re-exec uses the `_sp` alias on purpose (it must inherit the
    real stdio and must not be capped), so it is out of scope by construction.
    """
    tree = ast.parse(script_path().read_text(encoding="utf-8"))
    offenders: list[str] = []
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "run"
                and isinstance(f.value, ast.Name) and f.value.id == "subprocess"):
            continue
        checked += 1
        kw = {k.arg for k in node.keywords if k.arg}
        missing = {"stdin", "timeout"} - kw
        if missing:
            offenders.append(f"line {node.lineno}: missing {sorted(missing)}")
    assert checked >= 3, f"expected several subprocess.run calls, found {checked}"
    assert not offenders, "unguarded subprocess.run:\n  " + "\n  ".join(offenders)


# -------------------------------------------------------------------- B. live

def test_finalize_reports_final_count_before_synth():
    rc, out, err = _run_consilium([])
    assert rc == 0, f"rc={rc}\nstderr tail:\n{err[-800:]}"

    m = SIGNAL_RE.search(err)
    assert m, ("finalize must announce the FINAL count on stderr before synth; "
               f"stderr was:\n{err[-800:]}")
    assert int(m.group(2)) == 1, f"expected 1 role FINAL on disk, got {m.group(2)}"
    assert "peer-opus" in err


def test_signal_survives_synth_being_skipped():
    """The count must not depend on synth running — that is the whole point."""
    rc, out, err = _run_consilium(["--no-synth"])
    assert rc == 0, f"rc={rc}\nstderr tail:\n{err[-800:]}"
    assert SIGNAL_RE.search(err), "signal must print even when synth is disabled"


def test_json_stdout_stays_clean():
    """Operator diagnostics on stderr; stdout stays machine-parseable."""
    rc, out, err = _run_consilium(["--json"])
    assert rc == 0, f"rc={rc}\nstderr tail:\n{err[-800:]}"
    assert not SIGNAL_RE.search(out), "the signal must not pollute --json stdout"
    data = json.loads(out)
    assert data["ok"] == 1, data
    assert data["results"][0]["role"] == "peer-opus"
    if _SCRIPT_OVERRIDE is None:
        # A throwaway copy resolves consilium-synth.py next to ITSELF and skips,
        # so only the in-place script proves the synth leg end to end.
        assert data["synth"]["status"] == "ok", data["synth"]


# --------------------------------------------------------------------- runner

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
                print(f"        {e}")
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
