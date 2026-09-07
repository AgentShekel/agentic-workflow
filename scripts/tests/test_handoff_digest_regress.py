#!/usr/bin/env python3
"""Regression guard — handoff-digest binding.

Before this check existed, an acceptance verdict was bound to nothing. handoff.md
could be edited after an ACCEPT, or reworked in place without bumping the iteration
counter, and the recorded verdict kept reading as current: the engagement carried an
approval of content no longer in the file. Nothing in the precheck noticed.

The failure direction that matters here is the FALSE NEGATIVE (a tampered handoff that
still passes), so case A is the reason this file exists. But a check that fires on
legitimate rework would be worse than no check at all, because it would be waived within
a week and then ignored — hence B, D, E and H, which pin every path that must NOT fail.

  A. TAMPER FAILS          verdict for the current iteration, handoff changed since.
  B. REWORK PASSES         verdict from an earlier iteration; the handoff is SUPPOSED to
                           differ after rework.
  C. BOUND PASSES          recorded digest equals the current one.
  D. UNBOUND WARNS         a verdict with no recorded digest is a warn with the exact
                           line to paste, never a hard fail: every engagement written
                           before this check has no digest line.
  E. QUIET SKIPS           no handoff / no acceptance-log / no verdict yet.
  F. WHITESPACE IS SHAPE   CRLF, trailing spaces and trailing blank lines must not move
                           the digest, or a Windows-side rewrite reads as tampering.
  G. CONTENT IS CONTENT    a one-character content edit MUST move the digest. F must not
                           be implemented by normalizing away things that matter.
  H. UNKNOWN ITERATION     mismatch with no readable counter warns instead of failing:
                           rework and a later edit are indistinguishable without it.
  I. LIVE SUBPROCESS       handoff-precheck.py itself exits 1 and names the check on a
                           tampered M-tier engagement. A unit-green check that was never
                           wired into the dispatcher is the bug this pins.

Run standalone or under pytest:
  python test_handoff_digest_regress.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck import (
    check_handoff_digest,
    handoff_digest,
    normalize_for_digest,
)

HANDOFF = "# Handoff\n\n## 1 Diff summary\n\nTwo files changed.\n"

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        FAILURES.append(label)


def mkeng(root: Path, name: str, *, handoff: str | None = HANDOFF,
          log: str | None = None, iteration: int | None = None) -> Path:
    eng = root / name / "engagement"
    eng.mkdir(parents=True)
    (eng / "criteria.md").write_text(
        "---\nengagement: t\ndomain: dev\nsize: M\nux_heavy: false\ntools_required: []\n---\n",
        encoding="utf-8")
    if handoff is not None:
        (eng / "handoff.md").write_text(handoff, encoding="utf-8")
    if log is not None:
        (eng / "acceptance-log.md").write_text(log, encoding="utf-8")
    if iteration is not None:
        (eng / "iteration").write_text(f"{iteration}\n", encoding="utf-8")
    return eng


def log_section(iter_n: int, verdict: str = "ACCEPT", digest: str | None = None) -> str:
    body = f"## Iteration {iter_n}\n\n### Verdict: {verdict}\n\nAdjudicated.\n"
    if digest:
        body += f"\nhandoff-sha256: {digest}\n"
    return body


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # --- A. tamper fails -------------------------------------------------
        eng = mkeng(root, "a", iteration=1)
        bound = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "ACCEPT", bound), encoding="utf-8")
        (eng / "handoff.md").write_text(HANDOFF + "\nQuietly added after the verdict.\n",
                                        encoding="utf-8")
        r = check_handoff_digest(eng)
        check(r["status"] == "fail", f"A: tampered handoff must fail, got {r['status']}")
        check("changed after" in r["detail"], "A: detail must say the handoff changed after the verdict")
        check(bool(r.get("fix")), "A: a fail must carry a fix")

        # --- B. rework passes ------------------------------------------------
        eng = mkeng(root, "b", iteration=2)
        old = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "REJECT", old), encoding="utf-8")
        (eng / "handoff.md").write_text(HANDOFF + "\nReworked for iteration 2.\n", encoding="utf-8")
        r = check_handoff_digest(eng)
        check(r["status"] == "pass", f"B: rework past an earlier verdict must pass, got {r['status']}")

        # --- C. bound passes -------------------------------------------------
        eng = mkeng(root, "c", iteration=1)
        d = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "ACCEPT", d), encoding="utf-8")
        check(check_handoff_digest(eng)["status"] == "pass", "C: matching digest must pass")

        # backtick-wrapped and `=` separated forms are the same record
        (eng / "acceptance-log.md").write_text(
            f"## Iteration 1\n\n### Verdict: ACCEPT\n\nhandoff-sha256 = `{d.upper()}`\n",
            encoding="utf-8")
        check(check_handoff_digest(eng)["status"] == "pass",
              "C: backticked / uppercase / `=` digest record must still match")

        # --- D. unbound warns ------------------------------------------------
        eng = mkeng(root, "d", iteration=1, log=log_section(1, "ACCEPT"))
        r = check_handoff_digest(eng)
        check(r["status"] == "warn", f"D: verdict without a digest must warn, not fail, got {r['status']}")
        check(handoff_digest(eng) in (r.get("fix") or ""),
              "D: the warn must hand over the exact digest to paste")

        # --- E. quiet skips --------------------------------------------------
        check(check_handoff_digest(mkeng(root, "e1", handoff=None))["status"] == "skip",
              "E: no handoff.md must skip")
        check(check_handoff_digest(mkeng(root, "e2"))["status"] == "skip",
              "E: no acceptance-log.md must skip")
        check(check_handoff_digest(mkeng(root, "e3", log="## Iteration 1\n\nNotes, no verdict.\n"))["status"] == "skip",
              "E: acceptance-log without a verdict must skip")

        # --- F. whitespace is shape ------------------------------------------
        base = normalize_for_digest(HANDOFF)
        check(normalize_for_digest(HANDOFF.replace("\n", "\r\n")) == base, "F: CRLF must normalize")
        check(normalize_for_digest(HANDOFF.replace("\n", "\r")) == base, "F: lone CR must normalize")
        check(normalize_for_digest(HANDOFF.replace("changed.", "changed.   ")) == base,
              "F: trailing spaces must normalize")
        check(normalize_for_digest("\n\n" + HANDOFF + "\n\n\n") == base,
              "F: leading/trailing blank lines must normalize")

        # --- G. content is content -------------------------------------------
        check(normalize_for_digest(HANDOFF.replace("Two files", "Ten files")) != base,
              "G: a content edit must change the normalized form")
        check(normalize_for_digest(HANDOFF.replace("Two files", "Two  files")) != base,
              "G: interior whitespace is content, not shape")

        # --- H. unknown iteration warns --------------------------------------
        eng = mkeng(root, "h")  # no iteration file
        stale = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "ACCEPT", stale), encoding="utf-8")
        (eng / "handoff.md").write_text(HANDOFF + "\nchanged\n", encoding="utf-8")
        r = check_handoff_digest(eng)
        check(r["status"] == "warn",
              f"H: mismatch with no readable counter must warn, not fail, got {r['status']}")

        # BOM-written counter must still parse (the 2026-06-04 false-failure class)
        eng = mkeng(root, "h2")
        (eng / "iteration").write_text("﻿2\n", encoding="utf-8")
        old = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "REJECT", old), encoding="utf-8")
        (eng / "handoff.md").write_text(HANDOFF + "\nrework\n", encoding="utf-8")
        r = check_handoff_digest(eng)
        check(r["status"] == "pass", f"H: BOM-prefixed counter must parse as rework, got {r['status']}")

        # --- I. live subprocess ----------------------------------------------
        eng = mkeng(root, "i", iteration=1)
        d = handoff_digest(eng)
        (eng / "acceptance-log.md").write_text(log_section(1, "ACCEPT", d), encoding="utf-8")
        (eng / "handoff.md").write_text(HANDOFF + "\nedited after the verdict\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "handoff-precheck.py"), str(eng), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        check(proc.returncode == 1,
              f"I: precheck must exit 1 on a tampered handoff, got {proc.returncode}")
        try:
            payload = json.loads(proc.stdout)
            names = {c.get("name"): c.get("status") for c in payload.get("checks", [])}
            check(names.get("handoff-digest") == "fail",
                  f"I: handoff-digest must be wired into the M-tier dispatch and fail, saw {names.get('handoff-digest')!r}")
        except json.JSONDecodeError:
            FAILURES.append(f"I: precheck --json output unparseable: {proc.stdout[:200]}")

        # the digest printer must agree with the check, or the acceptor records a wrong value
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "handoff-digest.py"), str(eng), "--bare"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        check(proc.returncode == 0 and proc.stdout.strip() == handoff_digest(eng),
              "I: handoff-digest.py must print the same digest the check computes")

    if FAILURES:
        print(f"FAIL — {len(FAILURES)} regression(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS — handoff-digest binding regressions held")
    return 0


def test_handoff_digest_regression():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
