#!/usr/bin/env python3
"""Pre-flight tool check for agency engagements.

Verifies every tool in `tools_required` is reachable BEFORE secretary hands off
to a lead. Engagements starting with broken validation environments are the
root cause of CONDITIONAL-loop failures.

Usage:
  # Read tools_required from criteria.md frontmatter:
  python ~/.claude/scripts/preflight.py --criteria engagement/criteria.md

  # Explicit tool list:
  python ~/.claude/scripts/preflight.py --tools docker,playwright,postgres

  # Output JSON for automation:
  python ~/.claude/scripts/preflight.py --criteria ... --json

Exit codes:
  0 — all checks passed
  1 — at least one tool unreachable (engagement must NOT proceed)
  2 — invocation error (bad args, missing criteria.md, etc.)
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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOL_CHECKS = {
    "docker": {
        "cmd": ["docker", "info"],
        "fix_msg": "Запусти Docker Desktop. Подождите пока поднимется (`docker info` должен возвращать exit 0).",
        # Auto-fix: only attempts `docker compose up -d` if a compose file exists in CWD.
        # Does NOT start Docker Desktop itself (Windows GUI app, not safe to auto-launch).
        "auto_fix": "docker_compose_up",
    },
    "playwright": {
        "cmd_any": [
            ["npx", "playwright", "--version"],
            ["python", "-m", "playwright", "--version"],
            ["pwsh", "-c", "playwright --version"],
        ],
        "fix_msg": "Установи Playwright: `npm i -D @playwright/test && npx playwright install` (или `pip install playwright && playwright install`).",
        "auto_fix": "playwright_install",
    },
    "postgres": {
        "cmd": ["pg_isready"],
        "fix_msg": "Запусти PostgreSQL (`pg_isready` должен возвращать exit 0). В docker-compose проектах: `docker compose up -d db`.",
        "auto_fix": "compose_up_db",
    },
    "node": {
        "cmd": ["node", "--version"],
        "fix_msg": "Установи Node.js (https://nodejs.org).",
        # Don't auto-install runtime — that's user choice.
        "auto_fix": None,
    },
    "python": {
        "cmd": ["python", "--version"],
        "fix_msg": "Установи Python 3.11+ (https://python.org).",
        "auto_fix": None,
    },
    "bun": {
        "cmd": ["bun", "--version"],
        "fix_msg": "Установи Bun (https://bun.sh).",
        "auto_fix": None,
    },
    "git": {
        "cmd": ["git", "--version"],
        "fix_msg": "Установи Git.",
        "auto_fix": None,
    },
    "gh": {
        "cmd": ["gh", "--version"],
        "fix_msg": "Установи GitHub CLI (`gh`).",
        "auto_fix": None,
    },
    "redis": {
        "cmd_any": [["redis-cli", "ping"]],
        "fix_msg": "Запусти Redis (`redis-cli ping` должен возвращать PONG).",
        "auto_fix": "compose_up_redis",
    },
}


def auto_fix(name: str) -> tuple[bool, str]:
    """Attempt a SAFE auto-recovery for a failed tool. Return (success, message)."""
    cwd = Path.cwd()
    has_compose = any((cwd / f).exists() for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"])

    if name == "docker_compose_up" and has_compose:
        ok, out = run_cmd(["docker", "compose", "up", "-d"])
        return ok, f"docker compose up -d → {'started services' if ok else 'failed: ' + out}"

    if name == "compose_up_db" and has_compose:
        # Heuristic: try common DB service names
        for svc in ["db", "postgres", "pg"]:
            ok, _ = run_cmd(["docker", "compose", "up", "-d", svc])
            if ok:
                return True, f"docker compose up -d {svc} → started"
        return False, "no DB service found in compose file (tried: db, postgres, pg)"

    if name == "compose_up_redis" and has_compose:
        ok, out = run_cmd(["docker", "compose", "up", "-d", "redis"])
        return ok, f"docker compose up -d redis → {'started' if ok else 'failed: ' + out}"

    if name == "playwright_install":
        # npx is non-destructive; install dev dep first
        if (cwd / "package.json").exists():
            ok1, _ = run_cmd(["npm", "i", "-D", "@playwright/test"])
            if ok1:
                ok2, _ = run_cmd(["npx", "playwright", "install"])
                return ok2, "npm i -D @playwright/test && npx playwright install"
        # Fall back to pip
        ok, _ = run_cmd(["python", "-m", "pip", "install", "playwright"])
        if ok:
            ok2, _ = run_cmd(["python", "-m", "playwright", "install"])
            return ok2, "pip install playwright && playwright install"
        return False, "no package.json AND pip install failed"

    return False, f"no auto-fix recipe for '{name}' (or prerequisite missing, e.g. compose file)"

# Env-var presence checks — value not read, only existence
ENV_CHECKS = {
    "yandex-tokens": {
        "vars": ["YANDEX_OAUTH_TOKEN", "YANDEX_DIRECT_TOKEN", "YANDEX_METRIKA_TOKEN", "YANDEX_WEBMASTER_TOKEN"],
        "any_of": True,  # at least one
        "fix_msg": "Заполни ~/.claude/skills/yandex-analytics/config/.env с Yandex API токенами и запусти sync-config.sh.",
    },
    "openai-key": {
        "vars": ["OPENAI_API_KEY"],
        "fix_msg": "Добавь OPENAI_API_KEY в .env проекта.",
    },
    "anthropic-key": {
        "vars": ["ANTHROPIC_API_KEY"],
        "fix_msg": "Добавь ANTHROPIC_API_KEY в .env проекта.",
    },
}


def parse_criteria_frontmatter(path: Path) -> list[str]:
    """Extract tools_required list from criteria.md frontmatter."""
    if not path.exists():
        raise FileNotFoundError(f"criteria.md not found: {path}")
    text = path.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return []
    body = fm.group(1)
    # tools_required: [a, b, c]   OR   tools_required:\n  - a\n  - b
    inline = re.search(r"^tools_required:\s*\[([^\]]*)\]", body, re.MULTILINE)
    if inline:
        items = [x.strip().strip('"').strip("'") for x in inline.group(1).split(",")]
        return [x for x in items if x]
    block = re.search(r"^tools_required:\s*\n((?:\s+-\s+\S+\n?)+)", body, re.MULTILINE)
    if block:
        return re.findall(r"^\s+-\s+(\S+)", block.group(1), re.MULTILINE)
    return []


def run_cmd(cmd: list[str]) -> tuple[bool, str]:
    """Run a command, return (success, stderr/stdout snippet)."""
    if not shutil.which(cmd[0]):
        return False, f"command not found: {cmd[0]}"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            out = (result.stdout or result.stderr or "").strip().splitlines()
            return True, out[0] if out else "ok"
        return False, (result.stderr or result.stdout or f"exit {result.returncode}").strip().splitlines()[0]
    except subprocess.TimeoutExpired:
        return False, "timeout (>10s)"
    except Exception as e:
        return False, f"error: {e}"


def check_tool(tool: str, allow_auto_fix: bool = False) -> dict:
    """Returns {name, status, detail, fix?, auto_fixed?}."""
    if tool in TOOL_CHECKS:
        spec = TOOL_CHECKS[tool]
        cmds = spec.get("cmd_any") or [spec["cmd"]]
        last_detail = ""
        for cmd in cmds:
            ok, detail = run_cmd(cmd)
            if ok:
                return {"name": tool, "status": "pass", "detail": detail}
            last_detail = detail

        # Failed; attempt auto-fix if allowed and recipe exists
        if allow_auto_fix and spec.get("auto_fix"):
            fixed, fix_detail = auto_fix(spec["auto_fix"])
            if fixed:
                # Re-check after auto-fix
                for cmd in cmds:
                    ok, detail = run_cmd(cmd)
                    if ok:
                        return {
                            "name": tool, "status": "pass",
                            "detail": f"{detail} (after auto-fix: {fix_detail})",
                            "auto_fixed": True,
                        }
                # Auto-fix recipe ran but tool still unreachable — distinct status so
                # user sees that auto-fix was attempted vs blocked from the start
                return {
                    "name": tool, "status": "auto-fix-failed",
                    "detail": f"original blocker: {last_detail}",
                    "auto_fix_attempted": fix_detail,
                    "fix": spec["fix_msg"],
                }
            else:
                return {
                    "name": tool, "status": "auto-fix-unavailable",
                    "detail": f"original blocker: {last_detail}",
                    "auto_fix_attempted": fix_detail,
                    "fix": spec["fix_msg"],
                }

        return {"name": tool, "status": "fail", "detail": last_detail, "fix": spec["fix_msg"]}

    if tool in ENV_CHECKS:
        spec = ENV_CHECKS[tool]
        present = [v for v in spec["vars"] if os.environ.get(v) or _check_dotenv(v)]
        if spec.get("any_of"):
            ok = bool(present)
        else:
            ok = len(present) == len(spec["vars"])
        if ok:
            return {"name": tool, "status": "pass", "detail": f"env vars present: {present}"}
        missing = [v for v in spec["vars"] if v not in present]
        return {"name": tool, "status": "fail", "detail": f"missing: {missing}", "fix": spec["fix_msg"]}

    return {"name": tool, "status": "unknown", "detail": "no check defined for this tool name", "fix": f"Add check for '{tool}' to preflight.py TOOL_CHECKS or ENV_CHECKS."}


def _check_dotenv(var: str) -> bool:
    """Light-touch .env scan in CWD (presence of var name, not value)."""
    for candidate in [Path.cwd() / ".env", Path.cwd() / ".env.local"]:
        if candidate.exists():
            try:
                if re.search(rf"^{var}\s*=", candidate.read_text(encoding="utf-8"), re.MULTILINE):
                    return True
            except Exception:
                pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight tools check for agency engagement")
    parser.add_argument("--criteria", help="Path to engagement/criteria.md (reads tools_required from frontmatter)")
    parser.add_argument("--tools", help="Comma-separated tools list (overrides --criteria)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    parser.add_argument("--auto-fix", action="store_true",
                        help="Attempt safe auto-recovery for failing tools (docker compose up, npm install). Skips destructive ops.")
    args = parser.parse_args()

    tools: list[str] = []
    if args.tools:
        tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    elif args.criteria:
        try:
            tools = parse_criteria_frontmatter(Path(args.criteria))
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
    else:
        print("ERROR: provide --criteria PATH or --tools a,b,c", file=sys.stderr)
        return 2

    if not tools:
        msg = "No tools_required specified. Engagement may proceed (no validation env needed)."
        if args.json:
            print(json.dumps({"status": "pass", "tools": [], "message": msg}))
        else:
            print(msg)
        return 0

    results = [check_tool(t, allow_auto_fix=args.auto_fix) for t in tools]
    any_fail = any(r["status"] not in {"pass"} for r in results)

    if args.json:
        print(json.dumps({
            "status": "fail" if any_fail else "pass",
            "tools": results,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = {
                "pass": "[OK]",
                "fail": "[FAIL]",
                "auto-fix-failed": "[FIX-RAN-FAIL]",
                "auto-fix-unavailable": "[NO-AUTO-FIX]",
            }.get(r["status"], "[?]")
            print(f"{mark} {r['name']}: {r['detail']}")
            if r.get("auto_fix_attempted"):
                print(f"        Auto-fix attempt: {r['auto_fix_attempted']}")
            if r["status"] != "pass":
                print(f"        Manual fix:       {r.get('fix', 'unknown')}")
        print()
        print("VERDICT:", "FAIL — engagement must NOT start until tools are reachable" if any_fail else "PASS — proceed to lead handoff")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
