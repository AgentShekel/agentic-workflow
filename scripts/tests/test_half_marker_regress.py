#!/usr/bin/env python3
"""Regression guard — the partial-resolved half-markers, across BOTH readiness checkers.

A signal can be mixed: one half lives in a skill/agent (SkillOpt's layer), the other in a
script or the engine (HarnessOpt's layer). When one loop closes its own half it writes a
half-marker, and the contract is that ONLY that loop may then stop counting the signal:

    resolved:                  both loops close (the whole thing is fixed)
    resolved (SKILL half):     SkillOpt closes;  HarnessOpt keeps counting
    resolved (SCRIPT half):    HarnessOpt closes; SkillOpt keeps counting
    resolved (ENGINE ...):     HarnessOpt closes; SkillOpt keeps counting
    adjudicated:               NEITHER closes (judged unactionable, nothing was fixed)

This only works because the two regexes disagree, in opposite directions. That is fragile in
a specific way: each was tuned against the marker the OTHER loop writes, so a new marker can
be exactly inverted and nothing complains. That is what happened when `resolved (SKILL half):`
was introduced — the broad harness matcher closed it (dropping a still-open script half out of
its cluster) while the narrow skillopt matcher did not (leaving the skill signal live to
re-fire its cluster every session). Both halves wrong, in opposite directions, silently.

Nothing else in the system will catch this: a half-marker that both loops ignore looks like an
always-due trigger, and one both loops honour looks like a closed signal. Neither raises.

Run standalone or under pytest:
  python test_half_marker_regress.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


skillopt = _load("_skillopt_ready_hm", "skillopt-ready.py")
harness = _load("_harness_ready_hm", "harness-ready.py")

# (marker line, skillopt should close, harness should close)
MARKERS = [
    ("resolved: 2026-09-04 — closed by skillopt cycle 20260904T101500Z", True, True),
    ("resolved (SKILL half): 2026-09-04 — rule added to validation-pipeline", True, False),
    ("resolved (SCRIPT half): 2026-08-31 — red->green in scripts/metrics.py", False, True),
    ("resolved (ENGINE root, flag OFF byte-identical): 2026-08-31", False, True),
    ("resolved (PREFLIGHT half): 2026-08-31 — compose probe fixed", False, True),
    # Not a closure on either side: a cycle looked and produced nothing.
    ("adjudicated: 2026-09-04 | skillopt cycle | no-edit. target is a script.", False, False),
    # Near-misses that must not be read as closures.
    ("resolution: pending", False, False),
    ("resolvedish: nonsense", False, False),
]


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def main() -> int:
    results = []

    print("A. each loop closes on its own marker and on a full resolve, nothing else")
    for line, want_s, want_h in MARKERS:
        got_s = bool(skillopt.RESOLVED_RE.search(line))
        got_h = bool(harness.RESOLVED_RE.search(line))
        label = line.split("—")[0].split("|")[0].strip()[:46]
        results.append(check(f"skillopt {'closes' if want_s else 'keeps '} {label!r}",
                             got_s == want_s, f"got {got_s}, want {want_s}"))
        results.append(check(f"harness  {'closes' if want_h else 'keeps '} {label!r}",
                             got_h == want_h, f"got {got_h}, want {want_h}"))

    print("\nB. a half-marker is never honoured by BOTH loops")
    both = [line for line, s, h in MARKERS
            if "half" in line.lower() or "ENGINE" in line
            if bool(skillopt.RESOLVED_RE.search(line)) and bool(harness.RESOLVED_RE.search(line))]
    results.append(check("no half-marker closes on both sides", not both, f"got {both}"))

    print("\nC. a half-marker is never ignored by BOTH loops")
    neither = [line for line, s, h in MARKERS
               if "half" in line.lower() or "ENGINE" in line
               if not skillopt.RESOLVED_RE.search(line) and not harness.RESOLVED_RE.search(line)]
    results.append(check("every half-marker closes exactly one side", not neither, f"got {neither}"))

    print("\nD. the markers survive inside a real signal block")
    block = (
        "### SIGNAL | domain: dev | engagement: alpha\n"
        "Failure class: spec-code-drift\n"
        "Traced to: skills/validation-pipeline/SKILL.md vs scripts/metrics.py\n"
        "Evidence: engagement/acceptance-log.md\n"
        "resolved (SKILL half): 2026-09-04 — rule added\n"
    )
    sigs = skillopt.parse_signals(block)
    results.append(check("skillopt parses the block and marks it resolved",
                         len(sigs) == 1 and sigs[0]["resolved"] is True,
                         f"got {sigs}"))
    hsigs = harness.parse_signals(block)
    results.append(check("harness parses the same block and keeps it OPEN",
                         len(hsigs) == 1 and hsigs[0]["resolved"] is False,
                         f"got {hsigs}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_half_marker_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
