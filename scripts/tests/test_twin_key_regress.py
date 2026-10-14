#!/usr/bin/env python3
"""Regression guard — the cross-channel twin key in skillopt-ready.py.

Channel B counts only ORPHAN reflections: a reflection whose issue already sits in the log as a
SIGNAL is not counted twice. Until 2026-10-09 "the same issue" meant (engagement, rule_* token),
so one `rule_missing` log signal hid EVERY `rule_missing` reflection of its engagement, whatever
it was about: a reflection with no log signal of its own was invisible whenever an unrelated
signal from the same engagement carried the token. The bare-token class_key fallback leaked the same way.

Pinned here (live subprocess, --json):

  A. TARGET SPLITS TWINS     a log signal hides a same-engagement, same-token reflection only
                             when the reflection's target is one the signal traces to.
  B. SAME TARGET STILL TWIN  the signal the reflection was promoted into still hides it.
  C. ANY TRACED TARGET       a log signal traced to "engine + skill" still hides the reflection
                             that named the engine (reflections name one target, signals often
                             name two).
  D. REKEY KEEPS TWINS       a triage rekey changes the cluster class, not the issue identity: the
                             reflection, written with the original token, stays hidden.
  E. DESCRIPTIVE FALLBACK    a non-token class (e.g. `gate-false-positive`) still twins on
                             (engagement, class) alone, as before.
  F. OTHER ENGAGEMENT        nothing twins across engagements.

Run standalone or under pytest:
  python test_twin_key_regress.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

LOG = """\
# Skill evolution log

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-split
Failure class: rule_missing (validator findings deferred into handoff section 11)
Traced to: workflows/engagement-workflow.js + skills/validation-pipeline

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-engine
Failure class: rule_missing (validate phase does not block handoff)
Traced to: workflows/engagement-workflow.js (validate phase) + skills/validation-pipeline

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-rekey
Failure class: rule_missing (validator findings deferred)
Traced to: skills/validation-pipeline
rekey: 2026-10-09 - as validator-finding-deferred-without-waiver (rule_wrong). Re-keyed.

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-descr
Failure class: gate-false-positive (size-detect diffs vs the bootstrap commit)
Traced to: scripts/handoff-precheck.py
"""

# (engagement dir, reflection target, class)
REFLECTIONS = [
    ("eng-split", "skill: code-reviewing", "rule_missing"),        # A: other target -> orphan
    ("eng-split", "skill: validation-pipeline", "rule_missing"),   # B: same target -> twin
    ("eng-engine", "script: workflows/engagement-workflow.js", "rule_missing"),  # C -> twin
    ("eng-rekey", "skill: validation-pipeline", "rule_missing"),   # D -> twin
    ("eng-descr", "skill: validation-pipeline", "gate-false-positive"),  # E -> twin
    ("eng-other", "skill: validation-pipeline", "rule_missing"),   # F -> orphan
]


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def run(root: Path) -> dict | None:
    log = root / "skill-evolution-log.md"
    log.write_text(LOG, encoding="utf-8")
    by_eng: dict = {}
    for eng, target, cls in REFLECTIONS:
        by_eng.setdefault(eng, []).append(
            f"- target: {target}\n  class: {cls}\n  observation: x\n  evidence: y\n")
    for eng, bullets in by_eng.items():
        d = root / eng / "engagement"
        d.mkdir(parents=True)
        (d / "criteria.md").write_text("---\ndomain: dev\nsize: M\n---\n", encoding="utf-8")
        (d / "engagement-reflections.md").write_text(
            f"## Reflection — {eng} — 2026-10-06 — verdict: REJECT\n\n" + "\n".join(bullets),
            encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "skillopt-ready.py"), "--json", "--log", str(log),
         "--reflection-root", str(root), "--reflection-window-days", "0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    try:
        return json.loads(proc.stdout)
    except Exception:  # noqa: BLE001
        print(f"  no JSON: stdout={proc.stdout[:300]!r} stderr={proc.stderr[:300]!r}")
        return None


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as td:
        out = run(Path(td))
    results.append(check("checker emitted JSON", out is not None))
    out = out or {}
    visible = {(eng, key) for key, v in (out.get("reflection_buckets") or {}).items()
               for eng in v.get("engagements", [])}

    def shown(eng: str, target: str, cls: str) -> bool:
        return (eng, f"dev/{target}/{cls}") in visible

    print("A. a different target is not a twin")
    results.append(check("eng-split code-reviewing/rule_missing reflection is an orphan",
                         shown("eng-split", "code-reviewing", "rule_missing"), f"visible={visible}"))
    print("B. the promoted target is still a twin")
    results.append(check("eng-split validation-pipeline/rule_missing stays hidden",
                         not shown("eng-split", "validation-pipeline", "rule_missing"),
                         f"visible={visible}"))
    print("C. any traced target of the signal counts")
    results.append(check("eng-engine engine reflection stays hidden",
                         not any(e == "eng-engine" for e, _ in visible), f"visible={visible}"))
    print("D. a rekey does not orphan the reflection it came from")
    results.append(check("eng-rekey reflection stays hidden",
                         not any(e == "eng-rekey" for e, _ in visible), f"visible={visible}"))
    print("E. descriptive classes still twin on (engagement, class)")
    results.append(check("eng-descr gate-false-positive reflection stays hidden",
                         not any(e == "eng-descr" for e, _ in visible), f"visible={visible}"))
    print("F. no twin across engagements")
    results.append(check("eng-other reflection is an orphan",
                         shown("eng-other", "validation-pipeline", "rule_missing"),
                         f"visible={visible}"))
    results.append(check("exactly two orphan reflections overall",
                         out.get("reflection_count") == 2,
                         f"reflection_count={out.get('reflection_count')}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_twin_key_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
