#!/usr/bin/env python3
"""Regression guard: worktree cleanup never destroys unmerged or uncommitted work.

Cleanup must never touch dirty or unmerged trees. Our engine's failure path runs `git worktree remove --force` and
`git branch -D` on wave worktrees, which can delete a specialist's uncommitted or unmerged
work before a resume. scripts/worktree-gc.py is the Zone-1 alternative: report by default,
--apply removes only merged + clean trees (no --force, `branch -d`), prunes vanished ones.

  A. CLASSIFY   merged-clean / merged-dirty / unmerged / unmerged-conflict / missing
  B. DRY RUN    the default changes nothing
  C. APPLY      removes merged-clean only, prunes missing, keeps every other tree and branch
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "worktree-gc.py"


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def gc(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), str(repo), *args], capture_output=True, text=True,
                          timeout=120, check=False)


def main() -> int:
    results = []
    if not SCRIPT.exists():
        print(f"  [FAIL] {SCRIPT.name} missing")
        return 1
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = tmp / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "a.txt").write_text("base\n", encoding="utf-8")
        (repo / ".gitignore").write_text("*.local\n", encoding="utf-8")
        git(repo, "add", "a.txt", ".gitignore")
        git(repo, "commit", "-qm", "base")
        git(repo, "tag", "wf_tagged")  # a tag that shares a name with a branch below

        def tree(name):
            path = tmp / name
            git(repo, "worktree", "add", "-q", "-b", f"wf_{name}", str(path))
            return path

        merged = tree("merged")
        (merged / "m.txt").write_text("m\n", encoding="utf-8")
        git(merged, "add", "m.txt")
        git(merged, "commit", "-qm", "m")
        git(repo, "merge", "-q", "--no-edit", "wf_merged")

        dirty = tree("dirty")  # merged (no new commits) but holds uncommitted work
        (dirty / "wip.txt").write_text("uncommitted\n", encoding="utf-8")

        unmerged = tree("unmerged")
        (unmerged / "u.txt").write_text("u\n", encoding="utf-8")
        git(unmerged, "add", "u.txt")
        git(unmerged, "commit", "-qm", "u")

        conflict = tree("conflict")
        (conflict / "a.txt").write_text("theirs\n", encoding="utf-8")
        git(conflict, "commit", "-qam", "c")
        (repo / "a.txt").write_text("ours\n", encoding="utf-8")
        git(repo, "commit", "-qam", "ours")

        gone = tree("gone")
        shutil.rmtree(gone)

        # review round 1 (2026-10-10)
        ignored = tree("ignored")  # merged, nothing tracked changed, but holds a gitignored local file
        (ignored / "db.local").write_text("local state\n", encoding="utf-8")
        tagged = tree("tagged")  # branch wf_tagged has unmerged work; tag wf_tagged points at old base
        (tagged / "t.txt").write_text("t\n", encoding="utf-8")
        git(tagged, "add", "t.txt")
        git(tagged, "commit", "-qm", "t")

        p = gc(repo, "--json")
        try:
            states = {Path(w["path"]).name: w["state"] for w in json.loads(p.stdout)["worktrees"]}
        except (ValueError, KeyError):
            states = {}
        want = {"merged": "merged-clean", "dirty": "dirty", "unmerged": "unmerged",
                "conflict": "unmerged-conflict", "gone": "missing", "ignored": "ignored-files",
                "tagged": "unmerged"}
        for name, state in want.items():
            results.append(check(f"A {name} -> {state}", states.get(name) == state, f"{states} {p.stderr[-200:]}"))

        p = gc(unmerged, "--json")  # pointed at a linked worktree, not the main one
        try:
            data = json.loads(p.stdout)
            st = {Path(w["path"]).name: w["state"] for w in data["worktrees"]}
        except (ValueError, KeyError):
            data, st = {}, {}
        results.append(check("A base comes from the main worktree even when given a linked one",
                             data.get("base") == "main" and st.get("unmerged") == "unmerged", f"{data.get('base')} {st}"))
        p = gc(repo, "--base", "no-such-branch")
        results.append(check("A an unknown --base is an error (exit 2), not a silent plan", p.returncode == 2,
                             f"rc={p.returncode} {p.stdout[-200:]}"))

        before = git(repo, "worktree", "list")
        gc(repo)
        results.append(check("B dry run changes nothing", git(repo, "worktree", "list") == before))

        p = gc(repo, "--apply")
        listing = git(repo, "worktree", "list")
        branches = git(repo, "branch", "--list", "wf_*")
        results.append(check("C merged-clean tree removed", f"/{merged.name} " not in listing and not merged.exists(), listing))
        results.append(check("C its merged branch deleted with -d", "wf_merged" not in branches, branches))
        results.append(check("C missing tree pruned", "gone" not in listing, listing))
        results.append(check("C dirty tree and its file kept", dirty.exists() and (dirty / "wip.txt").exists()))
        results.append(check("C unmerged and conflicting trees kept",
                             unmerged.exists() and conflict.exists() and "wf_unmerged" in branches
                             and "wf_conflict" in branches, branches))
        results.append(check("C a tree holding gitignored files is kept with them",
                             (ignored / "db.local").exists()))
        results.append(check("C a branch shadowed by a same-name tag keeps its tree",
                             tagged.exists() and "wf_tagged" in branches, branches))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_worktree_gc():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
