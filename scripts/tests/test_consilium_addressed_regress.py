#!/usr/bin/env python3
"""Regression guard — check_consilium_addressed in lib/precheck/acceptance.py.

The gate this replaces was DEFERRED in 2026-06 for a good reason: a naive "M/L must have
consilium artefacts" rule false-REJECTs the legitimate cases, and a gate that cries wolf gets
switched off. Measured 2026-08-27 over 15 archived engagements, three L-tier ones were accepted
with no adversary artefacts and two of those were entirely proper — one waived by the human in
criteria.md, one disclosed in the acceptance-log when the subprocess stack was unavailable.

So the property is not "the consilium ran". It is "the verdict does not leave the consilium
unmentioned". Both failure directions matter, and this file pins both:

  A. SILENT SKIP FAILS       M/L verdict, no adversary output, no summary, no sentence about
                             either -> fail. This is the case the real corpus contained.
  B. PROOF PASSES            per-role adversary JSON, or consilium-summary.md, is enough.
  C. DISCLOSURE PASSES       waived / overridden / could-not-run / substituted, in the
                             acceptance-log or in criteria.md, in any of the phrasings the real
                             corpus used, INCLUDING one that wraps across a line break.
  D. NOT-YET STAYS SKIP      no acceptance-log means the consilium may still be pending; and S
                             has no consilium phase at all.

C is the direction that rots. Every phrase below came from a real acceptance-log; widening this
list without a corpus re-run turns the gate into a rubber stamp.

Run standalone or under pytest:
  python test_consilium_addressed_regress.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck.acceptance import check_consilium_addressed

VERDICT = "# Acceptance log\n\n### Verdict: ACCEPT\n"

# Verbatim dispositions from the archived corpus.
DISCLOSURES = [
    "criteria.md waives the mandatory PROTOCOL consilium gate.",
    "the L-tier consilium was human-overridden (criteria note).",
    "This box has no recursive sub-agent dispatch and no consilium/adversary run.",
    "M-tier consilium adversary (peer-Opus) NOT run — the script hung.",
    "`adversary_lg.py --consilium L` requires the director sub-process stack, which is\n"
    "unavailable here, so the L-tier 5-reviewer consilium did NOT run.",
    # wraps across a line break, which an earlier per-line rule missed
    "In lieu of a separately\nspun consilium-M workflow, the acceptor performed direct\n"
    "independent verification.",
]


def mkeng(tmp: Path, *, log: str | None = VERDICT, summary: bool = False,
          outputs: list[str] | None = None, criteria: str = "") -> Path:
    eng = Path(tempfile.mkdtemp(dir=tmp))
    (eng / "criteria.md").write_text("---\nsize: L\n---\n" + criteria, encoding="utf-8")
    if log is not None:
        (eng / "acceptance-log.md").write_text(log, encoding="utf-8")
    if summary:
        (eng / "consilium-summary.md").write_text(
            "# Consilium summary\n\n| role | verdict |\n|---|---|\n"
            "| peer-opus | satisfied |\n", encoding="utf-8")
    vo = eng / "validation-outputs"
    vo.mkdir()
    for name in (outputs or []):
        (vo / name).write_text("{}", encoding="utf-8")
    return eng


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("A. silent skip fails")
        for tier in ("M", "L"):
            eng = mkeng(tmp)
            r = check_consilium_addressed(eng, tier)
            results.append(check(f"tier {tier}, verdict, nothing said -> fail",
                                 r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # a validator JSON is not an adversary JSON
        eng = mkeng(tmp, outputs=["code-reviewer-iter-1-20260101T000000Z.json",
                                  "security-auditor-iter-1-20260101T000000Z.json"])
        r = check_consilium_addressed(eng, "L")
        results.append(check("validator outputs alone -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))

        print("\nB. proof of run passes")
        for name in ("peer-opus-iter-1-20260101T000000Z.json",
                     "codex-blind-iter-2-20260101T000000Z.json",
                     "codex-informed-iter-1-20260101T000000Z.json",
                     "sonnet-scoped-iter-1-20260101T000000Z.json",
                     "haiku-scoped-iter-1-20260101T000000Z.json"):
            eng = mkeng(tmp, outputs=[name])
            r = check_consilium_addressed(eng, "L")
            results.append(check(f"{name.split('-iter')[0]} output -> pass",
                                 r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, summary=True)
        r = check_consilium_addressed(eng, "L")
        results.append(check("consilium-summary.md alone -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nC. disclosure passes (phrasings taken from the real corpus)")
        for text in DISCLOSURES:
            eng = mkeng(tmp, log=VERDICT + "\n" + text)
            r = check_consilium_addressed(eng, "L")
            results.append(check(f"in acceptance-log: {text.splitlines()[0][:52]!r}",
                                 r["status"] == "pass", f"got {r['status']}"))
        eng = mkeng(tmp, criteria="\n## Consilium note\nThe consilium is waived for this run.\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("disclosure in criteria.md -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nD. not-yet and no-phase stay skip")
        eng = mkeng(tmp, log=None)
        r = check_consilium_addressed(eng, "L")
        results.append(check("no acceptance-log -> skip",
                             r["status"] == "skip", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp)
        r = check_consilium_addressed(eng, "S")
        results.append(check("tier S -> skip", r["status"] == "skip", f"got {r['status']}"))

        print("\nE. unrelated prose does not excuse it")
        eng = mkeng(tmp, log=VERDICT + "\nAll validators ran and the suite is green.\n"
                                       "The consilium findings are listed in the table above.\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("mentions 'consilium' with no disposition -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))

        print("\nF. cross-family counterexamples (Codex, 2026-08-27)")
        # Each of these passed the gate before the fix listed beside it.
        for label, log_text in [
            ("disposition in a DIFFERENT sentence",
             "The consilium is listed in criteria. Instead of changing the unrelated footer, "
             "the team changed the logo."),
            ("unrelated sentences colliding after whitespace collapse",
             "The consilium was merely mentioned.\nThe unrelated deployment phase was skipped "
             "by the release manager."),
        ]:
            eng = mkeng(tmp, log=VERDICT + "\n" + log_text)
            r = check_consilium_addressed(eng, "L")
            results.append(check(f"{label} -> fail", r["status"] == "fail",
                                 f"got {r['status']}: {r['detail']}"))
        # a validator file that merely contains a role name is not proof of run
        eng = mkeng(tmp, outputs=["validator-peer-opus-review.json"])
        r = check_consilium_addressed(eng, "L")
        results.append(check("'validator-peer-opus-review.json' is not proof -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # an empty summary file is not a summary
        eng = mkeng(tmp)
        (eng / "consilium-summary.md").write_text("", encoding="utf-8")
        r = check_consilium_addressed(eng, "L")
        results.append(check("empty consilium-summary.md -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # and a phrasing the review found rejected for no good reason
        eng = mkeng(tmp, log=VERDICT + "\nThe consilium was skipped due to a network failure.\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("'skipped due to a network failure' -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nG. second cross-family pass (Codex, 2026-08-27)")
        # a sentence with no ending punctuation used to degrade to a whole-document window
        eng = mkeng(tmp, log=VERDICT + "\nThe consilium is merely mentioned and a long "
                                       "unrelated sentence ends with the old bundle being "
                                       "substituted\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("punctuation-free sentence, halves far apart -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # a NEGATED disposition says the opposite of a non-run
        eng = mkeng(tmp, log=VERDICT + "\nThe consilium was not skipped; it ran, but its JSON "
                                       "was lost.\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("'was NOT skipped' -> fail", r["status"] == "fail",
                             f"got {r['status']}: {r['detail']}"))
        # role prefix without the iter marker is a hand-named file, not proof of run
        eng = mkeng(tmp, outputs=["peer-opus-validator-review.json"])
        r = check_consilium_addressed(eng, "L")
        results.append(check("'peer-opus-validator-review.json' is not proof -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # Non-empty is the bar, and a length floor was tried and REMOVED. At 40 characters it
        # rejected the legitimate terse summary below while still admitting a longer
        # placeholder: it bought nothing and cost a false REJECT. Content quality belongs to
        # `director-verdict`, which audits whether every consilium signal was adjudicated.
        eng = mkeng(tmp)
        (eng / "consilium-summary.md").write_text("Waived by human; no consilium run.",
                                                  encoding="utf-8")
        r = check_consilium_addressed(eng, "L")
        results.append(check("terse but real summary -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp)
        (eng / "consilium-summary.md").write_text("   \n\n", encoding="utf-8")
        r = check_consilium_addressed(eng, "L")
        results.append(check("whitespace-only consilium-summary.md -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        # the real disclosure that must survive all of the above
        eng = mkeng(tmp, log=VERDICT + "\nThe consilium command adversary_lg.py could not run "
                                       "because the subprocess stack was unavailable.\n")
        r = check_consilium_addressed(eng, "L")
        results.append(check("filename with a dot does not break the disclosure -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_consilium_addressed_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
