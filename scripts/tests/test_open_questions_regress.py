#!/usr/bin/env python3
"""Regression guard — the criteria.md open-questions check.

Intake asks one clarifying question and locks criteria. Whatever stayed ambiguous
after that used to live nowhere: not in criteria.md, not in the handoff, not in
the acceptance record. It came back as a specialist guessing, and the guess was
only visible once the manager rejected the result.

The whole value of the section is the DISPOSITION, not the question. A question
with no status is worth nothing, and a waived one must keep travelling rather than
vanish. Everything below pins that distinction, plus the backward-compatibility
that keeps the check from being waived on day one.

  A. NO SECTION SKIPS       every engagement written before this convention has no
                            section; a warn there would train people to ignore it.
  B. EMPTY IS A PASS        "nothing was left hanging" is a real, common answer and
                            is not the same as having no section.
  C. NO STATUS WARNS        a row nobody dispositioned is indistinguishable from a
                            row nobody read.
  D. STILL OPEN WARNS       reaching handoff with an open question means intake let
                            it through.
  E. WAIVED TRAVELS         waived passes AND is named in the detail, because the
                            manager has to see what was decided without an answer.
  F. ANSWERED PASSES        the ordinary good path.
  G. NEVER FAILS            no input may make this check `fail`. The blocking half
                            lives at intake; a hard gate at handoff on a brand-new
                            section gets waived once and then ignored forever.
  H. LIVE SUBPROCESS        wired into the S dispatch set and visible in --json.

Run standalone or under pytest:
  python test_open_questions_regress.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck import check_open_questions

FM = ("---\nengagement: t\ndomain: dev\nsize: S\nux_heavy: false\n"
      "tools_required: []\n---\n\n# Acceptance criteria\n\n## Scope\nx\n")

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def mkeng(root: Path, name: str, oq: str | None) -> Path:
    eng = root / name / "engagement"
    eng.mkdir(parents=True)
    body = FM + (f"\n## Open questions\n{oq}\n" if oq is not None else "")
    (eng / "criteria.md").write_text(body, encoding="utf-8")
    return eng


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        seen_statuses = set()

        def run(name: str, oq: str | None) -> dict:
            r = check_open_questions(mkeng(root, name, oq))
            seen_statuses.add(r["status"])
            return r

        # --- A. no section skips ---------------------------------------------
        r = run("a", None)
        check(r["status"] == "skip", f"A: no section must skip, got {r['status']}")

        # --- B. empty is a pass ----------------------------------------------
        for label, body in (("b1", ""), ("b2", "\n"), ("b3", "(none)")):
            r = run(label, body)
            check(r["status"] == "pass", f"B/{label}: an empty section must pass, got {r['status']}")

        # --- C. no status warns ----------------------------------------------
        r = run("c", "- [ ] q-1: which auth provider — needed to: pick the flow")
        check(r["status"] == "warn", f"C: a row with no status must warn, got {r['status']}")
        check("q-1" in r["detail"], "C: the warn must name the offending question id")

        # --- D. still open warns ---------------------------------------------
        r = run("d", "- [ ] q-1: which provider — needed to: pick the flow — status: open")
        check(r["status"] == "warn", f"D: an open question at handoff must warn, got {r['status']}")
        check("q-1" in r["detail"], "D: the warn must name the open question")

        # mixed: one answered, one open — the open one still governs
        r = run("d2", "- [x] q-1: a — status: answered\n- [ ] q-2: b — status: open")
        check(r["status"] == "warn" and "q-2" in r["detail"] and "q-1" not in r["detail"],
              f"D: a mix must warn about the open one only, got {r['status']} / {r['detail']}")

        # --- E. waived travels -----------------------------------------------
        r = run("e", "- [x] q-1: which provider — status: waived\n      assume email+password")
        check(r["status"] == "pass", f"E: waived must pass, got {r['status']}")
        check("waived" in r["detail"] and "q-1" in r["detail"],
              "E: a waived question must be NAMED in the detail — the manager has to see "
              f"what was decided without an answer. got: {r['detail']!r}")

        # --- F. answered passes ----------------------------------------------
        r = run("f", "- [x] q-1: which provider — status: answered\n      user said: Yandex ID")
        check(r["status"] == "pass", f"F: answered must pass, got {r['status']}")

        # case and separator tolerance — this is prose a human types
        r = run("f2", "* q-1 : which provider - Status: Answered")
        check(r["status"] == "pass", f"F: parsing must tolerate human formatting, got {r['status']}")

        # --- G. never fails --------------------------------------------------
        check("fail" not in seen_statuses,
              f"G: this check must never return `fail`; saw {sorted(seen_statuses)}")

        # --- H. live subprocess ----------------------------------------------
        eng = mkeng(root, "h", "- [ ] q-1: unresolved — status: open")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "handoff-precheck.py"), str(eng), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        try:
            names = {c.get("name"): c.get("status")
                     for c in json.loads(proc.stdout).get("checks", [])}
            check(names.get("open-questions") == "warn",
                  f"H: open-questions must be wired into the S dispatch set and warn, "
                  f"saw {names.get('open-questions')!r}")
        except json.JSONDecodeError:
            FAILURES.append(f"H: precheck --json unparseable: {proc.stdout[:200]}")

    if FAILURES:
        print(f"FAIL — {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS — open-questions regressions held")
    return 0


def test_open_questions_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
