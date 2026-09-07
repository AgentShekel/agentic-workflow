#!/usr/bin/env python3
"""Regression guard — metrics.py: no invented numbers, no false zeros.

The metric layer exists because the corpus measured its activity and not its
result. The way that fails a second time is subtler than having no metrics at
all: a dashboard that prints a confident number for a feed nobody writes to.
Two properties are pinned here, both learned from the first run of the script:

  A. NO DATA IS NOT ZERO   `post_accept_defect_rate` over 7 accepted engagements
                           with zero defect EVENTS printed "0.0% OK" on the first
                           run. That reads as "quality is fine" when it means
                           "nothing reports defects". It must be `no data`.
  B. LEDGER BEATS PROSE    override rate must come from gate_decision events when
                           they exist, and only fall back to hand-parsing the
                           acceptance-log verdict line when they do not — with
                           the fallback SAID OUT LOUD in the note.

Run standalone or under pytest:
  python test_metrics_regress.py
  python test_metrics_regress.py --script /tmp/patched-metrics.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPT = SCRIPTS_DIR / "metrics.py"
_SCRIPT_OVERRIDE: Path | None = None


def load_metrics():
    path = _SCRIPT_OVERRIDE or DEFAULT_SCRIPT
    spec = importlib.util.spec_from_file_location("metrics_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["metrics_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_engagement(root: Path, project: str, name: str, *, tier="M",
                    verdict: str | None = None, events: list[dict] | None = None,
                    handoff=False, nested=False) -> Path:
    """Build one archived engagement. `nested` puts artefacts in primary/,
    which is how multi-track engagements are laid out in the field."""
    eng = root / project / "engagement-archived" / name
    art = eng / "primary" if nested else eng
    art.mkdir(parents=True, exist_ok=True)
    (art / "criteria.md").write_text(f"---\ndomain: dev\nsize: {tier}\n---\n# crit\n",
                                     encoding="utf-8")
    if verdict:
        (art / "acceptance-log.md").write_text(
            f"# Acceptance\n\n### Verdict: {verdict}\n\n- signal 1 SUSTAINED\n"
            f"- signal 2 OVERRULED\n", encoding="utf-8")
    if handoff:
        (art / "handoff.md").write_text("# handoff\n", encoding="utf-8")
    if events is not None:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from lib.ledger import EventLedger
        led = EventLedger(eng, agent="dev-lead", tier=tier)
        for e in events:
            led.emit(e["type"], payload=e.get("payload"), verdict=e.get("verdict"),
                     tokens=e.get("tokens"))
    return eng


# --------------------------------------------------------------------- tests

def test_empty_corpus_reports_no_data_not_zero():
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        make_engagement(root, "proj", "e1", verdict=None, events=None)
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        metrics = M.compute(rows)
        for key in ("override_rate", "agreement_rate", "iv_tempo_ratio",
                    "outcome_validation_rate", "tokens_recorded"):
            assert metrics[key]["value"] is None, f"{key} invented a number: {metrics[key]}"
            assert metrics[key]["note"], f"{key} reports no data without saying why"
    print("PASS test_empty_corpus_reports_no_data_not_zero")


def test_accepted_with_no_defect_events_is_no_data():
    """Property A — the false zero that shipped on the first run."""
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        for i in range(3):
            make_engagement(root, "proj", f"acc{i}", verdict="ACCEPT",
                            events=[{"type": "specialist_completed",
                                     "payload": {"report": "r.md"}}])
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        m = M.compute(rows)["post_accept_defect_rate"]
        assert m["value"] is None, f"zero defect events reported as a rate: {m}"
        assert "empty feed" in m["note"], m["note"]

        th = M.load_thresholds()
        assert M.status_of("post_accept_defect_rate", m["value"], th) == "no data"
    print("PASS test_accepted_with_no_defect_events_is_no_data")


def test_defects_present_produce_a_rate():
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        make_engagement(root, "proj", "a", verdict="ACCEPT", events=[
            {"type": "post_accept_defect",
             "payload": {"severity": "high", "summary": "regression"}}])
        make_engagement(root, "proj", "b", verdict="ACCEPT", events=[])
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        m = M.compute(rows)["post_accept_defect_rate"]
        assert m["value"] == 50.0, m
    print("PASS test_defects_present_produce_a_rate")


def test_gate_events_beat_prose_fallback():
    """Property B — and the fallback must admit it is a fallback."""
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        # prose only: 2 ACCEPT + 2 REJECT -> 50% via the verdict line
        for i in range(2):
            make_engagement(root, "p1", f"ok{i}", verdict="ACCEPT", events=[])
            make_engagement(root, "p1", f"no{i}", verdict="REJECT", events=[])
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        prose = M.compute(rows)["override_rate"]
        assert prose["value"] == 50.0, prose
        assert "fallback" in prose["note"], prose["note"]

        # now add gate_decision events: 3 PROCEED + 1 REJECT -> 25%, prose ignored
        make_engagement(root, "p2", "gated", verdict="ACCEPT", events=[
            {"type": "gate_decision", "payload": {"decision": d, "gate": "human-directive"}}
            for d in ("PROCEED", "PROCEED", "PROCEED", "REJECT")])
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        gated = M.compute(rows)["override_rate"]
        assert gated["value"] == 25.0, gated
        assert gated["note"] == "from gate_decision events", gated["note"]
    print("PASS test_gate_events_beat_prose_fallback")


def test_nested_primary_artefacts_are_found():
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        make_engagement(root, "proj", "multi", tier="L", verdict="REJECT",
                        handoff=True, events=[], nested=True)
        row = M.collect(M.find_engagements([str(root)])[0])
        assert row["tier"] == "L", row
        assert row["verdict"] == "REJECT", row
        assert row["has_handoff"] and row["has_acceptance_log"], row
    print("PASS test_nested_primary_artefacts_are_found")


def test_nested_ledger_is_found():
    """A multi-track engagement keeps its artefacts in primary/, ledger included.
    Reading only the engagement root silently drops every one of its events —
    caught in the field when archiving an engagement moved its ledger under
    primary/ and the corpus quietly lost 12 events and a whole rework series."""
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        eng = root / "proj" / "engagement-archived" / "nested"
        (eng / "primary").mkdir(parents=True)
        (eng / "primary" / "criteria.md").write_text("---\nsize: L\n---\n", encoding="utf-8")
        sys.path.insert(0, str(SCRIPTS_DIR))
        from lib.ledger import EventLedger
        led = EventLedger(eng / "primary", agent="dev-lead", tier="L")
        led.emit("specialist_completed", payload={"report": "r-rework.md"})
        led.emit("wave_completed", payload={"wave": 1})

        row = M.collect(M.find_engagements([str(root)])[0])
        assert row["events"] == 4, f"nested ledger not read: {row['events']} events"
        assert row["has_ledger"] and row["chain_status"] == "ok", row
        assert row["rework_reports"] == 1, row
    print("PASS test_nested_ledger_is_found")


def test_cumulative_token_snapshots_become_phase_deltas():
    """The engine emits CUMULATIVE spend at each phase boundary. A phase costs the
    delta since the previous snapshot, and the engagement total is the PEAK — summing
    cumulative values would multiply the same tokens by the number of emit points."""
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        # delivery 100k, validation 40k, handoff 10k -> ratio 100/40 = 2.5, total 150k
        make_engagement(root, "proj", "e", verdict="ACCEPT", events=[
            {"type": "wave_completed", "payload": {"wave": 1}, "tokens": {"total": 100_000}},
            {"type": "validator_completed", "payload": {"validator": "code-reviewer"},
             "tokens": {"total": 140_000}},
            {"type": "handoff_submitted", "payload": {}, "tokens": {"total": 150_000}},
        ])
        row = M.collect(M.find_engagements([str(root)])[0])
        assert row["produce_tokens"] == 100_000, row
        assert row["validate_tokens"] == 40_000, row
        assert row["tokens_total"] == 150_000, f"total must be the peak, not the sum: {row}"

        metrics = M.compute([row])
        assert metrics["iv_tempo_ratio"]["value"] == 2.5, metrics["iv_tempo_ratio"]
        assert metrics["tokens_recorded"]["value"] == 150_000, metrics["tokens_recorded"]
    print("PASS test_cumulative_token_snapshots_become_phase_deltas")


def test_status_bands_and_directions():
    M = load_metrics()
    th = M.load_thresholds()
    assert M.status_of("override_rate", 25, th) == "OK"          # inside 10-40 band
    assert M.status_of("override_rate", 3, th) == "ALERT"        # < half the floor
    assert M.status_of("override_rate", 45, th) == "WARN"        # just outside
    assert M.status_of("ledger_coverage", 95, th) == "OK"        # higher_is_better
    assert M.status_of("ledger_coverage", 40, th) == "ALERT"
    assert M.status_of("iv_tempo_ratio", 1.5, th) == "OK"        # lower_is_better
    assert M.status_of("iv_tempo_ratio", 3.5, th) == "ALERT"
    assert M.status_of("nonexistent_metric", 1, th) == "no target"
    print("PASS test_status_bands_and_directions")


def test_every_metric_has_a_threshold_entry():
    """A metric with no target is decoration — the script must not grow one."""
    M = load_metrics()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        make_engagement(root, "proj", "e", verdict="ACCEPT", events=[])
        rows = [M.collect(e) for e in M.find_engagements([str(root)])]
        keys = set(M.compute(rows))
    th = set(M.load_thresholds())
    missing = keys - th
    assert not missing, f"metrics without a threshold triple: {sorted(missing)}"
    print("PASS test_every_metric_has_a_threshold_entry")


def test_json_mode_is_machine_readable():
    M = load_metrics()
    import contextlib, io  # noqa: E401 — local to the one test that captures stdout
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "projects"
        make_engagement(root, "proj", "e", verdict="ACCEPT", events=[])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = M.main(["--roots", str(root), "--json"])
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert "metrics" in payload and "engagements" in payload
    print("PASS test_json_mode_is_machine_readable")


def test_hook_speaks_only_on_new_information():
    """A hook that repeats the same ALERTs every session is wallpaper in a day,
    and the metric it guards dies with it. Speak on change, then shut up."""
    M = load_metrics()
    import contextlib, io  # noqa: E401 — local to the tests that capture stdout
    with tempfile.TemporaryDirectory() as td:
        stamp = Path(td) / "stamp"
        M.STAMP_FILE = stamp

        def run_hook(root):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                M.main(["--roots", str(root), "--hook"])
            return buf.getvalue()

        root = Path(td) / "projects"
        # an engagement with no ledger and no handoff -> ledger_coverage/evidence ALERT
        make_engagement(root, "proj", "e1", verdict="ACCEPT", events=None)

        first = run_hook(root)
        assert "ALERT" in first, f"first run must speak: {first!r}"
        second = run_hook(root)
        assert second == "", f"unchanged alerts must stay silent, got: {second!r}"

        # a previously-reported alert disappearing is news again
        data = json.loads(stamp.read_text(encoding="utf-8"))
        data["alerts"] = sorted(data["alerts"] + ["some_other_metric"])
        stamp.write_text(json.dumps(data), encoding="utf-8")
        third = run_hook(root)
        assert "cleared: some_other_metric" in third, third
    print("PASS test_hook_speaks_only_on_new_information")


TESTS = [
    test_empty_corpus_reports_no_data_not_zero,
    test_nested_ledger_is_found,
    test_cumulative_token_snapshots_become_phase_deltas,
    test_hook_speaks_only_on_new_information,
    test_accepted_with_no_defect_events_is_no_data,
    test_defects_present_produce_a_rate,
    test_gate_events_beat_prose_fallback,
    test_nested_primary_artefacts_are_found,
    test_status_bands_and_directions,
    test_every_metric_has_a_threshold_entry,
    test_json_mode_is_machine_readable,
]


def main(argv: list[str]) -> int:
    global _SCRIPT_OVERRIDE
    if "--script" in argv:
        _SCRIPT_OVERRIDE = Path(argv[argv.index("--script") + 1]).resolve()
        print(f"script under test: {_SCRIPT_OVERRIDE}")
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001 — standalone runner reports, does not raise
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
