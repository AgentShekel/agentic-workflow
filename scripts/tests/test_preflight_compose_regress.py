#!/usr/bin/env python3
"""Regression guard — preflight compose topology resolution.

Locks in the fixes for the recurring "probe matrix hardcodes a vanilla compose
topology" class, which was patched reactively three times:

  2026-06-03  postgres unreachable on a Docker-only project (host pg_isready only)
  2026-06-04  redis, same shape
  a compose file named docker-compose.dev.yml with service `postgres` on a
              non-default host port: bare preflight false-negatives postgres

Each was closed by appending one more hardcoded name. This file pins the two
generalisations so a 4th name is never needed:

  A. non-default compose FILENAME  -> COMPOSE_FILE injected into docker compose calls
  B. non-standard SERVICE name     -> probes discovered from `compose config --services`

Run standalone (harness gate) or under pytest:
  python test_preflight_compose_regress.py
  python test_preflight_compose_regress.py --script /tmp/patched-preflight.py
  pytest test_preflight_compose_regress.py -q

--script points the whole suite at a throwaway copy, which is how the gate proves
red before green.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "preflight.py"
_SCRIPT_OVERRIDE: Path | None = None


def load_preflight():
    """Fresh module instance per test — module-level caches must not leak."""
    path = _SCRIPT_OVERRIDE or DEFAULT_SCRIPT
    spec = importlib.util.spec_from_file_location("preflight_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class chdir_tmp:
    """cwd swap with restore — preflight reads Path.cwd() internally."""

    def __init__(self, path: Path):
        self.path = path
        self.prev = None

    def __enter__(self):
        self.prev = os.getcwd()
        os.chdir(self.path)
        return self.path

    def __exit__(self, *exc):
        os.chdir(self.prev)


def _mkdir(tmp: Path, name: str, files: list[str]) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_text("services: {}\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------- A. filename

def test_compose_file_injection_matrix(tmp_path: Path):
    pf = load_preflight()
    os.environ.pop("COMPOSE_FILE", None)

    default_only = _mkdir(tmp_path, "default_only", ["docker-compose.yml"])
    nondefault_only = _mkdir(tmp_path, "nondefault_only", ["docker-compose.dev.yml"])
    both = _mkdir(tmp_path, "both", ["docker-compose.yml", "docker-compose.dev.yml"])
    empty = _mkdir(tmp_path, "empty", [])

    # docker finds a default filename by itself -> do not override it
    assert pf._compose_file_to_inject(default_only) is None
    assert pf._compose_file_to_inject(both) is None
    assert pf._compose_file_to_inject(empty) is None
    # the 2026-06-25 case: only a non-default file exists -> inject it
    assert pf._compose_file_to_inject(nondefault_only) == "docker-compose.dev.yml"

    # an operator-set COMPOSE_FILE always wins
    os.environ["COMPOSE_FILE"] = "custom.yml"
    try:
        assert pf._compose_file_to_inject(nondefault_only) is None
    finally:
        os.environ.pop("COMPOSE_FILE", None)


def test_run_cmd_injects_compose_file_env(tmp_path: Path):
    pf = load_preflight()
    os.environ.pop("COMPOSE_FILE", None)
    seen = {}

    class FakeCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env")
        return FakeCompleted()

    pf.subprocess.run = fake_run
    pf.shutil.which = lambda _c: "/usr/bin/docker"

    with chdir_tmp(_mkdir(tmp_path, "nd", ["docker-compose.dev.yml"])):
        pf.run_cmd(["docker", "compose", "exec", "-T", "postgres", "pg_isready"])
    assert seen["env"] is not None, "COMPOSE_FILE must be injected for a non-default filename"
    assert seen["env"]["COMPOSE_FILE"] == "docker-compose.dev.yml"

    with chdir_tmp(_mkdir(tmp_path, "d", ["docker-compose.yml"])):
        pf.run_cmd(["docker", "compose", "ps"])
    assert seen["env"] is None, "default filename must keep docker's own resolution"

    with chdir_tmp(_mkdir(tmp_path, "nd2", ["docker-compose.dev.yml"])):
        pf.run_cmd(["pg_isready"])
    assert seen["env"] is None, "non-compose commands must not get a compose env"


# ----------------------------------------------------------------- B. service

def test_discovered_probes_match_declared_services(tmp_path: Path):
    pf = load_preflight()
    pf._compose_services = lambda _cwd: ["api", "database", "redis-cache", "worker"]

    pg = pf._discovered_probes("postgres", ["pg_isready"], tmp_path)
    assert pg == [["docker", "compose", "exec", "-T", "database", "pg_isready"]], pg

    rd = pf._discovered_probes("redis", ["redis-cli", "ping"], tmp_path)
    assert rd == [["docker", "compose", "exec", "-T", "redis-cache", "redis-cli", "ping"]], rd


def test_discovery_failure_is_inert(tmp_path: Path):
    """No docker / no compose / bad yaml -> [] -> static list unchanged."""
    pf = load_preflight()
    pf._compose_services = lambda _cwd: []
    assert pf._discovered_probes("postgres", ["pg_isready"], tmp_path) == []
    assert pf._service_candidates("postgres", tmp_path, ["db", "postgres", "pg"]) == \
        ["db", "postgres", "pg"]


def test_compose_services_swallows_failures(tmp_path: Path):
    pf = load_preflight()

    def boom(*_a, **_kw):
        raise OSError("docker not there")

    pf.subprocess.run = boom
    pf.shutil.which = lambda _c: "/usr/bin/docker"
    d = _mkdir(tmp_path, "svc_fail", ["docker-compose.yml"])
    assert pf._compose_services(d) == [], "discovery must never raise into the caller"


def test_check_tool_tries_discovery_only_after_static_probes(tmp_path: Path):
    pf = load_preflight()
    attempted: list[list[str]] = []
    discovery_calls = {"n": 0}

    def fake_run_cmd(cmd):
        attempted.append(list(cmd))
        return False, "nope"

    def fake_services(_cwd):
        discovery_calls["n"] += 1
        return ["api", "database"]

    pf.run_cmd = fake_run_cmd
    pf._compose_services = fake_services

    with chdir_tmp(_mkdir(tmp_path, "disc", ["docker-compose.dev.yml"])):
        res = pf.check_tool("postgres", allow_auto_fix=False)

    assert res["status"] == "fail"
    assert attempted[0] == ["pg_isready"], "host probe must stay first"
    assert ["docker", "compose", "exec", "-T", "database", "pg_isready"] in attempted, \
        "a service named `database` must be probed instead of missed"
    assert attempted.index(["docker", "compose", "exec", "-T", "database", "pg_isready"]) > \
        attempted.index(["docker", "compose", "exec", "-T", "postgres", "pg_isready"]), \
        "discovery runs after the declared names, not instead of them"
    assert discovery_calls["n"] >= 1


def test_check_tool_skips_discovery_on_happy_path(tmp_path: Path):
    """A vanilla topology must not pay for `compose config --services`."""
    pf = load_preflight()
    discovery_calls = {"n": 0}

    def fake_services(_cwd):
        discovery_calls["n"] += 1
        return ["db"]

    pf.run_cmd = lambda cmd: (True, "accepting connections")
    pf._compose_services = fake_services

    with chdir_tmp(_mkdir(tmp_path, "happy", ["docker-compose.yml"])):
        res = pf.check_tool("postgres", allow_auto_fix=False)

    assert res["status"] == "pass"
    assert discovery_calls["n"] == 0, "discovery must be lazy"


def test_autofix_uses_declared_service_names(tmp_path: Path):
    pf = load_preflight()
    started: list[str] = []

    def fake_run_cmd(cmd):
        started.append(cmd[-1])
        return (cmd[-1] == "database"), "x"

    pf.run_cmd = fake_run_cmd
    pf._compose_services = lambda _cwd: ["api", "database"]

    with chdir_tmp(_mkdir(tmp_path, "af", ["docker-compose.dev.yml"])):
        ok, msg = pf.auto_fix("compose_up_db")

    assert ok, msg
    assert "database" in msg
    assert started == ["database"], f"must not blind-guess db/postgres/pg first: {started}"


def test_redis_autofix_covers_all_fallback_names(tmp_path: Path):
    """compose_up_redis used to try `redis` only while its probe list had three."""
    pf = load_preflight()
    tried: list[str] = []

    def fake_run_cmd(cmd):
        tried.append(cmd[-1])
        return (cmd[-1] == "valkey"), "x"

    pf.run_cmd = fake_run_cmd
    pf._compose_services = lambda _cwd: []

    with chdir_tmp(_mkdir(tmp_path, "rf", ["docker-compose.yml"])):
        ok, _msg = pf.auto_fix("compose_up_redis")

    assert ok, f"valkey must be reachable via auto-fix; tried={tried}"
    assert tried == ["redis", "cache", "valkey"], tried


# --------------------------------------------------------------------- runner

def _run_standalone() -> int:
    import tempfile
    import traceback

    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"  PASS  {name}")
            except Exception:
                failed += 1
                print(f"  FAIL  {name}")
                traceback.print_exc()
    target = _SCRIPT_OVERRIDE or DEFAULT_SCRIPT
    print(f"\n{len(tests) - failed}/{len(tests)} passed  (target: {target})")
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--script" in argv:
        _SCRIPT_OVERRIDE = Path(argv[argv.index("--script") + 1]).resolve()
    sys.exit(_run_standalone())
