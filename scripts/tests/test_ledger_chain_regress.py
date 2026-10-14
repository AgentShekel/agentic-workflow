#!/usr/bin/env python3
"""Regression guard — ledger v2: hash chain, gate_decision, token aggregates.

Locks in the 2026-08-20 v2 additions and, more importantly, the two properties
that make them safe to land on ledgers that already exist in the field:

  A. LEGACY TOLERANCE   every real ledger today is a v1 prefix with no chain.
                        Verification must call that `legacy_only` / `ok`, never
                        `tamper` — otherwise the check cries wolf on day one and
                        gets ignored, which is how audit tooling dies.
  B. TAMPER != FORK     an edited/removed past line (tamper) and two processes
                        appending concurrently (fork) look similar and are not
                        the same event. Conflating them makes the report useless.

Plus the countability guarantee the acceptance seam was missing: a
`gate_decision` without a decision in {PROCEED,DIRECTED,REJECT} must fail loudly
at emit time rather than land as unparseable prose.

Run standalone (harness gate) or under pytest:
  python test_ledger_chain_regress.py
  python test_ledger_chain_regress.py --module /tmp/patched-ledger.py
  pytest test_ledger_chain_regress.py -q

--module points the suite at a throwaway copy of lib/ledger.py, which is how a
gate proves red before green.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODULE = SCRIPTS_DIR / "lib" / "ledger.py"
_MODULE_OVERRIDE: Path | None = None


def load_ledger():
    """Fresh module instance per test — the class-level lock must not leak."""
    path = _MODULE_OVERRIDE or DEFAULT_MODULE
    spec = importlib.util.spec_from_file_location("ledger_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ledger_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _engagement(tmp: Path) -> Path:
    eng = tmp / "engagement"
    eng.mkdir(parents=True, exist_ok=True)
    return eng


def _lines(eng: Path) -> list[dict]:
    p = eng / "events.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _rewrite(eng: Path, events: list[dict]) -> None:
    p = eng / "events.jsonl"
    p.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n"
                         for e in events), encoding="utf-8")


# --------------------------------------------------------------------- tests

def test_fresh_chain_verifies():
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-lead", tier="M")
        led.emit("phase_started", node="phase:plan", payload={"phase": "plan"})
        led.emit("phase_completed", node="phase:plan", payload={"phase": "plan"})

        rep = L.EventLedger.verify_chain(eng)
        assert rep["status"] == "ok", rep
        assert rep["chained"] == rep["events"], rep
        assert rep["legacy_prefix"] == 0, rep
        assert rep["problems"] == [], rep

        evs = _lines(eng)
        assert evs[0]["prev_hash"] is None, "first event starts the chain"
        for prev, cur in zip(evs, evs[1:]):
            assert cur["prev_hash"] == prev["event_hash"], "links must be contiguous"
    print("PASS test_fresh_chain_verifies")


def test_edited_past_event_is_tamper():
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-lead", tier="M")
        led.emit("specialist_completed", payload={"report": "reports/a.md"})
        led.emit("handoff_submitted", payload={"note": "done"})

        evs = _lines(eng)
        target = next(i for i, e in enumerate(evs)
                      if e["payload_type"] == "specialist_completed")
        evs[target]["payload"]["report"] = "reports/DIFFERENT.md"
        _rewrite(eng, evs)

        rep = L.EventLedger.verify_chain(eng)
        assert rep["status"] == "tamper", rep
        assert any(p["kind"] == "tamper" for p in rep["problems"]), rep
    print("PASS test_edited_past_event_is_tamper")


def test_removed_past_event_is_tamper():
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-lead", tier="L")
        led.emit("phase_started", payload={"phase": "deliver"})
        led.emit("wave_completed", payload={"wave": "W1"})
        led.emit("handoff_submitted", payload={})

        evs = _lines(eng)
        drop = next(i for i, e in enumerate(evs) if e["payload_type"] == "wave_completed")
        del evs[drop]
        _rewrite(eng, evs)

        rep = L.EventLedger.verify_chain(eng)
        assert rep["status"] == "tamper", rep
        assert any("not found earlier" in p["detail"] for p in rep["problems"]), rep
    print("PASS test_removed_past_event_is_tamper")


def test_concurrent_append_is_fork_not_tamper():
    """Two writers chaining off the same tail is benign and must not be tamper."""
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-lead", tier="M")
        led.emit("phase_started", payload={"phase": "deliver"})
        evs = _lines(eng)
        shared_tail = evs[-1]["prev_hash"]  # what the last event chained off

        twin = dict(evs[-1])
        twin["event_id"] = evs[-1]["event_id"] + "-twin"
        twin["prev_hash"] = shared_tail
        twin["event_hash"] = L.canonical_event_hash(twin)
        _rewrite(eng, evs + [twin])

        rep = L.EventLedger.verify_chain(eng)
        assert rep["status"] == "fork", rep
        assert all(p["kind"] == "fork" for p in rep["problems"]), rep
    print("PASS test_concurrent_append_is_fork_not_tamper")


def test_legacy_v1_prefix_is_not_a_break():
    """Every ledger in the field today is unchained v1. It must verify clean."""
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        legacy = [{
            "event_id": f"ledger-v1-2026060{i}T000000000000-abcdef01",
            "event_schema_version": "1",
            "engagement_id": "eng",
            "payload_type": "specialist_completed",
            "payload": {"report": f"r{i}.md"},
            "timestamp": f"2026-06-0{i}T00:00:00.000000Z",
        } for i in (1, 2)]
        _rewrite(eng, legacy)

        rep = L.EventLedger.verify_chain(eng)
        assert rep["status"] == "legacy_only", rep
        assert rep["legacy_prefix"] == 2 and rep["chained"] == 0, rep
        assert rep["problems"] == [], rep

        # A v2 event appended after a legacy prefix starts a fresh segment.
        led = L.EventLedger(eng, agent="dev-manager", tier="M")
        led.emit("verdict_written", verdict="ACCEPT", payload={})
        rep2 = L.EventLedger.verify_chain(eng)
        assert rep2["status"] == "ok", rep2
        assert rep2["legacy_prefix"] == 2 and rep2["chained"] >= 1, rep2
    print("PASS test_legacy_v1_prefix_is_not_a_break")


def test_gate_decision_must_be_countable():
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-manager", tier="L")

        for bad in ({}, {"decision": "proceed-ish"}, {"decision": None}):
            try:
                led.emit("gate_decision", payload=dict(bad))
            except AssertionError:
                pass
            else:
                raise AssertionError(f"uncountable gate_decision accepted: {bad!r}")

        led.emit("gate_decision", verdict="DIRECTED", payload={
            "decision": "DIRECTED", "gate": "human-directive",
            "signals_total": 4, "signals_overruled": 1,
        })
        evs = _lines(eng)
        assert evs[-1]["payload"]["decision"] == "DIRECTED"
        assert L.EventLedger.verify_chain(eng)["status"] == "ok"
    print("PASS test_gate_decision_must_be_countable")


def test_token_aggregate_roundtrip():
    L = load_ledger()
    with tempfile.TemporaryDirectory() as td:
        eng = _engagement(Path(td))
        led = L.EventLedger(eng, agent="dev-lead", tier="L")
        led.emit("budget_checkpoint",
                 payload={"scope": "wave", "pct_of_budget": 0.8},
                 tokens={"total": 412_000, "by_model": {"opus": 380_000}})
        ev = _lines(eng)[-1]
        assert ev["tokens"]["total"] == 412_000
        assert L.canonical_event_hash(ev) == ev["event_hash"], "tokens are covered by the hash"
        assert L.EventLedger.verify_chain(eng)["status"] == "ok"
    print("PASS test_token_aggregate_roundtrip")


TESTS = [
    test_fresh_chain_verifies,
    test_edited_past_event_is_tamper,
    test_removed_past_event_is_tamper,
    test_concurrent_append_is_fork_not_tamper,
    test_legacy_v1_prefix_is_not_a_break,
    test_gate_decision_must_be_countable,
    test_token_aggregate_roundtrip,
]


def main(argv: list[str]) -> int:
    global _MODULE_OVERRIDE
    if "--module" in argv:
        _MODULE_OVERRIDE = Path(argv[argv.index("--module") + 1]).resolve()
        print(f"module under test: {_MODULE_OVERRIDE}")
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001 — standalone runner reports, does not raise
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    total = len(TESTS)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
