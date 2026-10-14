#!/usr/bin/env python3
"""Report and safely clean up git worktrees: never touches unmerged, uncommitted or ignored work.

The engagement engine's failure path runs `git worktree remove --force` and `git branch -D`
on wave worktrees, which deletes a specialist's uncommitted or unmerged work before a resume
can use it. This is the safe alternative:

  python ~/.claude/scripts/worktree-gc.py <repo> [--base BRANCH] [--json] [--apply]

<repo> may be the main worktree or any linked one; the base defaults to the MAIN worktree's
branch. States (the main worktree is never listed):
  missing            the directory is gone; `git worktree prune` drops the record
  dirty              uncommitted changes; kept
  ignored-files      clean, but holds gitignored files (.env, local db, notes) that `worktree
                     remove` would delete with the directory; kept
  merged-clean       branch already contained in base, nothing uncommitted or ignored; removable
  unmerged           commits not in base, merges cleanly (predicted); kept
  unmerged-conflict  commits not in base, `git merge-tree` predicts a conflict; kept
  detached           no branch; kept
  error              a git call failed (detail says which); kept

Branches are compared as refs/heads/<name>, so a tag with the same name cannot stand in for
the branch. Default is a dry run that prints the plan. --apply runs only `git worktree remove`
(no --force), `git branch -d` (refuses unmerged) and `git worktree prune`. Exit 2 on usage
errors (not a repository, unknown --base, detached main worktree without --base), else 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo, *args, check=False):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def worktrees(repo):
    """All entries of `git worktree list --porcelain`; the first one is the main worktree."""
    out = git(repo, "worktree", "list", "--porcelain", check=True).stdout
    items, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                items.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val or True
    return items


def short_branch(entry):
    ref = entry.get("branch", "")
    return ref[len("refs/heads/"):] if isinstance(ref, str) and ref.startswith("refs/heads/") else ""


def classify(repo, wt, base_ref):
    path = Path(wt["worktree"])
    branch = short_branch(wt)
    info = {"path": str(path), "branch": branch, "ahead": 0, "detail": ""}
    if wt.get("prunable") or not path.exists():
        return {**info, "state": "missing"}
    st = git(path, "status", "--porcelain", "--ignored")
    if st.returncode != 0:
        return {**info, "state": "error", "detail": f"git status failed: {st.stderr.strip()[:160]}"}
    lines = [ln for ln in st.stdout.splitlines() if ln.strip()]
    if any(not ln.startswith("!!") for ln in lines):
        return {**info, "state": "dirty"}
    ignored = [ln[3:] for ln in lines if ln.startswith("!!")]
    if not branch:
        return {**info, "state": "detached"}
    ref = f"refs/heads/{branch}"
    mb = git(repo, "merge-base", "--is-ancestor", ref, base_ref)
    if mb.returncode not in (0, 1):
        return {**info, "state": "error", "detail": f"merge-base failed: {mb.stderr.strip()[:160]}"}
    if mb.returncode == 0:
        if ignored:
            return {**info, "state": "ignored-files", "detail": f"{len(ignored)} ignored: {', '.join(ignored[:5])}"}
        return {**info, "state": "merged-clean"}
    ahead = git(repo, "rev-list", "--count", f"{base_ref}..{ref}").stdout.strip()
    info["ahead"] = int(ahead) if ahead.isdigit() else 0
    mt = git(repo, "merge-tree", "--write-tree", base_ref, ref)
    if mt.returncode == 1:
        return {**info, "state": "unmerged-conflict"}
    if mt.returncode != 0:
        return {**info, "state": "error", "detail": f"merge-tree failed (rc {mt.returncode}): {mt.stderr.strip()[:160]}"}
    return {**info, "state": "unmerged"}


def plan(entries):
    steps = []
    for e in entries:
        if e["state"] == "merged-clean":
            steps.append(["worktree", "remove", e["path"]])
            steps.append(["branch", "-d", e["branch"]])
    if any(e["state"] == "missing" for e in entries):
        steps.append(["worktree", "prune"])
    return steps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo")
    ap.add_argument("--base", help="branch the work is merged into (default: the main worktree's branch)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="run the plan (default: dry run)")
    args = ap.parse_args()
    repo = Path(args.repo)
    if git(repo, "rev-parse", "--git-dir").returncode != 0:
        print(f"not a git repository: {repo}", file=sys.stderr)
        return 2
    entries_raw = worktrees(repo)
    main_wt, linked = entries_raw[0], entries_raw[1:]
    base = args.base or short_branch(main_wt)
    if not base:
        print("the main worktree is detached; pass --base BRANCH", file=sys.stderr)
        return 2
    heads = f"refs/heads/{base}"
    base_ref = heads if git(repo, "rev-parse", "--verify", "--quiet", heads).returncode == 0 else base
    if git(repo, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}").returncode != 0:
        print(f"unknown --base: {base}", file=sys.stderr)
        return 2
    main_path = Path(main_wt["worktree"])
    entries = [classify(main_path, wt, base_ref) for wt in linked]
    steps = plan(entries)
    done = []
    if args.apply:
        for step in steps:
            r = git(main_path, *step)
            done.append({"cmd": "git " + " ".join(step), "rc": r.returncode, "err": r.stderr.strip()[:200]})
    if args.json:
        print(json.dumps({"base": base, "worktrees": entries, "plan": ["git " + " ".join(s) for s in steps],
                          "applied": done}, ensure_ascii=False, indent=2))
        return 0
    for e in entries:
        extra = f" (+{e['ahead']} commits)" if e["ahead"] else ""
        detail = f"  [{e['detail']}]" if e["detail"] else ""
        print(f"{e['state']:<18} {e['branch'] or '-':<28} {e['path']}{extra}{detail}")
    print(f"\nbase: {base}")
    if not steps:
        print("nothing to clean up")
    for s in (done or [{"cmd": "git " + " ".join(s), "rc": None} for s in steps]):
        status = "" if s["rc"] is None else (" ok" if s["rc"] == 0 else f" FAILED rc={s['rc']}: {s.get('err', '')}")
        print(("applied: " if args.apply else "would run: ") + s["cmd"] + status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
