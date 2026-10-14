#!/usr/bin/env python3
"""Regression guard — the cycle threshold in skillopt-ready.py counts ENGAGEMENTS, not entries.

system-optimization-protocol and agents/dev-director.md both fire a cycle when ">=3 engagements
in this domain show the same failure class". The checker fired on `len(signals) >= 3`. One
engagement that logs one signal per iteration (L-tier allows three) reached the threshold alone:
the 2026-10-09 "CYCLE due - dev/rule_missing: 3" was three signals from one engagement. Channel B
had the same unit: two reflections from one engagement counted as two.

Pinned here (live subprocess, --json):

  A. ONE ENGAGEMENT           3 Channel-A signals from one engagement (date suffix and case
                              variants included) do not make a cycle due.
  B. THREE ENGAGEMENTS        3 signals from 3 engagements do, and the due entry reports both
                              numbers: `engagements` and the signal `count`.
  C. NO ENGAGEMENT            system-session signals (`engagement: none`) count one each, so 3 of
                              them still fire: they have no engagement to collapse into.
  D. SIGNALS != ENGAGEMENTS   4 signals across 2 engagements stay below the threshold.
  E. CHANNEL B, SAME RULE     3 reflections of one engagement do not fire; 3 engagements do.

Run standalone or under pytest:
  python test_cluster_threshold_regress.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def sig(eng: str, cls: str) -> str:
    return (f"### SIGNAL | domain: dev | 2026-10-06 | engagement: {eng}\n"
            f"Failure class: {cls} (rule_missing)\n"
            f"Traced to: skills/validation-pipeline\n\n")


LOG = "# Skill evolution log\n\n" + "".join([
    sig("solo", "solo-gap"), sig("solo-2026-10-01", "solo-gap"), sig("SOLO", "solo-gap"),
    sig("e1", "spread-gap"), sig("e2", "spread-gap"), sig("e3", "spread-gap"),
    sig("none", "anon-gap"), sig("none", "anon-gap"), sig("none", "anon-gap"),
    sig("m1", "mixed-gap"), sig("m1", "mixed-gap"), sig("m1", "mixed-gap"), sig("m2", "mixed-gap"),
])


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def write_refl(root: Path, eng: str, target: str, cls: str, iterations: int) -> None:
    d = root / eng / "engagement"
    d.mkdir(parents=True)
    (d / "criteria.md").write_text("---\ndomain: dev\nsize: L\n---\n", encoding="utf-8")
    blocks = [f"## Reflection — {eng} — 2026-10-0{i + 1} — verdict: REJECT\n\n"
              f"- target: skill: {target}\n  class: {cls}\n  observation: x\n  evidence: y\n"
              for i in range(iterations)]
    (d / "engagement-reflections.md").write_text("\n".join(blocks), encoding="utf-8")


def run(root: Path) -> dict | None:
    log = root / "skill-evolution-log.md"
    log.write_text(LOG, encoding="utf-8")
    write_refl(root, "loner", "code-reviewing", "rule_wrong", 3)       # E: one engagement x3
    for eng in ("r1", "r2", "r3"):                                      # E: three engagements
        write_refl(root, eng, "testing-methodology", "rule_wrong", 1)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "skillopt-ready.py"), "--json", "--log", str(log),
         "--reflection-root", str(root), "--reflection-window-days", "0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    try:
        return json.loads(proc.stdout)
    except Exception:  # noqa: BLE001
        print(f"  no JSON: stdout={proc.stdout[:300]!r} stderr={proc.stderr[:300]!r}")
        return None


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        out = run(Path(td))
    results.append(check("checker emitted JSON", out is not None))
    out = out or {}
    due = {d["class"]: d for d in out.get("due") or []}
    rdue = {(d["target"], d["class"]): d for d in out.get("reflection_due") or []}

    print("A. one engagement does not make a cycle")
    results.append(check("solo-gap (3 signals, 1 engagement) is not due", "solo-gap" not in due,
                         f"due={sorted(due)}"))
    print("B. three engagements do, and both numbers are reported")
    sp = due.get("spread-gap") or {}
    results.append(check("spread-gap is due", bool(sp), f"due={sorted(due)}"))
    results.append(check("due entry: engagements == 3 and count == 3",
                         sp.get("engagements") == 3 and sp.get("count") == 3, f"entry={sp}"))
    print("C. engagement-less signals count one each")
    results.append(check("anon-gap (3 x engagement: none) is due", "anon-gap" in due,
                         f"due={sorted(due)}"))
    print("D. four signals across two engagements stay below 3")
    results.append(check("mixed-gap is not due", "mixed-gap" not in due, f"due={sorted(due)}"))
    print("E. Channel B uses the same unit")
    results.append(check("one engagement x3 reflections is not due",
                         ("code-reviewing", "rule_wrong") not in rdue, f"reflection_due={sorted(rdue)}"))
    rr = rdue.get(("testing-methodology", "rule_wrong")) or {}
    results.append(check("three engagements x1 reflection are due, engagements == 3",
                         rr.get("engagements") == 3 and rr.get("count") == 3, f"entry={rr}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_cluster_threshold_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
