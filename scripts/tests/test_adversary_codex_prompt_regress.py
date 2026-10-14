#!/usr/bin/env python3
"""Regression guard — codex consilium roles receive the WHOLE multi-line prompt.

On an L-tier run, codex-blind and codex-informed both
answered "please send the material to review". Their raw transcripts show the
codex `user` block held only line 1 of the Pass-1 prompt. find_codex_cmd()
resolves through shutil.which to the npm `codex.CMD` shim, and cmd.exe stops
parsing the command line at the first newline, so `%*` forwarded one line. The
claude path had the same bug and was fixed in lib/claude_path.py by swapping the
shim for claude.exe; the codex path never got the fix.

  A. SHIM TRANSPORT       a 3-line prompt sent through an npm-layout codex.cmd
                          shim (cmd.exe -> node -> stand-in codex.js) arrives with
                          all 3 lines, Cyrillic intact. Live subprocess, Windows only.
  B. NO CMD PARSING       a prompt carrying cmd.exe metacharacters (" | & > %VAR%)
                          arrives byte-identical. Pass-2 prompts embed LLM-written
                          JSON; through the shim that text was cmd.exe input.
  C. WINDOWS USES STDIN   with the stdin switch on, argv ends in "-" and stdin is a
                          file holding the exact prompt bytes (LF, not CRLF) — never argv.
  D. NON-WINDOWS UNCHANGED with the switch off, the prompt is still the last argv
                          element and stdin is DEVNULL, exactly as before the fix.
  E. LIVE CODEX (opt-in)  ADVERSARY_LIVE_CODEX=1: the real codex CLI's transcript
                          shows markers that exist only on prompt lines 2 and 3.
                          May spend one codex call, so it is off by default.

Run standalone (harness gate) or under pytest:
  python test_adversary_codex_prompt_regress.py
  python test_adversary_codex_prompt_regress.py --script /tmp/patched-adversary.py
  pytest test_adversary_codex_prompt_regress.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "adversary_lg.py"
_SCRIPT_OVERRIDE: Path | None = None

THREE_LINES = (
    "LINE-ONE: you are an adversarial reviewer.\n"
    "LINE-TWO: curated path C:/tmp/eng-curated\n"
    "LINE-THREE: кириллица должна дойти целиком"
)

# Every character here means something to cmd.exe. Python escapes the inner quotes
# as \" which cmd does not understand, so the quote state flips and the rest is
# parsed as operators; %PATH% is expanded even inside quotes.
METACHARS = 'schema: "critical"|"major" & echo PWNED > nul %PATH% ^caret'

# Verbatim npm cmd-shim for @openai/codex 0.153.4 (AppData/Roaming/npm/codex.cmd).
NPM_SHIM = r"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@openai\codex\bin\codex.js" %*
"""

# Stand-in for @openai/codex/bin/codex.js: resolves the prompt the way
# `codex exec [PROMPT]` does ("-" or absent = read stdin) and reports it.
FAKE_CODEX_JS = r"""
const args = process.argv.slice(2);
const chunks = [];
process.stdin.on("data", (c) => chunks.push(c));
process.stdin.on("end", () => {
  const stdin = Buffer.concat(chunks).toString("utf8");
  const positional = args.filter((a) => a !== "exec" && !a.startsWith("--"));
  const p = positional.length ? positional[positional.length - 1] : "-";
  process.stdout.write(JSON.stringify({ args, prompt: p === "-" ? stdin : p }));
});
"""

# Runs inside the adversary venv (the module needs langgraph at import).
DRIVER = r"""
import importlib.util, json, sys
mode, script, prompt_file = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("adversary_under_test", script)
m = importlib.util.module_from_spec(spec)
sys.modules["adversary_under_test"] = m
spec.loader.exec_module(m)
prompt = open(prompt_file, encoding="utf-8").read()

if mode == "transport":
    rc, out, err = m.SubprocessInvoker()._invoke_codex(prompt, 120)
    print(json.dumps({"rc": rc, "stdout": out, "stderr": err}))
else:
    seen = []
    def fake_run(argv, **kw):
        fh = kw.get("stdin")
        seen.append({"argv": list(argv), "input": kw.get("input"),
                     "stdin_devnull": fh is m.subprocess.DEVNULL,
                     "stdin_text": fh.read().decode("utf-8") if hasattr(fh, "read") else None})
        return m.subprocess.CompletedProcess(argv, 0, "{}", "")
    m.subprocess.run = fake_run
    m.find_codex_cmd = lambda: "codex"
    m._CODEX_PROMPT_VIA_STDIN = (mode == "argv-stdin")
    m.SubprocessInvoker()._invoke_codex(prompt, 5)
    print(json.dumps(seen[0]))
"""


def script_path() -> Path:
    return _SCRIPT_OVERRIDE or DEFAULT_SCRIPT


class _Skip(unittest.SkipTest):
    """Missing optional prerequisite: SKIP loudly, never FAIL."""


