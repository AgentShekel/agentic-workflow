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
        # Host pg_isready first; then probe the compose-internal server for Docker-only
        # projects (no host postgres client by design — postgres is reachable only over
        # the compose network). First success wins; the docker probes are skipped fast
        # when their service name is absent. pg_isready needs no -U for a readiness check.
        "cmd_any": [
            ["pg_isready"],
            ["docker", "compose", "exec", "-T", "postgres", "pg_isready"],
            ["docker", "compose", "exec", "-T", "db", "pg_isready"],
            ["docker", "compose", "exec", "-T", "pg", "pg_isready"],
        ],
        "fix_msg": "Запусти PostgreSQL (`pg_isready` exit 0). Docker-only проекты: `docker compose up -d db` — preflight сам пробует `docker compose exec <svc> pg_isready`.",
        "auto_fix": "compose_up_db",
        # Fallback when every name above misses — probe the services the compose
        # file actually declares. See _discovered_probes.
        "compose_probe": {"kind": "postgres", "argv": ["pg_isready"]},
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
        # Host redis-cli first; then probe the compose-internal server for Docker-only
        # projects (no host redis client by design — redis is reachable only over the
        # compose network). First success wins; the docker probes are skipped fast when
        # their service name is absent. Mirrors the postgres host-probe fallback.
        "cmd_any": [
            ["redis-cli", "ping"],
            ["docker", "compose", "exec", "-T", "redis", "redis-cli", "ping"],
            ["docker", "compose", "exec", "-T", "cache", "redis-cli", "ping"],
            ["docker", "compose", "exec", "-T", "valkey", "redis-cli", "ping"],
        ],
        "fix_msg": "Запусти Redis (`redis-cli ping` → PONG). Docker-only проекты: `docker compose up -d redis` — preflight сам пробует `docker compose exec <svc> redis-cli ping`.",
        "auto_fix": "compose_up_redis",
        "compose_probe": {"kind": "redis", "argv": ["redis-cli", "ping"]},
    },
}


_DEFAULT_COMPOSE = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
_NONDEFAULT_COMPOSE_GLOBS = ("docker-compose.*.yml", "docker-compose.*.yaml",
                             "compose.*.yml", "compose.*.yaml")


def _find_compose_files(cwd: Path) -> tuple[list[str], list[str]]:
    """(defaults_present, nondefaults_present) compose filenames in cwd."""
    defaults = [f for f in _DEFAULT_COMPOSE if (cwd / f).exists()]
    nondefaults: list[str] = []
    for pat in _NONDEFAULT_COMPOSE_GLOBS:
        for p in sorted(cwd.glob(pat)):
            if p.name not in defaults and p.name not in nondefaults:
                nondefaults.append(p.name)
    return defaults, nondefaults


def _compose_file_to_inject(cwd: Path):
    """COMPOSE_FILE to set for a `docker compose` call when docker would NOT auto-find
    the project's compose file. Existing COMPOSE_FILE env -> None (respect it); a default
    filename present -> None (docker finds it, behaviour unchanged); only a non-default file
    (docker-compose.dev.yml, compose.<env>.yml) present -> return it. Generalises the
    per-service pg/redis docker-exec probes so a repo on a non-default compose filename
    (a real docker-compose.dev.yml on a non-default port) resolves without a manual COMPOSE_FILE."""
    if os.environ.get("COMPOSE_FILE"):
        return None
    defaults, nondefaults = _find_compose_files(cwd)
    if defaults or not nondefaults:
        return None
    return nondefaults[0]


def _any_compose_file(cwd: Path) -> bool:
    d, nd = _find_compose_files(cwd)
    return bool(d or nd)


# Service-name discovery. The docker-exec probes above list the service names a
# vanilla topology uses; every miss so far was patched by appending one more name
# (postgres 2026-06-03, redis 2026-06-04) or one more filename (2026-06-25) — the
# 3rd occurrence of the same class. Discovery reads the names the compose file
# actually declares, so `database` / `redis-cache` / `pg-main` resolve without a
# 4th patch. Patterns are substring-matched against the declared service names.
_SERVICE_PATTERNS = {
    "postgres": ("postgres", "postgresql", "pgsql", "database", "db", "pg"),
    "redis": ("redis", "valkey", "keydb", "cache"),
}

_SERVICES_CACHE: dict[str, list[str]] = {}


