#!/usr/bin/env python3
"""Regression guard — outcome-due.py.

This script is the only thing carrying an outcome hypothesis' check date forward. Every way it
can be wrong is silent: a hypothesis it fails to parse is indistinguishable from an engagement
that never wrote one, and both read as "nothing due". So the failure direction that matters is
the FALSE NEGATIVE, and most of what is pinned here came from a cross-family review (Codex,
2026-08-27) plus one self-inflicted bug found while applying that review.

  A. DUE IS REPORTED         past date, no outcome_check event.
  B. NOT DUE STAYS QUIET     future date; `metric: none`; unfilled template placeholders;
                             an engagement whose ledger already holds an outcome_check.
  C. MARKDOWN VARIANTS       bold labels (`- **check on:** ...`) parse. They are ordinary
                             Markdown, and an unbolded-only regex drops the engagement whole.
  D. `none` IS A WORD        `nonequilibrium concentration` is a metric, not a declared
                             no-effect hypothesis. The word-boundary in that regex was once
                             written as a literal backspace byte, which disabled the check
                             entirely — a corruption no compile step would catch.
  E. BAD LEDGER LINES        a valid JSON line that is not an object must not crash the scan
                             and take every other engagement's report down with it.

Run standalone or under pytest:
  python test_outcome_due_regress.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_outcome_due", SCRIPTS_DIR / "outcome-due.py")
outcome_due = importlib.util.module_from_spec(_spec)
sys.modules["_outcome_due"] = outcome_due
_spec.loader.exec_module(outcome_due)

TODAY = dt.date(2026, 8, 27)


def mkeng(root: Path, name: str, body: str, ledger: str | None = None,
          holder: str = "engagement") -> Path:
    eng = root / name / holder
    eng.mkdir(parents=True)
    (eng / "criteria.md").write_text("---\nsize: M\n---\n\n## Outcome hypothesis\n" + body,
                                     encoding="utf-8")
    if ledger is not None:
        (eng / "events.jsonl").write_text(ledger, encoding="utf-8")
    return eng


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        mkeng(root, "a-plain", "- metric: p95 latency\n- check on: 2026-08-01\n")
        mkeng(root, "b-future", "- metric: signups\n- check on: 2026-12-01\n")
        mkeng(root, "c-infra",
              "- metric: none (infrastructure work, no user-visible effect claimed)\n"
              "- check on: 2026-08-01\n")
        mkeng(root, "d-template", "- metric: {what should change}\n- check on: {YYYY-MM-DD}\n")
        mkeng(root, "e-closed", "- metric: conversion\n- check on: 2026-08-01\n",
              ledger='{"payload_type":"outcome_check","payload":{"result":"confirmed"}}\n')
        mkeng(root, "f-bold", "- **metric:** conversion rate\n- **check on:** 2026-08-26\n")
        mkeng(root, "g-nonequilibrium",
              "- metric: nonequilibrium concentration\n- check on: 2026-08-26\n")
        mkeng(root, "h-bad-ledger", "- metric: retention\n- check on: 2026-08-01\n",
              ledger='["outcome_check"]\n{"not":"an event"}\n')
        # an outcome_check carrying no `result` records that someone looked, not what they
        # found; metrics.py reads payload.result, so it must not silence the reminder
        mkeng(root, "i-no-result", "- metric: activation\n- check on: 2026-08-01\n",
              ledger='{"payload_type":"outcome_check","payload":{"note":"placeholder"}}\n')
        # the archived and aborted holders must be scanned too, or the explicit glob list
        # could be trimmed back to `engagement/` with every test still green
        mkeng(root, "k-archived", "- metric: churn\n- check on: 2026-08-01\n",
              holder="engagement-archived")
        mkeng(root, "l-aborted", "- metric: latency\n- check on: 2026-08-01\n",
              holder="engagement-aborted")
        # nested one level deeper than the old fixed-depth globs reached
        mkeng(root, "m-nested", "- metric: signup drop\n- check on: 2026-08-01\n",
              holder="engagement-archived/2026-06-01-thing/primary")
        # a whitespace-only result is not a finding
        mkeng(root, "n-blank-result", "- metric: arpu\n- check on: 2026-08-01\n",
              ledger='{"payload_type":"outcome_check","payload":{"result":"  "}}\n')
        # payload need not be an object
        mkeng(root, "o-list-payload", "- metric: dau\n- check on: 2026-08-01\n",
              ledger='{"payload_type":"outcome_check","payload":["result"]}\n')
        # a stray directory that merely starts with "engagement" is not an engagement
        notes = root / "j-notes" / "engagement-notes"
        notes.mkdir(parents=True)
        (notes / "criteria.md").write_text(
            "## Outcome hypothesis\n- metric: x\n- check on: 2026-08-01\n", encoding="utf-8")

        try:
            due = outcome_due.scan(TODAY, [root])
        except Exception as exc:  # noqa: BLE001 — a crash here is the defect under test
            print(f"  [FAIL] scan() raised {type(exc).__name__}: {exc}")
            return 1
        # key on any path component, since holders now nest to arbitrary depth
        names = {part for d in due for part in Path(d["engagement"]).parts}

        print("A. due is reported")
        results.append(check("a-plain (past date, no event)", "a-plain" in names, f"due={sorted(names)}"))

        print("\nB. not due stays quiet")
        for name, why in [("b-future", "date is in the future"),
                          ("c-infra", "metric: none"),
                          ("d-template", "unfilled placeholders"),
                          ("e-closed", "outcome_check already in the ledger")]:
            results.append(check(f"{name} ({why})", name not in names, f"due={sorted(names)}"))

        print("\nC. markdown variants parse")
        results.append(check("f-bold (`- **check on:** 2026-08-26`)", "f-bold" in names,
                             f"due={sorted(names)}"))

        print("\nD. `none` is a whole word")
        results.append(check("g-nonequilibrium is a metric, not 'none'",
                             "g-nonequilibrium" in names, f"due={sorted(names)}"))

        print("\nE. malformed ledger lines do not crash the scan")
        results.append(check("h-bad-ledger still evaluated", "h-bad-ledger" in names,
                             f"due={sorted(names)}"))
        results.append(check("i-no-result: outcome_check without a result does not close it",
                             "i-no-result" in names, f"due={sorted(names)}"))
        results.append(check("j-notes: engagement-notes/ is not an engagement",
                             "j-notes" not in names, f"due={sorted(names)}"))
        results.append(check("n-blank-result: a whitespace result does not close it",
                             "n-blank-result" in names, f"due={sorted(names)}"))
        results.append(check("o-list-payload: a non-object payload does not crash or close it",
                             "o-list-payload" in names, f"due={sorted(names)}"))

        print("\nG. every engagement holder is scanned, at any depth")
        for name in ("k-archived", "l-aborted", "m-nested"):
            results.append(check(f"{name} found", name in names, f"due={sorted(names)}"))
        results.append(check("no engagement reported twice",
                             len(due) == len({d["engagement"] for d in due}),
                             f"{len(due)} rows, {len({d['engagement'] for d in due})} unique"))

        print("\nF. overdue arithmetic")
        a = next((d for d in due if Path(d["engagement"]).parent.name == "a-plain"), None)
        results.append(check("a-plain is 26 days overdue",
                             a is not None and a["days_overdue"] == 26,
                             f"got {a and a['days_overdue']}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_outcome_due_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