def venv_python() -> str:
    for rel in ("Scripts/python.exe", "bin/python"):
        cand = DEFAULT_SCRIPT.parent / ".venv-adversary-lg" / rel
        if cand.exists():
            return str(cand)
    raise _Skip("adversary venv absent — build scripts/.venv-adversary-lg from "
                "scripts/requirements-adversary-lg.txt")


def _drive(mode: str, prompt: str, env_extra: dict | None = None) -> dict:
    with tempfile.TemporaryDirectory() as td:
        pf = Path(td) / "prompt.txt"
        pf.write_text(prompt, encoding="utf-8")
        # A throwaway copy of the script cannot see lib/ next to itself.
        env = {**os.environ, **(env_extra or {}), "PYTHONPATH": os.pathsep.join(
            p for p in (str(DEFAULT_SCRIPT.parent), os.environ.get("PYTHONPATH", "")) if p)}
        r = subprocess.run([venv_python(), "-c", DRIVER, mode, str(script_path()), str(pf)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, stdin=subprocess.DEVNULL, check=False, timeout=300)
        assert r.returncode == 0, f"driver rc={r.returncode}\n{r.stderr[-1500:]}"
        return json.loads(r.stdout.strip().splitlines()[-1])


def _through_npm_shim(prompt: str) -> str:
    """Send `prompt` through _invoke_codex with CODEX_CMD at an npm-layout shim."""
    if os.name != "nt":
        raise _Skip("cmd.exe shim transport is Windows-only")
    if not shutil.which("node"):
        raise _Skip("node not on PATH — the npm shim needs it")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "codex.cmd").write_text(NPM_SHIM.replace("\n", "\r\n"), encoding="ascii")
        js = root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        js.parent.mkdir(parents=True)
        js.write_text(FAKE_CODEX_JS, encoding="utf-8")
        res = _drive("transport", prompt, {"CODEX_CMD": str(root / "codex.cmd")})
    assert res["rc"] == 0, f"shim rc={res['rc']} stderr={res['stderr'][-600:]}"
    return json.loads(res["stdout"])["prompt"]


# ------------------------------------------------------------- A/B. live shim

def test_multiline_prompt_survives_npm_shim():
    got = _through_npm_shim(THREE_LINES)
    assert got == THREE_LINES, (
        "codex received a different prompt than was sent — the cmd.exe newline "
        f"truncation is back.\n  sent {len(THREE_LINES.splitlines())} lines, "
        f"got {len(got.splitlines())}: {got!r}")


def test_cmd_metacharacters_are_not_parsed():
    got = _through_npm_shim(METACHARS)
    assert got == METACHARS, f"cmd.exe rewrote the prompt:\n  sent {METACHARS!r}\n  got  {got!r}"


# ------------------------------------------------------------- C/D. argv shape

def test_windows_mode_sends_prompt_on_stdin():
    seen = _drive("argv-stdin", THREE_LINES)
    assert seen["argv"][-1] == "-", f"argv must end in '-' (read stdin), got {seen['argv']}"
    assert THREE_LINES not in seen["argv"], "the prompt must not ride argv on Windows"
    # Byte-exact: input= through a text-mode pipe would arrive with CRLF line ends.
    assert seen["stdin_text"] == THREE_LINES, (
        f"stdin must carry the exact prompt, got {seen['stdin_text']!r}")


def test_codex_reviewer_is_read_only():
    """The comment said "sandbox read-only" but argv never set it, so the
    reviewer's sandbox came from ~/.codex/config.toml and the project trust level."""
    for mode in ("argv-plain", "argv-stdin"):
        argv = _drive(mode, THREE_LINES)["argv"]
        assert "--sandbox" in argv and argv[argv.index("--sandbox") + 1] == "read-only", (mode, argv)


def test_non_windows_argv_unchanged():
    seen = _drive("argv-plain", THREE_LINES)
    assert seen["argv"][1:] == ["exec", "--sandbox", "read-only", "--skip-git-repo-check", THREE_LINES], seen["argv"]
    assert seen["input"] is None and seen["stdin_devnull"], (
        "off Windows stdin must stay DEVNULL with no input=, as before the fix")


# --------------------------------------------------------------- E. live codex

def test_live_codex_sees_lines_two_and_three():
    if os.environ.get("ADVERSARY_LIVE_CODEX") != "1":
        raise _Skip("set ADVERSARY_LIVE_CODEX=1 to spend one real codex call")
    prompt = ("Reply with ONLY the tokens that start with MK- found anywhere in this "
              "message, one per line. If you find none, reply NONE.\n"
              "MK-ALPHA-417\n"
              "MK-БРАВО-902")
    res = _drive("transport", prompt)
    # codex echoes the prompt it received as the `user` block on stderr before it
    # calls the model; that block is where the incident showed line 1 only. Checking
    # it keeps the transport verdict independent of the model answer and of quota
    # (a usage-limit error still prints the block).
    seen = res["stderr"] + res["stdout"]
    assert "user\n" in res["stderr"], f"no codex transcript on stderr: {res['stderr'][-800:]!r}"
    assert "MK-ALPHA-417" in seen and "MK-БРАВО-902" in seen, (
        f"real codex did not receive prompt lines 2-3; stderr tail={res['stderr'][-800:]!r}")


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
