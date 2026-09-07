#!/usr/bin/env python3
"""Regression guard — pytest/`test_*.py` entry point for the loop-gating suite.

The suite itself is JavaScript (`test_loop_gating_regress.cjs`) and has to be: it runs the
bodies of skillopt-workflow.js and harnessopt-workflow.js with stubbed globals, which is the
only way to exercise agent-script control flow. This shim exists so it is picked up by pytest
and by the plain `for t in test_*.py` sweep, like every other guard in this directory.

Skips (rather than fails) when node is absent, so a machine without it does not report a
red suite for a missing tool.

Run standalone or under pytest:
  python test_loop_gating_regress.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SUITE = Path(__file__).resolve().parent / "test_loop_gating_regress.cjs"


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("SKIP — node not found on PATH; the loop-gating suite needs it")
        return 0
    proc = subprocess.run([node, str(SUITE)], text=True, encoding="utf-8",
                          errors="replace", check=False)
    return proc.returncode


def test_loop_gating_regression():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not on PATH")
    proc = subprocess.run([node, str(SUITE)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


if __name__ == "__main__":
    raise SystemExit(main())
