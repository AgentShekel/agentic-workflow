#!/usr/bin/env python3
"""Regression guard — adjudicated harness signals and the self-clearing suppression.

2026-08-31: a harness-evolution cycle ran against the `engagement-workflow.js /
rule_missing` cluster and Codex judged all three signals unfixable under the Zone-2
freeze. The cycle wrote nothing, so `harness-ready.py` kept reporting the same
cluster DUE. A trigger that fires on a cluster the loop structurally cannot close
is a trigger that gets ignored, and then the real ones get ignored with it.

`adjudicated:` is the disposition that was missing. It is deliberately NOT the same
as the two that already existed:

  resolved:  fixed.
  platform:  the constraint lives outside our layer.
  adjudicated: a cycle looked, on a stated date, and judged it unactionable HERE
               for a stated reason. The want still stands.

The suppression has to be self-clearing, and clearing in one specific direction:
one NEW signal joining an adjudicated cluster must re-fire it immediately, without
waiting for a second. A class judged speculative that then actually happens in the
field has earned a fresh look on the first real hit. Case D is that property and is
the reason this file exists.

  A. UNMARKED STILL FIRES   the pre-existing behaviour must not move.
  B. ALL ADJUDICATED QUIET  the cluster stops firing.
  C. STILL VISIBLE          it is suppressed, never hidden: the count and the
                            adjudicated tally stay in the report.
  D. ONE FRESH SIGNAL       re-fires the cluster on the FIRST new hit, not the second.
  E. DISPOSITIONS DIFFER    adjudicated is not resolved: a resolved signal leaves the
                            live set entirely, an adjudicated one stays and counts.
  F. LIVE SUBPROCESS        the real script, real exit codes: 1 when due, 0 when not.

Run standalone or under pytest:
  python test_harness_adjudicated_regress.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_harness_ready", SCRIPTS_DIR / "harness-ready.py")
hr = importlib.util.module_from_spec(_spec)
sys.modules["_harness_ready"] = hr
_spec.loader.exec_module(hr)

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def sig(n: int, *, extra: str = "") -> str:
    return (f"### SIGNAL | domain: harness | 2026-08-31 | engagement: e{n}\n"
            f"Failure class: rule_missing (thing {n})\n"
            f"Traced to: workflows/engagement-workflow.js (spot {n}).\n"
            f"Evidence: none.\n{extra}")


ADJ = "adjudicated: 2026-08-31 | cycle X | no-patch, frozen zone.\n"
RES = "resolved: 2026-08-31 — fixed.\n"


def due_of(text: str):
    _, buckets, due = hr.analyze(hr.parse_signals(text))
    return buckets, due


def main() -> int:
    # --- A. unmarked still fires ------------------------------------------
    _, due = due_of(sig(1) + "\n" + sig(2))
    check(len(due) == 1 and due[0][2] == 2,
          f"A: two unmarked signals must still be DUE, got {due}")

    # --- B. all adjudicated goes quiet ------------------------------------
    text_all_adj = sig(1, extra=ADJ) + "\n" + sig(2, extra=ADJ) + "\n" + sig(3, extra=ADJ)
    buckets, due = due_of(text_all_adj)
    check(due == [], f"B: a fully adjudicated cluster must not fire, got {due}")

    # --- C. suppressed, not hidden ----------------------------------------
    key = ("workflows/engagement-workflow.js", "rule_missing")
    check(key in buckets and len(buckets[key]) == 3,
          "C: the bucket must remain visible with all 3 signals still counted")
    check(sum(1 for s in buckets[key] if s["adjudicated"]) == 3,
          "C: all three must be reported as adjudicated")

    # --- D. one fresh signal re-fires -------------------------------------
    _, due = due_of(text_all_adj + "\n" + sig(4))
    check(len(due) == 1 and due[0][2] == 4,
          f"D: ONE new signal joining an adjudicated cluster must re-fire it on the "
          f"first hit — field evidence reopens a speculative judgement. got {due}")

    # a single adjudicated signal below threshold stays quiet either way
    _, due = due_of(sig(1, extra=ADJ))
    check(due == [], "D: one signal is below threshold regardless of disposition")

    # --- E. adjudicated is not resolved -----------------------------------
    buckets_r, due_r = due_of(sig(1, extra=RES) + "\n" + sig(2, extra=RES) + "\n" + sig(3))
    live_r = sum(len(v) for v in buckets_r.values())
    check(live_r == 1,
          f"E: resolved signals must LEAVE the live set, got {live_r} live")
    buckets_a, _ = due_of(sig(1, extra=ADJ) + "\n" + sig(2, extra=ADJ) + "\n" + sig(3))
    live_a = sum(len(v) for v in buckets_a.values())
    check(live_a == 3,
          f"E: adjudicated signals must STAY in the live set and keep counting, got {live_a}")
    # ...and because they stay, that third unmarked one still makes the cluster due
    _, due_a = due_of(sig(1, extra=ADJ) + "\n" + sig(2, extra=ADJ) + "\n" + sig(3))
    check(len(due_a) == 1, "E: an unadjudicated signal in an otherwise adjudicated cluster fires")

    # --- F. live subprocess -----------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        quiet = Path(td) / "quiet.md"
        quiet.write_text("# log\n\n" + text_all_adj, encoding="utf-8")
        loud = Path(td) / "loud.md"
        loud.write_text("# log\n\n" + text_all_adj + "\n" + sig(4), encoding="utf-8")

        for path, want_rc, label in ((quiet, 0, "quiet"), (loud, 1, "loud")):
            r = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "harness-ready.py"), "--log", str(path), "--json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            check(r.returncode == want_rc,
                  f"F/{label}: expected exit {want_rc}, got {r.returncode}")
            try:
                data = json.loads(r.stdout)
                check(data["ready"] is bool(want_rc), f"F/{label}: ready flag disagrees with exit code")
                check("adjudicated" in data,
                      "F: --json must expose the adjudicated tally, or suppression is invisible "
                      "to anything consuming this programmatically")
            except json.JSONDecodeError:
                FAILURES.append(f"F/{label}: --json unparseable: {r.stdout[:160]}")

    if FAILURES:
        print(f"FAIL — {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS — adjudicated-signal regressions held")
    return 0


def test_harness_adjudicated_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
