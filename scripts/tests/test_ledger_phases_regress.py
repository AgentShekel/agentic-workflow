#!/usr/bin/env python3
"""Regression guard — ledger-emit-phases.py.

The events this script writes are what metrics.py and skillopt-ready.py later read as
fact. The dangerous failure is therefore not a crash but a plausible payload carrying a
field the workflow never returned: a fabricated ledger reads exactly like a real one and
is impossible to audit after the fact. Everything here pins the boundary between
"derived from the return object" and "made up".

  A. NOTHING IS INVENTED    a key absent from the return is absent from the payload; a
                            return with nothing usable emits NOTHING rather than a
                            placeholder.
  B. NULL IS NOT MISSING    a returned null is information and must survive; only an
                            absent key is absent.
  C. HARD STOP SHAPE        error + no waves emits ONE deliver event with
                            readyForAcceptance false, not the three-event happy path.
  D. HAPPY PATH SHAPE       waves / adversarial_verify+validation_files / gate map to
                            deliver / validate / gate, in that order.
  E. BEST EFFORT            unreadable file, non-JSON, JSON that is not an object, and a
                            missing engagement dir all exit 0 and write nothing. An
                            observability helper may never break the work it observes.
  F. LIVE SUBPROCESS        a real run against a real engagement appends real lines to
                            events.jsonl, and those lines parse.

Run standalone or under pytest:
  python test_ledger_phases_regress.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "_ledger_emit_phases", SCRIPTS_DIR / "ledger-emit-phases.py")
lep = importlib.util.module_from_spec(_spec)
sys.modules["_ledger_emit_phases"] = lep
_spec.loader.exec_module(lep)

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def phases(events: list[dict]) -> list[str]:
    return [e["phase"] for e in events]


def run_cli(*argv: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ledger-emit-phases.py"), *argv],
        input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120)


def mkeng(root: Path, name: str) -> Path:
    eng = root / name / "engagement"
    eng.mkdir(parents=True)
    (eng / "criteria.md").write_text(
        "---\nengagement: t\ndomain: dev\nsize: M\nux_heavy: false\ntools_required: []\n---\n",
        encoding="utf-8")
    return eng


def main() -> int:
    # --- A. nothing is invented ------------------------------------------
    check(lep.build_events({}) == [], "A: an empty return must emit nothing")
    check(lep.build_events({"unrelated": 1}) == [],
          "A: a return with no known keys must emit nothing")
    check(lep.build_events("not a dict") == [], "A: a non-dict return must emit nothing")

    ev = lep.build_events({"waves": [{"merge_ok": True}]})
    check(phases(ev) == ["deliver"], f"A: waves alone must emit deliver only, got {phases(ev)}")
    check(ev[0]["payload"] == {"waveSummaries": [{"merge_ok": True}]},
          "A: deliver payload must be exactly the returned waves")

    ev = lep.build_events({"waves": [], "adversarial_verify": {"ran": True}})
    check(phases(ev) == ["deliver", "validate"],
          f"A: absent validation_files must not appear, got {phases(ev)}")
    check("validation_files" not in ev[1]["payload"],
          "A: a key the workflow did not return must not be in the payload")

    ev = lep.build_events({"waves": [], "readyForAcceptance": True})
    check(phases(ev) == ["deliver", "gate"], "A: readyForAcceptance alone still makes a gate event")
    check("failures" not in ev[-1]["payload"],
          "A: gate.failures must be omitted when the return has no gate")

    # --- B. null is not missing -------------------------------------------
    ev = lep.build_events({"waves": None})
    check(phases(ev) == ["deliver"] and ev[0]["payload"] == {"waveSummaries": None},
          "B: an explicitly returned null must survive as null")

    ev = lep.build_events({"waves": [], "gate": {"failures": []}, "readyForAcceptance": False})
    check(ev[-1]["payload"] == {"failures": [], "readyForAcceptance": False},
          "B: empty list and False are values, not absence")

    # --- C. hard-stop shape ------------------------------------------------
    ev = lep.build_events({"error": "malformed plan", "gate": {"failures": ["x"]}})
    check(phases(ev) == ["deliver"], f"C: a hard stop must emit one deliver event, got {phases(ev)}")
    # .get() rather than [] on purpose: a mutation that breaks the shape must be
    # REPORTED alongside every other failure, not raise and hide the rest of the run.
    hard = ev[0]["payload"] if ev else {}
    check(hard.get("error") == "malformed plan", f"C: the error must be carried verbatim, got {hard!r}")
    check(hard.get("readyForAcceptance") is False,
          "C: a hard stop is readyForAcceptance false")
    check(hard.get("failures") == ["x"], "C: stub gate failures must be carried")

    # an error alongside real waves is NOT a hard stop — the cascade produced output
    ev = lep.build_events({"error": "late warning", "waves": [1], "readyForAcceptance": True})
    check(phases(ev) == ["deliver", "gate"],
          f"C: error WITH waves must take the normal path, got {phases(ev)}")

    # --- D. happy-path shape ----------------------------------------------
    ev = lep.build_events({
        "waves": [{"merge_ok": True}],
        "adversarial_verify": {"ran": True},
        "validation_files": ["a.json"],
        "gate": {"failures": []},
        "readyForAcceptance": True,
    })
    check(phases(ev) == ["deliver", "validate", "gate"],
          f"D: full return must map to three events in order, got {phases(ev)}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # --- E. best effort ------------------------------------------------
        eng = mkeng(root, "e")
        bad = root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        r = run_cli(str(eng), "--result", str(bad))
        check(r.returncode == 0, f"E: unparseable JSON must exit 0, got {r.returncode}")
        check(not (eng / "events.jsonl").exists(), "E: unparseable JSON must write nothing")

        arr = root / "arr.json"
        arr.write_text("[1,2]", encoding="utf-8")
        r = run_cli(str(eng), "--result", str(arr))
        check(r.returncode == 0 and not (eng / "events.jsonl").exists(),
              "E: a JSON array must exit 0 and write nothing")

        r = run_cli(str(eng), "--result", str(root / "nope.json"))
        check(r.returncode == 0, "E: a missing result file must exit 0")

        good = root / "good.json"
        good.write_text(json.dumps({"waves": [{"merge_ok": True}], "readyForAcceptance": True}),
                        encoding="utf-8")
        r = run_cli(str(root / "no-such-engagement"), "--result", str(good))
        check(r.returncode == 0, "E: a missing engagement dir must exit 0")

        # dry-run writes nothing but reports the mapping
        r = run_cli(str(eng), "--result", str(good), "--dry-run")
        check(r.returncode == 0 and not (eng / "events.jsonl").exists(),
              "E: --dry-run must write nothing")
        check(len([ln for ln in r.stdout.splitlines() if ln.strip()]) == 2,
              f"E: --dry-run must print the 2 mapped events, got {r.stdout!r}")

        # --- F. live subprocess --------------------------------------------
        eng = mkeng(root, "f")
        r = run_cli(str(eng), "--result", "-", stdin=json.dumps({
            "waves": [{"merge_ok": True}],
            "adversarial_verify": {"ran": True},
            "validation_files": ["v.json"],
            "gate": {"failures": []},
            "readyForAcceptance": True,
            "tier": "M",
        }))
        check(r.returncode == 0, f"F: live run must exit 0, got {r.returncode}: {r.stderr[:200]}")
        ledger = eng / "events.jsonl"
        check(ledger.exists(), "F: live run must create events.jsonl")
        if ledger.exists():
            lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
            try:
                parsed = [json.loads(ln) for ln in lines]
            except json.JSONDecodeError as e:
                FAILURES.append(f"F: events.jsonl line is not valid JSON: {e}")
                parsed = []
            nodes = [p.get("node") for p in parsed]
            for want in ("phase:deliver", "phase:validate", "phase:gate"):
                check(want in nodes, f"F: {want} missing from events.jsonl (saw {nodes})")

    if FAILURES:
        print(f"FAIL — {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS — ledger-emit-phases regressions held")
    return 0


def test_ledger_phases_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
