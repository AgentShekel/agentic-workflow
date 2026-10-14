#!/usr/bin/env python3
"""Regression guard: a nested `claude -p` must run the PARENT session's build.

Root cause of the desktop-only silent hang (2026-08-31, 2026-09-28), settled
2026-10-09 by a live bisect. `lib/claude_path.py` resolved the npm global build
from PATH (2.1.153, autoupdate off) while the desktop host ran 2.1.247-2.1.284.
The desktop exports the Windows system proxy as HTTPS_PROXY (a local
proxy on 127.0.0.1). Through that proxy the old build returned zero
bytes on both streams until killed; stripping only HTTPS_PROXY/HTTP_PROXY made
it answer in 5s, stripping every CLAUDE_*/ANTHROPIC_*/MCP_* var did not. A
current build answers through the same proxy in ~7s. A plain terminal never
gets HTTPS_PROXY (WinINet is not env), so the same call worked there and the
gap was misread as "the desktop host blocks the headless path".

Fix: CLAUDE_CODE_EXECPATH (the parent's own binary) wins over PATH.

  A. EXECPATH WINS          over a stale build earlier on PATH.
  B. OVERRIDE STILL WINS    CLAUDE_CLI_PATH stays the operator escape hatch.
  C. MISSING FALLS THROUGH  a stale EXECPATH (desktop updated mid-run) is skipped.
  D. NODE IS REFUSED        an EXECPATH of node.exe would make `-p <prompt>`
                            evaluate the prompt as JavaScript.
  E. TIMEOUT NAMES CAUSE    the preflight timeout detail names binary and proxy.
  F. LIVE RED->GREEN        only when CLAUDE_OLD_BUILD_DIR points at a dir holding
                            an old claude.exe (e.g. 2.1.153 from the npm cache).
                            Skips loudly otherwise; never fails on machine state.

Run standalone or under pytest:
  python test_claude_path_execpath_regress.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import claude_path

_spec = importlib.util.spec_from_file_location("_preflight_xp", SCRIPTS_DIR / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
sys.modules["_preflight_xp"] = preflight
_spec.loader.exec_module(preflight)

FAILURES: list[str] = []
_KEYS = ("CLAUDE_CODE_EXECPATH", "CLAUDE_CLI_PATH", "CLAUDE_CLI", "PATH")


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def _with_env(**env):
    saved = {k: os.environ.get(k) for k in _KEYS}
    for k in _KEYS:
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is not None:
            os.environ[k] = v
    try:
        return claude_path.find_claude_cmd()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _live_red_green(old_dir: str) -> None:
    host = os.environ.get("CLAUDE_CODE_EXECPATH")
    if not host:
        print("NOTE: F skipped, not nested in a Claude Code session (no EXECPATH).")
        return
    if not (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")):
        print("NOTE: F skipped, no inherited HTTPS_PROXY: the old build would answer "
              "here too, so red could not be shown.")
        return
    saved = {k: os.environ.get(k) for k in _KEYS}
    saved_timeout = preflight.CLAUDE_PROBE_TIMEOUT_S
    os.environ.pop("CLAUDE_CLI_PATH", None)
    os.environ.pop("CLAUDE_CLI", None)
    os.environ["PATH"] = old_dir + os.pathsep + saved["PATH"]
    preflight.CLAUDE_PROBE_TIMEOUT_S = 45
    try:
        os.environ.pop("CLAUDE_CODE_EXECPATH")
        red = preflight.check_claude_cli()
        os.environ["CLAUDE_CODE_EXECPATH"] = host
        green = preflight.check_claude_cli()
    finally:
        preflight.CLAUDE_PROBE_TIMEOUT_S = saved_timeout
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print(f"NOTE: F red (old build on PATH)  -> {red['status']}: {red['detail'][:90]}")
    print(f"NOTE: F green (parent EXECPATH) -> {green['status']}: {green['detail'][:90]}")
    check(red["status"] == "fail", "F: the old build on PATH must reproduce the hang "
                                   "(red); if it passes, F proves nothing")
    check(green["status"] == "pass", "F: with EXECPATH the probe must pass")


def main() -> int:
    if os.name != "nt":
        print("NOTE: A-D skipped, fixtures are Windows .exe layouts (see module doc).")
    else:
        _resolver_cases()
    _preflight_and_live()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS: claude_path EXECPATH regressions held")
    return 0


def _resolver_cases() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "path").mkdir()
        stale = t / "path" / "claude.exe"
        host = t / "host" / "claude.exe"
        node = t / "node" / "node.exe"
        for f in (stale, host, node):
            f.parent.mkdir(exist_ok=True)
            f.write_bytes(b"")
        path = str(t / "path")

        # --- A. parent binary beats PATH -----------------------------------------
        got = _with_env(PATH=path, CLAUDE_CODE_EXECPATH=str(host))
        check(got == str(host), f"A: EXECPATH must win over PATH, got {got}")
        got = _with_env(PATH=path)
        check(got is not None and Path(got).parent == stale.parent,
              f"A: without EXECPATH, PATH must still resolve, got {got}")

        # --- B. explicit override beats everything --------------------------------
        got = _with_env(PATH=path, CLAUDE_CODE_EXECPATH=str(host), CLAUDE_CLI_PATH=str(stale))
        check(got == str(stale), f"B: CLAUDE_CLI_PATH must win over EXECPATH, got {got}")

        # --- C. a vanished EXECPATH falls through ---------------------------------
        got = _with_env(PATH=path, CLAUDE_CODE_EXECPATH=str(t / "gone" / "claude.exe"))
        check(got is not None and Path(got).parent == stale.parent,
              f"C: a missing EXECPATH must fall through to PATH, got {got}")

        # --- D. never hand `-p <prompt>` to node ----------------------------------
        got = _with_env(PATH=path, CLAUDE_CODE_EXECPATH=str(node))
        check(got is None or Path(got).name.lower() != "node.exe",
              f"D: EXECPATH=node.exe must be refused, got {got}")


def _preflight_and_live() -> None:
    # --- E. the timeout detail names the real suspects ---------------------------
    r = preflight.classify_claude_probe(None, "", "", timed_out=True,
                                        binary=r"C:\x\claude.exe",
                                        proxy="http://127.0.0.1:8080")
    check(r["status"] == "fail", "E: a timeout still fails")
    check(r"C:\x\claude.exe" in r["detail"], "E: the detail must name the binary it ran")
    check("127.0.0.1:8080" in r["detail"], "E: the detail must name the inherited proxy")
    check("CLAUDE_CODE_EXECPATH" in (r.get("fix") or ""),
          "E: the fix must point at the resolver rule, not at 'use a terminal'")
    r = preflight.classify_claude_probe(None, "", "", timed_out=True)
    check("HTTPS_PROXY" not in r["detail"], "E: no proxy, no proxy claim")

    # --- F. live red->green, opt-in -------------------------------------------------
    old_dir = os.environ.get("CLAUDE_OLD_BUILD_DIR")
    if old_dir and (Path(old_dir) / "claude.exe").is_file():
        _live_red_green(old_dir)
    else:
        print("NOTE: F skipped. Set CLAUDE_OLD_BUILD_DIR to a dir with an old "
              "claude.exe to run the live red->green repro.")


def test_claude_path_execpath_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
