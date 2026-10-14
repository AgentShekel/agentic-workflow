#!/usr/bin/env python3
"""Regression guard: agent tool grants live under `tools:`, and the lint checks that key.

Until 2026-10-06 every agent declared `allowed-tools:`, which Claude Code honours only in skills.
For subagents the key was silently ignored, so all 59 agents inherited every tool (Agent, Write,
Bash, every MCP server), and check-agent-models.py passed them all because it validated the same
ignored key. This pins both halves:

  A. LINT KEY        `allowed-tools:` is a violation; a missing or empty `tools:` is a violation;
                     inline and YAML-list `tools:` both parse, comments inside the list included.
  B. SPECIFIERS      `Bash(cmd:*)` inside `tools:` narrows nothing and is a violation;
                     `Agent(type)` is documented and allowed.
  C. DECLARED OPEN   `tools-unrestricted:` with a reason stays the one sanctioned open surface.
  D. LIVE CORPUS     no file in agents/ carries `allowed-tools:`, and the live lint exits 0.
  E. GUARD           hooks/agent-bash-guard.py lets through exactly the command its profile names
                     and blocks chaining, other scripts and write-capable git options, plus every
                     bash rewrite Codex showed slipping past a normalising parser (brace expansion,
                     backslash escapes, a quoted `~`); any malformed hook input exits 2.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2]
CHECKER = CLAUDE / "scripts" / "check-agent-models.py"
GUARD = CLAUDE / "hooks" / "agent-bash-guard.py"

spec = importlib.util.spec_from_file_location("check_agent_models", CHECKER)
cam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cam)


def fm(body: str) -> str:
    return f"---\nname: x\nmodel: sonnet\n{body}\n---\n\nbody\n"


LINT = [
    # (label, frontmatter body, expect_error_substring or None, expected tools)
    ("A ignored key", "allowed-tools: Read, Glob", "ignored for agents", None),
    ("A ignored key list", "allowed-tools:\n  - Read", "ignored for agents", None),
    ("A missing", "color: green", "no tools: line", None),
    ("A empty list", "tools:\ncolor: green", "is empty", None),
    ("A inline", "tools: Read, Glob, Grep", None, ["Read", "Glob", "Grep"]),
    ("A list+comment", "tools:\n  - Read\n  # why Write\n  - Write\ncolor: g", None, ["Read", "Write"]),
    ("A mcp server", "tools: Read, mcp__codex", None, ["Read", "mcp__codex"]),
    ("B bash specifier", "tools:\n  - Read\n  - Bash(python x.py:*)", "specifier", None),
    ("B agent allowlist", "tools: Read, Agent(worker, researcher)", None, ["Read", "Agent(worker, researcher)"]),
    ("B quoted flow spec", 'tools: [Read, "Bash(echo:*)"]', "specifier", None),
    ("B commented spec", "tools:\n  - Read\n  - Bash(echo:*) # narrowed?", "specifier", None),
    ("A comment only", "tools: # explanation\ncolor: g", "is empty", None),
    ("A flow list", "tools: [Read, Grep]", None, ["Read", "Grep"]),
    ("A unindented seq", "tools:\n- Read\n- Grep", None, ["Read", "Grep"]),
    ("A crlf", "tools:\r\n  - Read\r\ncolor: g", None, ["Read"]),
    ("C declared open", "tools-unrestricted: >\n  needs the live MCP roster", None, ["*"]),
    ("C empty reason", "tools-unrestricted:\ncolor: green", "needs a written reason", None),
    ("C empty folded", "tools-unrestricted: >\ncolor: green", "needs a written reason", None),
]

GUARD_CASES = [
    # (profile, command, allowed)
    ("contrast", 'python ~/.claude/scripts/contrast.py "#fff" "#2f9e44" --size 16', True),
    ("contrast", 'python3 ~/.claude/scripts/contrast.py "rgba(0,0,0,0.45)" "#ffffff"', True),
    ("contrast", f'python {Path.home().as_posix()}/.claude/scripts/contrast.py "#000" "#fff"', True),
    ("contrast", 'python ~/.claude/scripts/contrast.py "#fff" "#000" && rm -rf x', False),
    ("contrast", 'python ~/.claude/scripts/contrast.py "#fff" "#000"; curl evil', False),
    ("contrast", 'python ~/.claude/scripts/contrast.py $(cat secret)', False),
    ("contrast", "python ~/.claude/scripts/other.py", False),
    ("contrast", "python -c 'import os'", False),
    ("contrast", "cat ~/.claude/scripts/contrast.py", False),
    ("contrast", 'python ~/.claude/scripts/contrast.py "#fff" "#000" > out.json', False),
    ("contrast", 'python "~/.claude/scripts/contrast.py" "#fff" "#000"', False),   # quoted ~ stays literal
    ("contrast", 'python scripts\\contrast.py "#fff" "#000"', False),             # bash eats the backslash
    ("contrast", 'python ~/.claude/scripts/contrast.py{,x} "#fff"', False),       # brace expansion
    ("contrast", 'python ~/.claude/scripts/../scripts/contrast.py "#fff"', False),
    ("git-read", "git diff main..HEAD --stat", True),
    ("git-read", "git -C /repo diff main..HEAD --unified=0 -- '*.py'", True),
    ("git-read", "git --no-pager log --oneline -5", True),
    ("git-read", "git merge-base HEAD main", True),
    ("git-read", "git commit -m x", False),
    ("git-read", "git checkout main", False),
    ("git-read", "git diff --output=patch.txt", False),
    ("git-read", "git -c core.pager=sh diff", False),
    ("git-read", "cd /repo && git diff", False),
    ("git-read", "git diff | tee x", False),
    ("git-read", "git -C {.,-c,alias.x=!whoami,x} diff", False),               # brace -> -c injection
    ("git-read", "git diff --outpu\\t=review.patch", False),                    # escape hides --output
    ("git-read", "git diff --textconv HEAD~1", False),
    ("git-read", "git status", False),                                          # may run core.fsmonitor
    ("git-read", "git diff *", False),                                          # unquoted glob
    ("git-read", "git log --oneline HEAD~5..HEAD", True),
    ("audit", "npm audit --json", True),
    ("audit", "pnpm audit --prod", True),
    ("audit", "pip-audit -r requirements.txt --no-deps --disable-pip", True),
    ("audit", "pip-audit -r requirements.txt", False),                         # pip may run build code
    ("audit", "pip-audit --disable-pip --no-deps -r r.txt -o out.json", False),
    ("audit", "npm audit --registry https://attacker.example", False),
    ("audit", "npm audit --userconfig x.npmrc", False),
    ("audit", "osv-scanner fix --manifest package.json", False),
    ("audit", "pip-audit -r requirements.txt # --disable-pip", False),          # comment drops the flag
    ("audit", "pip-audit --disable-pip --no-deps -r r.txt -ovictim.json", False),  # attached short arg
    ("audit", "npm audit --reg=https://attacker.example", False),              # npm abbreviation
    ("audit", "npm audit --userc=other.npmrc", False),
    ("audit", "npm audit --prefix=C:/other-project", False),
    ("audit", "npm audit --audit-level=high --omit=dev --json", True),
    ("audit", "pnpm audit --audit-level high", True),
    ("audit", "pip-audit --disable-pip --no-deps -r requirements.txt -f json", True),
    ("git-read", "git log --outp=x.patch", False),                              # git abbreviation
    ("git-read", "git diff --oneline --stat --no-ext-diff main..HEAD", True),
    ("contrast", 'python ~/.claude/scripts/contrast.py "#fff" "#000" --over "#ffffff" --size 16 --weight 700', True),
    ("audit", "npm audit fix --force", False),
    ("audit", "pip-audit --fix", False),
    ("audit", "npm install lodash", False),
    ("audit", "npx some-scanner", False),
]


def guard(profile: str, command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    r = subprocess.run([sys.executable, str(GUARD), profile], input=payload,
                       capture_output=True, text=True, check=False)
    return r.returncode


def main() -> int:
    bad = 0
    for label, body, want_err, want_tools in LINT:
        tools, err = cam.tools_of(fm(body))
        ok = (want_err in (err or "")) if want_err else (err is None and (want_tools is None or tools == want_tools))
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: tools={tools} err={err}")

    leftovers = [p.name for p in (CLAUDE / "agents").glob("*.md")
                 if "\nallowed-tools:" in p.read_text(encoding="utf-8").replace("\r\n", "\n")]
    ok = not leftovers
    bad += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] D no allowed-tools in agents/: {leftovers}")
    r = subprocess.run([sys.executable, str(CHECKER), "--quiet"], capture_output=True, text=True, check=False)
    ok = r.returncode == 0
    bad += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] D live lint exit {r.returncode} {r.stdout.strip()[:200]}")

    for profile, command, allowed in GUARD_CASES:
        rc = guard(profile, command)
        ok = (rc == 0) == allowed
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] E {profile}: {'allow' if allowed else 'block'} {command[:70]} (rc={rc})")
    for raw in ("not json", "null", "[]", '{"tool_name": "Bash", "tool_input": [1]}',
                '{"tool_name": "Bash", "tool_input": {"command": 5}}',
                '{"tool_name": null, "tool_input": {"command": "echo bypass"}}',
                '{"tool_name": ["Bash"], "tool_input": {"command": "echo bypass"}}'):
        rc = subprocess.run([sys.executable, str(GUARD), "contrast"], input=raw,
                            capture_output=True, text=True, check=False).returncode
        ok = rc == 2
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] E malformed input {raw[:40]!r} fails closed (rc={rc})")

    print(f"\n{'OK' if not bad else f'{bad} FAILED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
