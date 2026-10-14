#!/usr/bin/env python3
"""Regression guard: load-bearing clauses in agent and skill prompts survive SkillOpt edits.

Cheap regex checks that required clauses are still present. Our golden gate judges an edit's behaviour and the
diff guard checks WHICH files changed, but nothing checked WHAT a promoted edit removed. A
bounded edit that drops "judge-only" from a director or the adjudication markers from a
manager would pass both. This list is short on purpose: only clauses other parts of the
system depend on. Patterns are anchored to the clause itself (review 2026-10-10: `suggestions`
used to match inside `approved_with_suggestions`, so deleting the real key passed).

The SkillOpt diff guard runs this file and reads one `  [FAIL] <path>: ...` line per broken
invariant; a FAIL on a file the cycle wrote is a violation (rollback), a FAIL elsewhere is a
pre-existing break it reports but does not blame on the cycle.

  A. every invariant holds on the live corpus (one FAIL line per violation, path first)
  B. the checker catches a removed clause, including the anchored ones (mutated temp copy)
  C. skillopt-workflow's diff guard runs this test, scoped to the files the cycle wrote
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2]
WS = r"\s+"
I = re.IGNORECASE

# (glob under ~/.claude, why it is load-bearing, regex, flags); patterns may span lines
INVARIANTS = [
    ("agents/**/*-manager.md", "manager adjudication markers (acceptance-protocol, precheck)", r"\bSUSTAINED\b", 0),
    ("agents/**/*-director.md", "directors judge, Codex authors", r"judge-only", I),
    ("agents/**/*-director.md", "cross-family proposer", r"cross-family", I),
    ("agents/**/dev-director.md", "rejection buffer read before proposing", r"rejection" + WS + "buffer", I),
    ("agents/**/design-director.md", "rejection buffer read before proposing", r"rejection" + WS + "buffer", I),
    ("agents/**/marketing-director.md", "rejection buffer read before proposing", r"rejection" + WS + "buffer", I),
    ("agents/**/harness-director.md", "Zone-2 engine stays frozen", r"\bFROZEN\b", 0),
    ("agents/**/harness-director.md", "byte-identity when a flag is off", r"byte-identi", I),
    ("agents/**/*-lead.md", "leads plan only; the engine dispatches", r"You" + WS + "do" + WS + "not" + WS + "dispatch", 0),
    ("agents/**/code-reviewer.md", "output key read by precheck findings-dispositioned", r'"criticalIssues"\s*:', 0),
    ("agents/**/code-reviewer.md", "output key read by precheck findings-dispositioned", r'"suggestions"\s*:', 0),
    ("skills/engagement-contract/SKILL.md", "specialist contract", r"Evidence" + WS + "before" + WS + "claims", I),
    ("skills/engagement-contract/SKILL.md", "specialist contract", r"\bNEEDS_CONTEXT\b", 0),
    ("skills/engagement-contract/SKILL.md", "specialist contract", r"rule-do-not-stall", I),
    ("skills/acceptance-protocol/SKILL.md", "adjudication vocabulary", r"\bOVERRULED\b", 0),
    ("skills/acceptance-protocol/SKILL.md", "adjudication vocabulary", r"\bFALSE_POSITIVE\b", 0),
    ("skills/acceptance-protocol/SKILL.md", "managers judge, do not sweep-rerun",
     r"(?:do" + WS + "not|don't|never)" + WS + "re-run" + WS + "validators", I),
]


def violations(root: Path) -> list[str]:
    out = []
    for glob, why, pattern, flags in INVARIANTS:
        files = sorted(root.glob(glob))
        if not files:
            out.append(f"{glob}: no file matches ({why})")
        for f in files:
            if not re.search(pattern, f.read_text(encoding="utf-8", errors="replace"), flags):
                out.append(f"{f.relative_to(root).as_posix()}: lost /{pattern}/ ({why})")
    return out


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -- {detail}"))
    return ok


def copy_corpus(root: Path):
    for glob, *_ in INVARIANTS:
        for f in CLAUDE.glob(glob):
            dst = root / f.relative_to(CLAUDE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(f.read_bytes())


def main() -> int:
    results = []
    live = violations(CLAUDE)
    for v in live:  # one line per violation, path first: the diff guard reads these
        print(f"  [FAIL] {v}")
    results.append(not live)
    if not live:
        print(f"  [PASS] A all {len(INVARIANTS)} invariants hold on the live corpus")

    mutations = {
        "agents/**/dev-director.md": (r"(?i)judge-only", "judge"),
        "agents/**/code-reviewer.md": (r'"suggestions"\s*:', '"advice":'),
        "agents/**/dev-manager.md": (r"SUSTAINED", "upheld"),
        "skills/acceptance-protocol/SKILL.md": (r"(?i)(do not|don't) re-run validators", "MUST re-run validators"),
    }
    for rel, (pat, repl) in mutations.items():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_corpus(root)
            target = next(root.glob(rel))  # agents/ may be flat or grouped by role
            rel = target.relative_to(root).as_posix()
            target.write_text(re.sub(pat, repl, target.read_text(encoding="utf-8")), encoding="utf-8")
            v = violations(root)
            results.append(check(f"B a mutated {rel} is caught", any(x.startswith(rel + ":") for x in v), str(v)))

    wf = (CLAUDE / "workflows" / "skillopt-workflow.js").read_text(encoding="utf-8")
    guard = wf[wf.find("DIFF GUARD"):wf.find("label: 'diff-guard'")]
    step6 = guard[guard.find("PROMPT INVARIANTS"):] if "PROMPT INVARIANTS" in guard else ""
    results.append(check("C the diff guard runs this test, counts only FAILs on files the cycle wrote, and treats "
                         "a crash as inconclusive",
                         "test_prompt_invariants_regress.py" in step6 and "prompt-invariant: " in step6
                         and "declared target" in step6 and "inconclusive" in step6
                         # Codex review 2026-10-14: "inconclusive" must reach the workflow as ran:false
                         # (publish blocked, no rollback); a guard that reports ran:true, clean:true
                         # after the checker failed to run let a stripped clause through
                         and "ran:false" in step6, step6[:400]))

    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


def test_prompt_invariants():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