def _compose_services(cwd: Path) -> list[str]:
    """Service names declared by the project's compose file, or [] when unknown.

    Uses the same COMPOSE_FILE resolution as the probes, so a non-default filename
    is handled identically. ANY failure (no docker, no compose file, bad yaml,
    timeout) returns [] and the caller keeps its static list — discovery can only
    add probes, never remove them.
    """
    key = str(cwd)
    if key in _SERVICES_CACHE:
        return _SERVICES_CACHE[key]
    services: list[str] = []
    if _any_compose_file(cwd) and shutil.which("docker"):
        env = None
        cf = _compose_file_to_inject(cwd)
        if cf:
            env = {**os.environ, "COMPOSE_FILE": cf}
        try:
            r = subprocess.run(
                ["docker", "compose", "config", "--services"],
                capture_output=True, text=True, timeout=15, env=env,
            )
            if r.returncode == 0:
                services = [s.strip() for s in (r.stdout or "").splitlines() if s.strip()]
        except Exception:
            services = []
    _SERVICES_CACHE[key] = services
    return services


def _discovered_probes(kind: str, argv: list[str], cwd: Path) -> list[list[str]]:
    """`docker compose exec -T <svc> <argv>` for each declared service matching kind."""
    pats = _SERVICE_PATTERNS.get(kind, ())
    hits = [s for s in _compose_services(cwd) if any(p in s.lower() for p in pats)]
    return [["docker", "compose", "exec", "-T", s, *argv] for s in hits]


def _service_candidates(kind: str, cwd: Path, fallback: list[str]) -> list[str]:
    """Declared services matching kind, else the static fallback names."""
    pats = _SERVICE_PATTERNS.get(kind, ())
    hits = [s for s in _compose_services(cwd) if any(p in s.lower() for p in pats)]
    return hits or fallback


def auto_fix(name: str) -> tuple[bool, str]:
    """Attempt a SAFE auto-recovery for a failed tool. Return (success, message)."""
    cwd = Path.cwd()
    has_compose = _any_compose_file(cwd)

    if name == "docker_compose_up" and has_compose:
        ok, out = run_cmd(["docker", "compose", "up", "-d"])
        return ok, f"docker compose up -d → {'started services' if ok else 'failed: ' + out}"

    if name == "compose_up_db" and has_compose:
        # Declared service names first; the old hardcoded guesses stay as fallback.
        tried = _service_candidates("postgres", cwd, ["db", "postgres", "pg"])
        for svc in tried:
            ok, _ = run_cmd(["docker", "compose", "up", "-d", svc])
            if ok:
                return True, f"docker compose up -d {svc} → started"
        return False, f"no DB service started (tried: {', '.join(tried)})"

    if name == "compose_up_redis" and has_compose:
        tried = _service_candidates("redis", cwd, ["redis", "cache", "valkey"])
        for svc in tried:
            ok, _ = run_cmd(["docker", "compose", "up", "-d", svc])
            if ok:
                return True, f"docker compose up -d {svc} → started"
        return False, f"no Redis service started (tried: {', '.join(tried)})"

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
    env = None
    if cmd[:2] == ["docker", "compose"]:
        cf = _compose_file_to_inject(Path.cwd())
        if cf:
            env = {**os.environ, "COMPOSE_FILE": cf}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, env=env,
        )
        if result.returncode == 0:
            out = (result.stdout or result.stderr or "").strip().splitlines()
            return True, out[0] if out else "ok"
        return False, (result.stderr or result.stdout or f"exit {result.returncode}").strip().splitlines()[0]
    except subprocess.TimeoutExpired:
        return False, "timeout (>10s)"
    except Exception as e:
        return False, f"error: {e}"


CLAUDE_PROBE_TIMEOUT_S = 90

_CLAUDE_FIX = (
    "Headless-путь недоступен, а консилиум на M и L ходит только через него. "
    "Две известные причины, проверять в этом порядке. "
    "(1) Истёкший токен: `claude auth login` в обычном терминале. Из терминала "
    "протухший токен виден как 401 за секунду, изнутри сессии он даёт ровно эту "
    "тишину. "
    "(2) Хост запуска. Установлено 2026-08-31: вложенный `claude -p` работает из "
    "терминальной сессии `claude` и молчит из сессии внутри десктопного "
    "приложения. Один и тот же бинарь, те же креды, тот же argv. Ни версия, ни "
    "токен, ни унаследованные CLAUDE_CODE_*_AUTH_REFRESH этого не объясняют "
    "(проверено и опровергнуто). Значит M и L запускать из терминальной сессии "
    "`claude`, а не из десктопа. "
    "`claude setup-token` даёт долгоживущий токен вместо протухающего OAuth и "
    "снимает причину (1) насовсем."
)


