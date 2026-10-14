#!/usr/bin/env python3
"""Regression guard: consilium-summary.md must say what the role finals say.

A field incident (2026-06-24): the summary the human judged was not written by
consilium-synth.py; it said PROCEED over role finals that said rework_required, and the
human gate decided on it. synth itself cannot do that (rework_required dominates), so the
gap was a summary nobody compared with the finals, and finals nobody dated against the
tree they reviewed.

  A. HAND-WRITTEN SUMMARY FAILS   no synth aggregate line -> fail.
  B. DISAGREEING SUMMARY FAILS    synth-shaped line says satisfied, finals say rework.
  C. REAL SYNTH OUTPUT PASSES     consilium-synth.py writes the summary -> pass.
  D. STALE FINALS FAIL            a code commit after the finals -> fail; finals after
                                  the last code commit -> pass; engagement-only commits
                                  after the finals do not count.
  E. NO SUMMARY YET               -> skip.
  F. WIRED                        handoff-precheck.py runs it on M and L.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck.consilium_fidelity import check_consilium_fidelity

ROLES_M = ("peer-opus",)


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def final(verdict, findings=()):
    return {"verdict": verdict, "summary": "s", "findings": list(findings)}


def mkeng(root: Path, finals: dict, stamp="20261009T120000Z", size="M") -> Path:
    eng = Path(tempfile.mkdtemp(dir=root)) / "engagement"
    (eng / "validation-outputs").mkdir(parents=True)
    (eng / "iteration").write_text("1", encoding="utf-8")
    (eng / "criteria.md").write_text(f"---\nsize: {size}\n---\n", encoding="utf-8")
    for role, data in finals.items():
        (eng / "validation-outputs" / f"{role}-iter-1-{stamp}.json").write_text(json.dumps(data), encoding="utf-8")
    return eng


def synth(eng: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "consilium-synth.py"), str(eng), "--tier", "M"],
                          capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                          timeout=60, check=False)


def git(cwd: Path, *args, when: str | None = None):
    env = dict(os.environ)
    if when:
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env, check=True)


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rework = {"peer-opus": final("rework_required", [{"severity": "high", "issue": "auth bypass"}])}

        eng = mkeng(tmp, rework)
        (eng / "consilium-summary.md").write_text("# Consilium summary\n\nAll reviewers fine. PROCEED.\n",
                                                  encoding="utf-8")
        r = check_consilium_fidelity(eng)
        results.append(check("A: hand-written summary (no synth aggregate line) -> fail", r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, rework)
        (eng / "consilium-summary.md").write_text(
            "# Consilium synthesis — iter 1\n\n**Aggregate verdict:** satisfied  \n**Rationale:** x\n", encoding="utf-8")
        r = check_consilium_fidelity(eng)
        results.append(check("B: summary says satisfied, finals say rework_required -> fail",
                             r["status"] == "fail" and "rework_required" in r["detail"], f"{r}"))

        for verdict in ("satisfied", "rework_required"):
            eng = mkeng(tmp, {"peer-opus": final(verdict)})
            p = synth(eng)
            r = check_consilium_fidelity(eng)
            results.append(check(f"C: real consilium-synth.py output ({verdict}) -> pass",
                                 p.returncode == 0 and r["status"] == "pass", f"synth rc={p.returncode} {p.stderr[-200:]} {r}"))

        repo = tmp / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        git(repo, "add", "app.py")
        git(repo, "commit", "-qm", "code", when="2026-10-09T10:00:00Z")
        eng = repo / "engagement"
        (eng / "validation-outputs").mkdir(parents=True)
        (eng / "iteration").write_text("1", encoding="utf-8")
        (eng / "criteria.md").write_text("---\nsize: M\n---\n", encoding="utf-8")
        (eng / "validation-outputs" / "peer-opus-iter-1-20261009T120000Z.json").write_text(
            json.dumps(final("satisfied")), encoding="utf-8")
        synth(eng)
        r = check_consilium_fidelity(eng)
        results.append(check("D: finals newer than the last code commit -> pass", r["status"] == "pass", f"{r}"))
        git(repo, "add", "engagement")
        git(repo, "commit", "-qm", "handoff", when="2026-10-09T13:00:00Z")
        r = check_consilium_fidelity(eng)
        results.append(check("D: an engagement-only commit after the finals does not count -> pass",
                             r["status"] == "pass", f"{r}"))
        (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
        git(repo, "commit", "-qam", "late code change", when="2026-10-09T14:00:00Z")
        r = check_consilium_fidelity(eng)
        results.append(check("D: a code commit after the finals -> fail", r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, rework)
        r = check_consilium_fidelity(eng)
        results.append(check("E: no consilium-summary.md yet -> skip", r["status"] == "skip", f"{r}"))

        print("\nG. Codex review of 5c92a79")
        eng = mkeng(tmp, {"peer-opus": final("satisfied")}, size="M")
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "consilium-synth.py"), str(eng), "--tier", "L"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, check=False)
        r = check_consilium_fidelity(eng)
        results.append(check("G1: size M engagement reviewed with --tier L (roles missing) -> pass",
                             r["status"] == "pass", f"{r}"))

        repo2 = tmp / "repo2"
        repo2.mkdir()
        git(repo2, "init", "-q")
        git(repo2, "config", "user.email", "t@t")
        git(repo2, "config", "user.name", "t")
        (repo2 / "app.py").write_text("x = 1\n", encoding="utf-8")
        git(repo2, "add", "app.py")
        git(repo2, "commit", "-qm", "code", when="2026-10-09T13:00:00Z")
        eng = repo2 / "engagement"
        (eng / "validation-outputs").mkdir(parents=True)
        (eng / "iteration").write_text("1", encoding="utf-8")
        (eng / "criteria.md").write_text("---\nsize: M\n---\n", encoding="utf-8")
        (eng / "validation-outputs" / "peer-opus-iter-1-20261009T100000Z.json").write_text(
            json.dumps(final("satisfied")), encoding="utf-8")
        synth(eng)
        (eng / "validation-outputs" / "peer-opus-iter-1-20261009T150000Z.json").write_text("{truncated", encoding="utf-8")
        r = check_consilium_fidelity(eng)
        results.append(check("G2: a newer unparseable final does not date a stale review as fresh -> fail",
                             r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, {"peer-opus": final("satisfied")})
        synth(eng)
        (eng / "iteration").write_text("2", encoding="utf-8")
        (eng / "validation-outputs" / "peer-opus-iter-2-20261009T130000Z.json").write_text(
            json.dumps(final("rework_required", [{"severity": "high", "issue": "x"}])), encoding="utf-8")
        r = check_consilium_fidelity(eng)
        results.append(check("G3: an iter-1 summary while iter-2 finals exist -> fail", r["status"] == "fail", f"{r}"))
        (eng / "validation-outputs" / "peer-opus-iter-2-20261009T130000Z.json").unlink()
        r = check_consilium_fidelity(eng)
        results.append(check("G3: an iter-1 summary before the iter-2 consilium has run -> skip",
                             r["status"] == "skip", f"{r}"))

        eng = mkeng(tmp, rework)
        (eng / "consilium-summary.md").write_text("# hand-written\nPROCEED\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPTS_DIR / "handoff-precheck.py"), str(eng), "--json"],
                           capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                           timeout=120, check=False)
        try:
            names = {c["name"]: c["status"] for c in json.loads(p.stdout).get("checks", [])}
        except ValueError:
            names = {}
        results.append(check("F: handoff-precheck runs consilium-fidelity on M and it fails here",
                             names.get("consilium-fidelity") == "fail", f"{names.get('consilium-fidelity')!r}"))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_consilium_fidelity():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
