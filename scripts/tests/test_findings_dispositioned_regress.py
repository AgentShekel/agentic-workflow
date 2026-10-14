#!/usr/bin/env python3
"""Regression guard: check_findings_dispositioned in lib/precheck/validators.py.

An engagement could reach handoff three iterations running with validator-confirmed
Medium findings open. They can sit under `approved_with_suggestions` verdicts,
so a guard keyed on `changes_required` would not have fired; iteration 3 listed every one in
handoff §7 and none in §11, which reads as honest and is still a deferral nobody waived.
engagement-protocol allows exactly two deferrals: criteria.md out-of-scope, or a director-approved
scope-sync.md waiver.

Both failure directions matter:

  A. PARKED FAILS        Medium+ in the latest output, no disposition in validation-log.md or
                         scope-sync.md -> fail, whatever the verdict and whatever handoff.md says.
  B. RE-RUN PASSES       a newer output of the same validator in the same iteration supersedes
                         the old one, including across the two timestamp shapes in the corpus.
  C. RECORD PASSES       the id cited in a section that rules it fixed / out of scope / waived,
                         in the shapes an accepted engagement used.
  D. NOT IN SCOPE        low/info/nit, consilium roles, preliminary files, older iterations.
  E. NOT YET             no outputs -> skip.

C is the direction that rots: a disposition vocabulary that grows "deferred" or "backlog"
turns the check into a rubber stamp for the exact failure it closes.

Run standalone or under pytest:
  python test_findings_dispositioned_regress.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.precheck.validators import check_findings_dispositioned

TS1 = "20261006T081619Z"
TS2 = "20261006T125834Z"


def finding(sev, msg="something", **extra):
    return {"severity": sev, "file": "src/x.py", "line": 1, "message": msg, "fix": "do y", **extra}


def mkeng(root: Path, outputs: dict, iteration=None, log=None, scope_sync=None, handoff=None) -> Path:
    eng = Path(tempfile.mkdtemp(dir=root)) / "engagement"
    (eng / "validation-outputs").mkdir(parents=True)
    for name, (verdict, findings) in outputs.items():
        (eng / "validation-outputs" / name).write_text(
            json.dumps({"verdict": verdict, "findings": findings}), encoding="utf-8")
    if iteration is not None:
        (eng / "iteration").write_text(str(iteration), encoding="utf-8")
    for fname, text in (("validation-log.md", log), ("scope-sync.md", scope_sync), ("handoff.md", handoff)):
        if text is not None:
            (eng / fname).write_text(text, encoding="utf-8")
    return eng


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


PARKED_LOG = (
    "# Validation log\n\n### code-reviewer\n\n"
    "verdict: approved_with_caveats (status: approved_with_suggestions)\n"
    "adversarial-verify: 7 confirmed / 1 refuted of 8\n"
    "summary: The consolidated tree covers D1 to D9.\n"
    f"output: engagement/validation-outputs/code-reviewer-iter-2-{TS1}.json\n"
)
PARKED_HANDOFF = (
    "## 7. Self-acceptance\n\n4. [crit-14] concern: empty API_TOKEN passes config validation. "
    "Confirmed Medium (code-reviewer).\n\n## 11. Known deferrals\n\n"
    "No validator-confirmed Medium or High is listed here; those are in section 7.\n"
)


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("A. parked Medium+ fails")
        eng = mkeng(tmp, {
            f"code-reviewer-iter-2-{TS1}.json": ("approved_with_suggestions",
                                                 [finding("low"), finding("medium", "empty API_TOKEN")]),
            f"security-auditor-iter-2-{TS1}.json": ("approved_with_suggestions", [finding("medium", "token in logs")]),
        }, iteration=2, log=PARKED_LOG, handoff=PARKED_HANDOFF)
        r = check_findings_dispositioned(eng)
        results.append(check("field shape: Medium under approved_with_suggestions, cited only in handoff -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        results.append(check("detail names both open ids",
                             "code-reviewer#1" in r["detail"] and "security-auditor#0" in r["detail"], r["detail"]))
        for sev in ("major", "high", "critical", "Medium"):
            eng = mkeng(tmp, {f"reality-checker-iter-1-{TS1}.json": ("approved", [finding(sev)])})
            r = check_findings_dispositioned(eng)
            results.append(check(f"severity {sev!r} -> fail", r["status"] == "fail", f"got {r['status']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("medium")])},
                    log="### code-reviewer\n- code-reviewer#0 deferred to backlog, follow-up ticket.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("id cited as 'deferred to backlog' with no ruling -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("low"), finding("medium")])},
                    log="### code-reviewer\n- code-reviewer#12 FIXED in abc123.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("code-reviewer#12 FIXED does not dispose of code-reviewer#1",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))

        print("\nB. a newer re-run in the same iteration supersedes")
        eng = mkeng(tmp, {
            f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("critical")]),
            f"code-reviewer-iter-1-{TS2}.json": ("approved", [finding("low")]),
        })
        r = check_findings_dispositioned(eng)
        results.append(check("clean re-run -> pass", r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        # '-' sorts before 'T': by filename the 13:57 T-stamp wins over the later 16:27 dash-stamp
        eng = mkeng(tmp, {
            "reality-checker-iter-1-20260603T135725Z.json": ("changes_required", [finding("medium")]),
            "reality-checker-iter-1-20260603-162718.json": ("approved", []),
        })
        r = check_findings_dispositioned(eng)
        results.append(check("mixed timestamp shapes: later dash-stamp re-run wins -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nC. a recorded disposition passes (real-world shapes)")
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("medium")])},
                    log="### code-reviewer\n- code-reviewer#0: FIXED in abc123, re-run clean.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("id on a FIXED line -> pass", r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        cf_log = (
            "### Out-of-plan validators\n\n"
            "`deploy-reviewer` (changes_required) and `infrastructure-reviewer` were NOT in plan.md.\n\n"
            "**Adjudication: OUT-OF-SCOPE.** Every finding is a PROJECT-WIDE, PRE-EXISTING infra condition.\n\n"
            "Itemised:\n"
            "- deploy-reviewer#1 (major, CI doesn't validate Celery task registration) → backlog.\n"
            "- infrastructure-reviewer#0 (crit, containers-as-root) → backlog (legit project-level item).\n"
            "- infrastructure-reviewer#1/#2/#3 (major, missing .dockerignore / dev-deps in image) → backlog.\n"
            "- deploy-reviewer#3/#4 (minor) → backlog.\n\n"
            "### In-scope finding triage — FIXED\n\n"
            "| ID | Validator | Finding | Fix |\n|---|---|---|---|\n"
            "| code-reviewer#0 | code-reviewer | cached client | per-call client |\n"
        )
        eng = mkeng(tmp, {
            f"deploy-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("minor"), finding("major")]),
            f"infrastructure-reviewer-iter-1-{TS1}.json": ("changes_required",
                                                          [finding("critical"), finding("major"), finding("major"), finding("major")]),
            f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("critical")]),
        }, log=cf_log)
        r = check_findings_dispositioned(eng)
        results.append(check("section-level OUT-OF-SCOPE ruling, `#1/#2/#3` shorthand, FIXED table -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {f"infrastructure-reviewer-iter-1-{TS1}.json": ("changes_required",
                                                                         [finding("major")] * 5)},
                    log="### Ruling\nOut of scope per criteria.md:\n- infrastructure-reviewer#1/#2/#3 → backlog.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("shorthand covers only the listed indices (#0, #4 stay open) -> fail",
                             r["status"] == "fail" and "infrastructure-reviewer#0" in r["detail"]
                             and "infrastructure-reviewer#4" in r["detail"] and "#2 (" not in r["detail"],
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {f"security-auditor-iter-1-{TS1}.json": ("approved", [finding("medium")])},
                    scope_sync="## Finding waiver 2026-10-09\nsecurity-auditor#0 waived by the user: log redaction ships next.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("waiver in scope-sync.md -> pass", r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("critical", id="CR-7", status="FIXED")])})
        r = check_findings_dispositioned(eng)
        results.append(check("status FIXED on the finding -> pass", r["status"] == "pass", f"got {r['status']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [finding("high", id="CR-7")])},
                    log="### code-reviewer\n- CR-7 false positive: the path is unreachable.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("own id ruled false positive -> pass", r["status"] == "pass", f"got {r['status']}"))

        print("\nD. outside the check's scope")
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved_with_suggestions",
                                                               [finding("low"), finding("info"), finding("nit"), finding("minor")])})
        r = check_findings_dispositioned(eng)
        results.append(check("low/info/nit/minor only -> pass", r["status"] == "pass", f"got {r['status']}"))
        eng = mkeng(tmp, {
            f"peer-opus-iter-1-{TS1}.json": ("rework_required", [finding("critical")]),
            f"codex-blind-iter-1-{TS1}.json": ("rework_required", [finding("major")]),
            f"code-reviewer-iter-1-preliminary-{TS1}.json": ("changes_required", [finding("critical")]),
            f"code-reviewer-iter-1-{TS2}.json": ("approved", []),
        })
        r = check_findings_dispositioned(eng)
        results.append(check("consilium roles and preliminary files ignored -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {
            f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("critical")]),
            f"code-reviewer-iter-2-{TS2}.json": ("approved", []),
        }, iteration=2)
        r = check_findings_dispositioned(eng)
        results.append(check("older iteration ignored -> pass", r["status"] == "pass", f"got {r['status']}"))
        eng = mkeng(tmp, {
            f"code-reviewer-iter-1-{TS1}.json": ("approved", []),
            f"code-reviewer-iter-2-{TS2}.json": ("approved", [finding("medium")]),
        })
        r = check_findings_dispositioned(eng)
        results.append(check("no iteration file -> highest iteration is judged -> fail",
                             r["status"] == "fail", f"got {r['status']}"))

        print("\nE. not yet")
        eng = mkeng(tmp, {})
        r = check_findings_dispositioned(eng)
        results.append(check("empty validation-outputs/ -> skip", r["status"] == "skip", f"got {r['status']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("approved", [])}, iteration=2)
        r = check_findings_dispositioned(eng)
        results.append(check("no outputs for the current iteration -> skip", r["status"] == "skip", f"got {r['status']}"))

        print("\nF. Codex review 2026-10-09: rulings bind to lines, not to whole sections")
        two = {f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("major", "a"), finding("major", "b")])}
        eng = mkeng(tmp, two, iteration=1,
                    log="### code-reviewer\n- code-reviewer#0: FIXED in abc123\n- code-reviewer#1: deferred to backlog\n")
        r = check_findings_dispositioned(eng)
        results.append(check("#0 FIXED does not carry #1 'deferred to backlog' in the same section -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("major")])}, iteration=1,
                    log="### code-reviewer\n- code-reviewer#0: not fixed yet\n")
        r = check_findings_dispositioned(eng)
        results.append(check("'not fixed' is not a disposition -> fail", r["status"] == "fail", f"got {r['status']}"))
        eng = mkeng(tmp, two, iteration=1,
                    log="### code-reviewer\nMost findings were fixed in abc123.\n- code-reviewer#0 ok\n- code-reviewer#1 deferred to backlog\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a FIXED remark does not let a backlog line inherit (#1 open) -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, two, iteration=1,
                    log="### Ruling\nOut of scope per criteria.md:\n- code-reviewer#0 -> backlog\n- code-reviewer#1 still open\n")
        r = check_findings_dispositioned(eng)
        results.append(check("'still open' never inherits a section ruling (#1 open, #0 ruled) -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", "")
                             and "code-reviewer#0 " not in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))

        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("changes_required",
                    [finding("major", "a", id="sec_01"), finding("major", "b")])}, iteration=1,
                    log="### code-reviewer\n- sec_01: FIXED in abc123\n- code-reviewer#1 see notes\n")
        r = check_findings_dispositioned(eng)
        results.append(check("an own-id FIXED line is not a section ruling (#1 open, sec_01 closed) -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", "")
                             and "code-reviewer#0 " not in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, two, iteration=1,
                    log="### code-reviewer\nFixed:\n- code-reviewer#0\nNot fixed:\n- code-reviewer#1\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a negated label line ends the ruling above it (#1 open) -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", "")
                             and "code-reviewer#0 " not in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))

        print("\nH. dispositions bind to their iteration (engagement-protocol: rework goes under `## Iteration N`)")
        out2 = {f"code-reviewer-iter-2-{TS1}.json": ("changes_required", [finding("major", "new #0 in iter 2")])}
        eng = mkeng(tmp, out2, iteration=2,
                    log="## Iteration 1\n### code-reviewer\n- code-reviewer#0: FIXED in abc123\n\n"
                        "## Iteration 2\n### code-reviewer\nverdict: changes_required\n")
        r = check_findings_dispositioned(eng)
        results.append(check("an iter-1 `#0: FIXED` does not cover iter-2's #0 -> fail", r["status"] == "fail",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2, iteration=2,
                    log="## Iteration 1\n- code-reviewer#0: FIXED in abc123\n\n## Iteration 2\n- code-reviewer#0: FIXED in def456\n")
        r = check_findings_dispositioned(eng)
        results.append(check("...the iter-2 section's own `#0: FIXED` does -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2, iteration=2, log="### code-reviewer\n- code-reviewer#0: FIXED in def456\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a log with no iteration headings (rewritten by the engine) counts as current -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nI. review round 1 (2026-10-10)")
        for label in ("Open:", "Remaining:", "Pending:"):
            eng = mkeng(tmp, two, iteration=1,
                        log=f"### code-reviewer\nFixed:\n- code-reviewer#0\n{label}\n- code-reviewer#1 race condition\n")
            r = check_findings_dispositioned(eng)
            results.append(check(f"a neutral label '{label}' ends the 'Fixed:' ruling (#1 open) -> fail",
                                 r["status"] == "fail" and "code-reviewer#1" in r.get("detail", "")
                                 and "code-reviewer#0 " not in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, two, iteration=1,
                    log="### code-reviewer\n- code-reviewer#0: FIXED; code-reviewer#1: deferred to backlog\n")
        r = check_findings_dispositioned(eng)
        results.append(check("one line, two clauses: FIXED does not cover the deferred #1 -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, two, iteration=1, log="### code-reviewer\n- code-reviewer#0, #1: fixed in abc123\n")
        r = check_findings_dispositioned(eng)
        results.append(check("...but one clause listing both ids still covers both -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))

        # a real-world shape: a wrapped continuation line ending in "-> backlog."
        # inside an OUT-OF-SCOPE ruling must not end the ruling (it did in a first cut of this fix)
        eng = mkeng(tmp, {f"infrastructure-reviewer-iter-1-{TS1}.json": ("changes_required",
                                                                       [finding("major"), finding("major"), finding("major")])},
                    iteration=1,
                    log="### Out-of-plan validators\n\n**Adjudication: OUT-OF-SCOPE.** Every finding is pre-existing.\n\n"
                        "Itemised:\n- infrastructure-reviewer#0 (major) — in-scope slice delivered in Phase 7\n"
                        "  docs; project-wide runbook → backlog.\n- infrastructure-reviewer#1/#2 (major) → backlog.\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a wrapped continuation line ending in '→ backlog.' keeps the scope ruling -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        import os
        out2 = {f"code-reviewer-iter-2-{TS2}.json": ("changes_required", [finding("major", "new #0 in iter 2")])}
        eng = mkeng(tmp, out2, iteration=2, log="### code-reviewer\n- code-reviewer#0: FIXED in abc123\n")
        old = os.path.getmtime(eng / "validation-outputs" / f"code-reviewer-iter-2-{TS2}.json") - 3600
        os.utime(eng / "validation-log.md", (old, old))
        r = check_findings_dispositioned(eng)
        results.append(check("iter 2, log without iteration headings and older than the outputs -> its index ids "
                             "do not count -> fail", r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2, iteration=2, scope_sync="## Waivers\n- code-reviewer#0: waived by director\n")
        os.utime(eng / "scope-sync.md", (old, old))
        r = check_findings_dispositioned(eng)
        results.append(check("...same for an older scope-sync.md waiver citing an index id -> fail", r["status"] == "fail",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2, iteration=2, log="### code-reviewer\n- code-reviewer#0: FIXED in def456\n")
        r = check_findings_dispositioned(eng)
        results.append(check("...a log written after the outputs (engine rewrite + lead append) counts -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        eng = mkeng(tmp, {f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("major", "x", id="2")])},
                    iteration=1, log="### code-reviewer\n- code-reviewer#3: fixed in commit 2\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a bare numeric own id '2' is not matched by any digit in the log -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))

        eng = mkeng(tmp, out2, iteration=2,
                    log="## Iteration 2\n### Iteration 1 recap\nsee above\n### code-reviewer\n- code-reviewer#0: FIXED in x\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a '### Iteration 1 recap' heading inside iteration 2 is not a boundary -> pass",
                             r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

        print("\nK. review round 2 (2026-10-10)")
        one = {f"code-reviewer-iter-1-{TS1}.json": ("changes_required", [finding("major")])}
        for phrase in ("confirmed, to be fixed in a follow-up", "will be resolved later", "partially fixed",
                       "should be fixed next round", "has not been fixed", "isn't fixed", "wasn't resolved",
                       "not fully fixed", "not a false positive"):
            eng = mkeng(tmp, one, iteration=1, log=f"### code-reviewer\n- code-reviewer#0: {phrase}\n")
            r = check_findings_dispositioned(eng)
            results.append(check(f"'{phrase}' is not a disposition -> fail", r["status"] == "fail",
                                 f"got {r['status']}: {r['detail']}"))
        sk = {f"skeptic-iter-1-{TS1}.json": ("approved_with_suggestions", [finding("major"), finding("major")])}
        eng = mkeng(tmp, sk, iteration=1,
                    log="### skeptic\nverdict: approved_with_suggestions\nadversarial-verify: 2 confirmed / 1 refuted of 3\n"
                        "summary: two claims unverified\n- skeptic#1: confirmed, needs product decision\n")
        r = check_findings_dispositioned(eng)
        results.append(check("the engine's 'adversarial-verify: ... refuted ...' line is not a ruling -> fail",
                             r["status"] == "fail" and "skeptic#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, one, iteration=1,
                    log="### code-reviewer\nIteration-1 findings were all fixed in 4c1d2e.\n\n- code-reviewer#0 see notes\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a prose remark is not a ruling for the ids below it -> fail", r["status"] == "fail",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, two, iteration=1, log="### code-reviewer\n- code-reviewer#0 fixed, code-reviewer#1 needs a migration\n")
        r = check_findings_dispositioned(eng)
        results.append(check("comma-joined clauses about different ids are judged apart (#1 open) -> fail",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))

        import os as _os
        two_v = {f"code-reviewer-iter-2-{TS1}.json": ("changes_required", [finding("major", "cr")]),
                 f"skeptic-iter-2-{TS1}.json": ("changes_required", [finding("major", "sk")])}
        eng = mkeng(tmp, two_v, iteration=2,
                    log="### code-reviewer\n- code-reviewer#0: FIXED in a1\n### skeptic\n- skeptic#0: FIXED in a2\n")
        now = _os.path.getmtime(eng / "validation-log.md")
        for f, t in ((f"code-reviewer-iter-2-{TS1}.json", now - 600), (f"skeptic-iter-2-{TS1}.json", now + 600)):
            _os.utime(eng / "validation-outputs" / f, (t, t))
        r = check_findings_dispositioned(eng)
        results.append(check("staleness is per validator: only the validator re-run after the log loses its index ids",
                             r["status"] == "fail" and "skeptic#0" in r.get("detail", "")
                             and "code-reviewer#0" not in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))

        out2b = {f"code-reviewer-iter-2-{TS2}.json": ("changes_required", [finding("major")])}
        for head in ("## **Iteration 2**", "## Iteration 2 rework", "## Iteration 2 — 2026-10-10"):
            eng = mkeng(tmp, out2b, iteration=2,
                        log=f"## Iteration 1\n- code-reviewer#0: FIXED old\n\n{head}\n- code-reviewer#0: FIXED in b2\n")
            r = check_findings_dispositioned(eng)
            results.append(check(f"'{head}' is the iteration-2 boundary -> pass", r["status"] == "pass",
                                 f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2b, iteration=2,
                    log="## Iteration 2\n### Iteration 1 — recap\nold stuff\n### code-reviewer\n- code-reviewer#0: FIXED in b2\n")
        r = check_findings_dispositioned(eng)
        results.append(check("'### Iteration 1 — recap' inside iteration 2 is not a boundary -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, one, iteration=1, log="### code-reviewer\n- Code-reviewer#0: fixed in c3\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a capitalised validator name still names the id -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2b, iteration=2, log=chr(0xFEFF) + "## Iteration 2\n- code-reviewer#0: FIXED in b2\n")
        r = check_findings_dispositioned(eng)
        results.append(check("a BOM before the first heading does not hide it -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))

        print("\nL. Codex review 2026-10-14")
        for phrase in ("could be resolved by changing X", "may be fixed", "might be addressed", "can be fixed later"):
            eng = mkeng(tmp, one, iteration=1, log=f"### code-reviewer\n- code-reviewer#0 {phrase}\n")
            r = check_findings_dispositioned(eng)
            results.append(check(f"modal '{phrase}' is not a disposition -> fail", r["status"] == "fail",
                                 f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2b, iteration=2, log="## Iteration 2\n- code-reviewer#0: FIXED in b2\n")
        t = _os.path.getmtime(eng / "validation-log.md") + 900
        _os.utime(eng / "validation-outputs" / f"code-reviewer-iter-2-{TS2}.json", (t, t))
        r = check_findings_dispositioned(eng)
        results.append(check("a headed log is stale too when its validator re-ran 15 min after it -> fail",
                             r["status"] == "fail", f"got {r['status']}: {r['detail']}"))
        eng = mkeng(tmp, out2b, iteration=2, log="## Iteration 2\n- code-reviewer#0: FIXED in b2\n")
        t = _os.path.getmtime(eng / "validation-log.md") + 5
        _os.utime(eng / "validation-outputs" / f"code-reviewer-iter-2-{TS2}.json", (t, t))
        r = check_findings_dispositioned(eng)
        results.append(check("...but seconds apart (a copy or checkout) is not a re-run -> pass", r["status"] == "pass",
                             f"got {r['status']}: {r['detail']}"))

        print("\nG. Codex review 2026-10-09: the reviewer's native criticalIssues / suggestions shape")
        eng = Path(tempfile.mkdtemp(dir=tmp)) / "engagement"
        (eng / "validation-outputs").mkdir(parents=True)
        (eng / "iteration").write_text("1", encoding="utf-8")
        (eng / "validation-outputs" / f"code-reviewer-iter-1-{TS1}.json").write_text(json.dumps({
            "status": "approved_with_suggestions", "findings": [], "criticalIssues": [],
            "suggestions": [{"severity": "minor", "description": "nit"},
                            {"severity": "major", "description": "unchecked error path"}]}), encoding="utf-8")
        r = check_findings_dispositioned(eng)
        results.append(check("major in `suggestions` with empty `findings` -> fail, named #1",
                             r["status"] == "fail" and "code-reviewer#1" in r.get("detail", ""), f"got {r['status']}: {r['detail']}"))
        (eng / "validation-log.md").write_text("### code-reviewer\n- code-reviewer#1: FIXED in def456\n", encoding="utf-8")
        r = check_findings_dispositioned(eng)
        results.append(check("...and its index id disposes it -> pass", r["status"] == "pass", f"got {r['status']}: {r['detail']}"))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_findings_dispositioned():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
