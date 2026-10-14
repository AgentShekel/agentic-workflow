#!/usr/bin/env python3
"""Regression guard: executor-reports survive a rework iteration.

The engine tells every specialist to write/refresh executor-reports/{task}.md on every
run, iteration 2+ included, so the iter-1 text was overwritten in place. The precheck caught it and
was right to; nothing in Zone-1 ran between iterations to keep a copy.

Fix: human-directive.py snapshots executor-reports/*.md to executor-reports/iter-{N}/
when the human sends iteration N back (REJECT or DIRECTED), never overwriting an existing
snapshot; check_executor_iteration_structure accepts the snapshots as the audit trail.

  A. OVERWRITE STILL FAILS   iter 2, reports without headings, no snapshot -> fail.
  B. SNAPSHOT PASSES         same plus a non-empty iter-1/ snapshot -> pass.
  C. EMPTY SNAPSHOT FAILS    an iter-1/ snapshot holding an empty file -> fail.
  D. LIVE REJECT SNAPSHOTS   human-directive.py --decision REJECT (subprocess) creates
                             iter-N/ with the reports; a second run never overwrites it.
  E. PROCEED DOES NOT        --decision PROCEED leaves no snapshot.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck.iteration import check_executor_iteration_structure


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def mkeng(root: Path, iteration: int, reports: dict, snapshots: dict | None = None) -> Path:
    eng = Path(tempfile.mkdtemp(dir=root)) / "engagement"
    (eng / "executor-reports").mkdir(parents=True)
    (eng / "iteration").write_text(str(iteration), encoding="utf-8")
    for name, text in reports.items():
        (eng / "executor-reports" / name).write_text(text, encoding="utf-8")
    for k, files in (snapshots or {}).items():
        d = eng / "executor-reports" / f"iter-{k}"
        d.mkdir()
        for name, text in files.items():
            (d / name).write_text(text, encoding="utf-8")
    return eng


def directive(eng: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "human-directive.py"), str(eng), *args],
                          capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                          timeout=60, check=False)


ITER2 = "## Criteria acknowledgement\n- crit-1 ok\n\n## Work\niter-2 text only\n"


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        eng = mkeng(tmp, 2, {"T01.md": ITER2, "T02.md": ITER2})
        r = check_executor_iteration_structure(eng)
        results.append(check("A: overwritten iter-2 reports, no snapshot -> fail", r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, 2, {"T01.md": ITER2, "T02.md": ITER2},
                    {1: {"T01.md": "iter-1 work T01\n", "T02.md": "iter-1 work T02\n"}})
        r = check_executor_iteration_structure(eng)
        results.append(check("B: iter-1/ snapshot is the audit trail -> pass", r["status"] == "pass", f"{r}"))

        eng = mkeng(tmp, 2, {"T01.md": ITER2}, {1: {"T01.md": ""}})
        r = check_executor_iteration_structure(eng)
        results.append(check("C: empty snapshot file -> fail", r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, 3, {"T01.md": ITER2}, {1: {"T01.md": "iter-1\n"}})
        r = check_executor_iteration_structure(eng)
        results.append(check("C2: iter 3 needs iter-1/ AND iter-2/ -> fail", r["status"] == "fail", f"{r}"))

        eng = mkeng(tmp, 1, {"T01.md": "iter-1 original\n", "T02.md": "iter-1 T02\n"})
        p = directive(eng, "--decision", "REJECT", "--reasons", "rework T01")
        snap = eng / "executor-reports" / "iter-1"
        results.append(check("D: REJECT exits 0", p.returncode == 0, p.stderr[-300:]))
        results.append(check("D: REJECT snapshots the reports to iter-1/",
                             (snap / "T01.md").exists() and (snap / "T01.md").read_text(encoding="utf-8") == "iter-1 original\n"
                             and (snap / "T02.md").exists(), f"{sorted(x.name for x in snap.glob('*'))if snap.exists() else 'no dir'}"))
        (eng / "executor-reports" / "T01.md").write_text("changed later\n", encoding="utf-8")
        p = directive(eng, "--decision", "REJECT", "--reasons", "again", "--overwrite")
        results.append(check("D: a second REJECT never overwrites the snapshot",
                             (snap / "T01.md").read_text(encoding="utf-8") == "iter-1 original\n",
                             (snap / "T01.md").read_text(encoding="utf-8") if (snap / "T01.md").exists() else "missing"))
        results.append(check("D: snapshot dir not read as current reports (no iter-1/ files at top level)",
                             sorted(x.name for x in (eng / "executor-reports").glob("*.md")) == ["T01.md", "T02.md"]))

        import importlib.util
        spec = importlib.util.spec_from_file_location("_hd", SCRIPTS_DIR / "human-directive.py")
        hd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hd)
        eng = mkeng(tmp, 1, {"A.md": "iter-1 A\n", "B.md": "iter-1 B\n"})
        real_copy, n = hd.shutil.copy2, []

        def dying_copy(src, dst):
            if n:
                raise OSError("interrupted")
            n.append(1)
            return real_copy(src, dst)

        hd.shutil.copy2 = dying_copy
        try:
            hd.snapshot_executor_reports(eng, 1)
        except OSError:
            pass
        finally:
            hd.shutil.copy2 = real_copy
        snap = eng / "executor-reports" / "iter-1"
        results.append(check("D2: a copy interrupted after one file leaves no iter-1/ behind",
                             not snap.exists(), f"{sorted(x.name for x in snap.glob('*')) if snap.exists() else ''}"))
        hd.snapshot_executor_reports(eng, 1)
        results.append(check("D2: the retry writes the full snapshot",
                             snap.exists() and sorted(x.name for x in snap.glob("*.md")) == ["A.md", "B.md"],
                             f"{sorted(x.name for x in snap.glob('*')) if snap.exists() else 'no dir'}"))
        results.append(check("D2: no temp dir left among the reports",
                             sorted(x.name for x in (eng / "executor-reports").iterdir()) == ["A.md", "B.md", "iter-1"],
                             f"{sorted(x.name for x in (eng / 'executor-reports').iterdir())}"))

        eng = mkeng(tmp, 1, {"T01.md": "x\n"})
        p = directive(eng, "--decision", "PROCEED")
        results.append(check("E: PROCEED leaves no snapshot", p.returncode == 0 and not (eng / "executor-reports" / "iter-1").exists(),
                             p.stderr[-300:]))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_executor_snapshot():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
