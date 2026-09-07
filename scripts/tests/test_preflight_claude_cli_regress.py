#!/usr/bin/env python3
"""Regression guard — preflight `claude-cli` check.

On 2026-08-31 the Claude Code OAuth token expired. Nothing noticed. The binary
answered `--version` instantly, and `claude auth status` reported
`{"loggedIn": true, ..., "subscriptionType": "max"}` while every headless call was
already dead. Nested inside a session the dead call did not error either: it
returned zero bytes on both streams for 170s+, three times, sandboxed and not.

That combination is why this check exists and why it is shaped the way it is. An
M/L engagement would have spent the full role timeout per consilium role and
reported empty output, and the diagnosis would have pointed at the reviewers
instead of at auth.

  A. TIMEOUT IS AUTH        silence is the nested signature of an expired token,
                            not slowness. Reading it as slowness is the whole bug.
  B. REAL 401 TEXT          the exact string the CLI produced that day, verbatim,
                            must classify as a failure.
  C. EXIT 0 IS NOT ENOUGH   rc=0 with empty stdout is a reviewer that returns no
                            verdict; it must fail, not pass.
  D. HEALTHY PASSES         a normal answer passes, or the check is a permanent
                            blocker and gets removed within a week.
  E. AUTH-STATUS TRAP       the JSON `claude auth status` printed while broken must
                            NOT be able to satisfy this check. Pinned so nobody
                            "optimises" the probe into the cheap, useless form.
  F. LIVE PROBE             the real check against the real machine right now.
                            Skips loudly rather than failing if the CLI is absent.

Run standalone or under pytest:
  python test_preflight_claude_cli_regress.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location("_preflight", SCRIPTS_DIR / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
sys.modules["_preflight"] = preflight
_spec.loader.exec_module(preflight)

# Verbatim, as the CLI printed it in PowerShell on 2026-08-31.
REAL_401 = ("Failed to authenticate. API Error: 401 OAuth access token has expired. "
            "Re-authenticate to continue.")

# Verbatim `claude auth status` output from the SAME broken machine, minutes before
# the successful re-login. This is the trap: it looks entirely healthy.
REAL_AUTH_STATUS = (
    '{\n  "loggedIn": true,\n  "authMethod": "claude.ai",\n'
    '  "apiProvider": "firstParty",\n  "email": "redacted@example.com",\n'
    '  "orgId": "redacted",\n  "orgName": "redacted",\n'
    '  "subscriptionType": "max"\n}'
)

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def main() -> int:
    cls = preflight.classify_claude_probe

    # --- A. timeout is auth --------------------------------------------------
    r = cls(None, "", "", timed_out=True)
    check(r["status"] == "fail", f"A: a silent timeout must fail, got {r['status']}")
    check("expired" in r["detail"].lower(),
          "A: the detail must name the expired token as a cause, not report slowness")
    check("not the only cause" in r["detail"],
          "A: it must NOT claim the token is the only cause — the same silence was "
          "seen 2026-08-31 with a valid token, and a check that names one cause "
          "sends the reader down one road")
    check("auth login" in (r.get("fix") or ""), "A: the fix must tell the user to re-login")

    # --- B. the real 401 -----------------------------------------------------
    for where in ("stderr", "stdout"):
        r = cls(1, REAL_401 if where == "stdout" else "",
                REAL_401 if where == "stderr" else "", timed_out=False)
        check(r["status"] == "fail", f"B: the real 401 on {where} must fail")
        check("auth login" in (r.get("fix") or ""), f"B: 401 on {where} must carry the fix")

    # a 401 that somehow arrives with rc=0 is still a 401
    r = cls(0, REAL_401, "", timed_out=False)
    check(r["status"] == "fail", "B: a 401 body must fail even on exit 0")

    # --- C. exit 0 is not enough ---------------------------------------------
    r = cls(0, "", "", timed_out=False)
    check(r["status"] == "fail", "C: rc=0 with empty stdout must fail")
    check("no verdict" in r["detail"], "C: the detail must explain what it costs downstream")

    r = cls(0, "   \n  ", "", timed_out=False)
    check(r["status"] == "fail", "C: whitespace-only stdout is empty stdout")

    # --- D. healthy passes ---------------------------------------------------
    r = cls(0, "ok\n", "", timed_out=False)
    check(r["status"] == "pass", f"D: a normal answer must pass, got {r['status']}")
    check("ok" in r["detail"], "D: a pass should show what came back")

    # a non-zero exit with no recognisable auth text still fails, but as an exit
    r = cls(127, "", "command not found", timed_out=False)
    check(r["status"] == "fail", "D: a non-zero exit must fail")

    # --- E. the auth-status trap ---------------------------------------------
    # If someone reimplements the probe as `claude auth status`, this is what it
    # would feed in: exit 0, healthy-looking JSON, from a machine that was broken.
    r = cls(0, REAL_AUTH_STATUS, "", timed_out=False)
    check(r["status"] == "pass",
          "E: sanity — this text alone is not self-evidently broken, which is exactly "
          "why `auth status` cannot be the probe; the guard is that check_claude_cli "
          "calls `claude -p`, asserted below")
    src = (SCRIPTS_DIR / "preflight.py").read_text(encoding="utf-8")
    fn = src.split("def check_claude_cli", 1)[1].split("\ndef ", 1)[0]
    check('"-p"' in fn, "E: check_claude_cli must probe with `claude -p` (a real agentic "
                        "call); a non-agentic probe passes on an expired token")
    check("auth status" not in fn.replace("auth status` is NOT", ""),
          "E: check_claude_cli must not be reduced to `claude auth status`")
    check("stdin=subprocess.DEVNULL" in fn,
          "E: the probe must close stdin or it hangs regardless of auth state")

    # --- F. live probe -------------------------------------------------------
    # Reported, never fatal. This suite pins the CHECK's logic; whether the machine
    # is healthy right now is preflight's job at intake, which is the entire point
    # of having built the check. A regression suite that goes red because an OAuth
    # token expired is a suite people learn to ignore.
    from lib.claude_path import find_claude_cmd
    if not find_claude_cmd():
        print("NOTE: claude CLI not resolvable here — live probe skipped, not passed.")
    else:
        live = preflight.check_claude_cli()
        check(live["status"] in ("pass", "fail"), "F: live probe must return a verdict")
        if live["status"] == "pass":
            print(f"NOTE: live headless path OK — {live['detail']}")
        else:
            print("NOTE: live headless path is DOWN right now. Not a test failure; "
                  "this is the check working. Any M/L engagement started in this "
                  f"state would lose its consilium.\n      {live['detail']}")

    if FAILURES:
        print(f"FAIL — {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS — preflight claude-cli regressions held")
    return 0


def test_preflight_claude_cli_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
