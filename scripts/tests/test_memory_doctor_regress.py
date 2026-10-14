#!/usr/bin/env python3
"""Regression guard: memory-doctor.py catches what would rot the auto-memory silently.

Our memory is a
directory of one-fact markdown files plus a MEMORY.md index loaded every session; nothing
validated it. memory-doctor.py checks it; --hook is silent unless something is wrong.

  A. HEALTHY      a valid dir (incl. the frontmatter-less loop logs) -> exit 0, hook silent
  B. SECRET       a token-shaped string in a memory file -> error, reported by the hook
  C. BROKEN LINK  an index link to a missing file -> error
  D. FRONTMATTER  a fact file without frontmatter / with an unknown type -> error
  E. INDEX SIZE   MEMORY.md over 200 lines -> error (it is truncated beyond that)
  F. DUPLICATE    two files with the same `name:` -> error
  G. ORPHAN       a file unreachable from the index -> warning only, hook stays silent
  H. HOOK PATH    --hook resolves the memory dir from the payload cwd like Claude Code does
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "memory-doctor.py"


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def fact(name, type_="project", body="x"):
    return f"---\nname: {name}\ndescription: d\nmetadata:\n  type: {type_}\n---\n\n{body}\n"


def mkdir(root: Path, files: dict) -> Path:
    d = Path(tempfile.mkdtemp(dir=root)) / "memory"
    d.mkdir()
    for n, t in files.items():
        (d / n).write_text(t, encoding="utf-8")
    return d


def run(*args, stdin=""):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=60, check=False)


BASE = {
    "MEMORY.md": "# Memory Index\n- [A](a.md) — a\n- [Log](skill-evolution-log.md) — loop data\n",
    "a.md": fact("a"),
    "skill-evolution-log.md": "SIGNAL | domain: dev\n",
}


def main() -> int:
    results = []
    if not SCRIPT.exists():
        print(f"  [FAIL] {SCRIPT.name} missing")
        return 1
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        d = mkdir(tmp, BASE)
        p = run(str(d))
        results.append(check("A healthy dir -> exit 0", p.returncode == 0, p.stdout + p.stderr))
        p = run(str(d), "--hook")
        results.append(check("A healthy dir -> hook silent", p.stdout.strip() == "", p.stdout))

        cases = {
            "B secret": {**BASE, "a.md": fact("a", body="token glpat-AbCdEfGhIjKlMnOpQrSt12")},
            "C broken link": {**BASE, "MEMORY.md": BASE["MEMORY.md"] + "- [Gone](gone.md) — x\n"},
            "D no frontmatter": {**BASE, "a.md": "just text\n"},
            "D unknown type": {**BASE, "a.md": fact("a", type_="misc")},
            "E index too long": {**BASE, "MEMORY.md": BASE["MEMORY.md"] + "line\n" * 205},
            # Codex review 2026-10-14: 201 lines without a trailing newline is still 201 lines
            "E index 201 lines, no final newline": {**BASE, "MEMORY.md": "\n".join(
                [BASE["MEMORY.md"].rstrip("\n")] + ["line"] * (201 - BASE["MEMORY.md"].count("\n")))},
            "F duplicate name": {**BASE, "b.md": fact("a"),
                                 "MEMORY.md": BASE["MEMORY.md"] + "- [B](b.md) — b\n"},
        }
        # The hook speaks only for safety and index integrity (B, C, E). Format issues (D, F) are in
        # the full report: legacy projects hold pre-frontmatter files, and a hook that nags at every
        # session start about formatting gets ignored, including the day it reports a secret.
        severe = {"B secret", "C broken link", "E index too long", "E index 201 lines, no final newline"}
        for label, files in cases.items():
            d = mkdir(tmp, files)
            p = run(str(d))
            h = run(str(d), "--hook")
            results.append(check(f"{label} -> exit 1", p.returncode == 1, p.stdout))
            if label in severe:
                results.append(check(f"{label} -> hook reports it", h.stdout.strip() != "", h.stdout))
            else:
                results.append(check(f"{label} -> hook stays silent (format, not safety)", h.stdout.strip() == "", h.stdout))
            if label == "B secret":
                results.append(check("B the report never prints the secret itself",
                                     "AbCdEfGhIjKlMnOp" not in p.stdout + h.stdout, p.stdout))

        d = mkdir(tmp, {"a.md": fact("a")})  # a project memory dir that never got an index
        p = run(str(d))
        h = run(str(d), "--hook")
        results.append(check("I no MEMORY.md -> warning, exit 0", p.returncode == 0 and "MEMORY.md" in p.stdout, p.stdout))
        results.append(check("I no MEMORY.md -> hook silent", h.stdout.strip() == "", h.stdout))

        d = mkdir(tmp, {**BASE, "stray.md": fact("stray")})
        p = run(str(d))
        h = run(str(d), "--hook")
        results.append(check("G orphan -> warning, exit 0", p.returncode == 0 and "stray.md" in p.stdout, p.stdout))
        results.append(check("G orphan -> hook silent", h.stdout.strip() == "", h.stdout))

        home = tmp / "home"
        mem = home / ".claude" / "projects" / "C--work-x" / "memory"
        mem.mkdir(parents=True)
        for n, t in {**BASE, "a.md": fact("a", body="ghp_" + "a" * 36)}.items():
            (mem / n).write_text(t, encoding="utf-8")
        p = run("--hook", "--home", str(home), stdin=json.dumps({"cwd": "C:" + chr(92) + "work-x", "hook_event_name": "SessionStart"}))
        results.append(check("H --hook finds the project memory dir from the payload cwd", "secret" in p.stdout.lower(),
                             p.stdout + p.stderr))
        p = run("--hook", "--home", str(home), stdin="{not json")
        results.append(check("H malformed payload -> silent exit 0", p.returncode == 0 and p.stdout.strip() == "", p.stdout))

        # review round 1 (2026-10-10)
        bs = chr(92)
        mem2 = home / ".claude" / "projects" / "C--Users-x--claude" / "memory"
        mem2.mkdir(parents=True)
        for n, t in {**BASE, "a.md": fact("a", body="ghp_" + "b" * 36)}.items():
            (mem2 / n).write_text(t, encoding="utf-8")
        p = run("--hook", "--home", str(home),
                stdin=json.dumps({"cwd": "C:" + bs + "Users" + bs + "x" + bs + ".claude"}))
        results.append(check("H every non-alphanumeric in the cwd becomes '-' (C:\\Users\\x\\.claude)",
                             "secret" in p.stdout.lower(), p.stdout + p.stderr))

        shapes = {
            "env-style password": "REDIS_PASSWORD=s3cr3tValue99",
            "telegram bot token": "bot 123456789:AAH" + "x" * 32,
            "github fine-grained pat": "github_pat_" + "A1" * 20,
            "connection string": "postgres://app:Sup3rS3cret@db.local:5432/x",
            "wireguard key": "PrivateKey = " + "Q" * 43 + "=",
            "openai project key": "sk-proj-" + "a_b-" * 10,
        }
        for label, line in shapes.items():
            d = mkdir(tmp, {**BASE, "a.md": fact("a", body=line)})
            p = run(str(d))
            results.append(check(f"B {label} -> caught", p.returncode == 1 and "a.md" in p.stdout, p.stdout))

        for label, text in {"quoted type": "---\nname: a\ndescription: d\nmetadata:\n  type: 'feedback'\n---\n\nx\n",
                            "BOM": chr(0xFEFF) + fact("a"),
                            "nested name does not shadow": "---\nname: a\ndescription: d\nmetadata:\n  type: user\n"
                                                           "  extra:\n    name: zzz\n---\n\nx\n"}.items():
            files = {**BASE, "a.md": text, "b.md": fact("zzz"), "MEMORY.md": BASE["MEMORY.md"] + "- [B](b.md) — b\n"}
            d = mkdir(tmp, files)
            p = run(str(d))
            results.append(check(f"D frontmatter: {label} -> ok", p.returncode == 0, p.stdout))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_memory_doctor():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