def classify_claude_probe(rc, stdout: str, stderr: str, timed_out: bool) -> dict:
    """Decide what a `claude -p` probe result means. Pure, so every failure mode
    can be pinned against real captured output instead of a live broken machine.

    Two things here are counter-intuitive and both come from the 2026-08-31
    incident. Do not "simplify" either one away:

    1. `claude auth status` is NOT a usable check. With a fully expired token it
       still answered `{"loggedIn": true, ..., "subscriptionType": "max"}`. A
       cheap non-agentic probe reports healthy while every consilium role is
       about to fail. Only a real (tiny) agentic call proves the auth path works.
    2. A TIMEOUT IS AN AUTH FAILURE, not slowness. In a plain terminal an expired
       token returns `401 OAuth access token has expired` in about a second, but
       the same call nested inside a Claude Code session (which is where
       adversary_lg.py and validator_lg.py run) produced zero bytes on both
       streams for 170s+, three times, sandboxed and not. Reading that as "slow"
       is what turns one auth error into N silent role timeouts mid-engagement.
    """
    name = "claude-cli"
    if timed_out:
        return {
            "name": name, "status": "fail",
            "detail": f"`claude -p` produced nothing in {CLAUDE_PROBE_TIMEOUT_S}s. "
                      "Nested inside a session the headless path fails silently "
                      "instead of erroring, so silence is the only symptom there is. "
                      "An expired token produces exactly this (a plain terminal would "
                      "show 401), but it is not the only cause: the same silence was "
                      "observed 2026-08-31 with a freshly valid token, after one "
                      "successful call.",
            "fix": _CLAUDE_FIX,
        }
    blob = f"{stdout}\n{stderr}"
    if re.search(r"\b401\b|authenticate|OAuth access token|Invalid API key", blob, re.IGNORECASE):
        return {
            "name": name, "status": "fail",
            "detail": f"auth rejected: {(stderr or stdout).strip()[:200]}",
            "fix": _CLAUDE_FIX,
        }
    if rc != 0:
        return {
            "name": name, "status": "fail",
            "detail": f"`claude -p` exit {rc}: {(stderr or stdout).strip()[:200]}",
            "fix": _CLAUDE_FIX,
        }
    if not stdout.strip():
        return {
            "name": name, "status": "fail",
            "detail": "`claude -p` exited 0 with empty stdout — a reviewer would "
                      "return no verdict and read as 'produced nothing'.",
            "fix": _CLAUDE_FIX,
        }
    return {"name": name, "status": "pass",
            "detail": f"headless `claude -p` answered: {stdout.strip()[:60]!r}"}


def check_claude_cli() -> dict:
    """Prove the headless path the consilium rides is actually usable.

    `adversary_lg.py` and `validator_lg.py` dispatch every reviewer through
    `claude -p`. When that path is down the engagement does not fail loudly: it
    burns the full role timeout per role and returns empty output, which reads as
    "the reviewers found nothing" rather than "re-authenticate". Catching it at
    intake is the difference between one blocked intake and a wasted M/L cascade.

    Cost is one trivial model call (~5s) per intake. That is the price of the
    check being meaningful at all — see classify_claude_probe note 1.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from lib.claude_path import find_claude_cmd
    except Exception as e:
        return {"name": "claude-cli", "status": "fail",
                "detail": f"cannot import the claude resolver: {e}",
                "fix": "Restore scripts/lib/claude_path.py."}

    claude = find_claude_cmd()
    if not claude:
        return {"name": "claude-cli", "status": "fail",
                "detail": "claude CLI not found (PATH, env override and the known "
                          "install dirs were all probed)",
                "fix": "Install Claude Code CLI, or set CLAUDE_CLI_PATH to the binary."}

    # stdin=DEVNULL: a headless `claude -p` waits on stdin even WITH a prompt arg,
    # and an inherited never-closing pipe blocks it to the timeout with empty
    # stdout. Same guard adversary_lg.py carries, for the same reason.
    try:
        r = subprocess.run([claude, "-p", "Reply with exactly one word: ok"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL,
                           timeout=CLAUDE_PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return classify_claude_probe(None, "", "", timed_out=True)
    except Exception as e:
        return {"name": "claude-cli", "status": "fail",
                "detail": f"probe could not run: {e}", "fix": _CLAUDE_FIX}
    return classify_claude_probe(r.returncode, r.stdout or "", r.stderr or "",
                                 timed_out=False)


def check_tool(tool: str, allow_auto_fix: bool = False) -> dict:
    """Returns {name, status, detail, fix?, auto_fixed?}."""
    # Special check: not a `cmd` probe (see check_claude_cli for why a cheap
    # non-agentic probe cannot detect the failure it exists to catch).
    if tool == "claude-cli":
        return check_claude_cli()

    if tool in TOOL_CHECKS:
        spec = TOOL_CHECKS[tool]
        cmds = spec.get("cmd_any") or [spec["cmd"]]
        last_detail = ""
        for cmd in cmds:
            ok, detail = run_cmd(cmd)
            if ok:
                return {"name": tool, "status": "pass", "detail": detail}
            last_detail = detail

        # Declared probes exhausted. Ask the compose file for its real service
        # names before declaring the tool unreachable. Lazy on purpose: a vanilla
        # topology passes on the static list and never pays for the extra call.
        probe = spec.get("compose_probe")
        if probe:
            for cmd in _discovered_probes(probe["kind"], probe["argv"], Path.cwd()):
                if cmd in cmds:
                    continue
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
