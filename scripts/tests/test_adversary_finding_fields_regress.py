#!/usr/bin/env python3
"""Regression guard — scoped-reviewer findings reach the consilium synthesizer.

On an L-tier run, consilium-summary.md listed the
sonnet-scoped findings as blank "**MINOR** — " lines. The scoped prompts show
`"findings": [...]` with no per-item schema, so sonnet wrote its own keys
(criterion / producer_claim / plain_criteria_wording / actual_state / decision,
no severity). adversary_lg's Finding model then dumped the canonical
issue / evidence_path / fix_hint as "" and consilium-synth had nothing to show.
The same coercion turned a scoped reviewer's "high" into "minor".

  A. SONNET SHAPE        the incident's key set: issue <- actual_state, own keys kept.
  B. HAIKU SHAPE         finding / detail / location: issue <- finding,
                         evidence_path <- location.
  C. CANONICAL UNTOUCHED a peer-opus finding passes through unchanged.
  D. SEVERITY SCALE      high -> major, blocker -> critical, medium / moderate /
                         low / junk -> minor (validator_lg's collapse, 3 levels).
  E. BARE STRING         a finding that is just a string becomes its issue text
                         instead of failing Pass-2 validation.
  F. END TO END          run_two_pass("sonnet-scoped") with a stand-in invoker
                         returning the incident shape, then the real
                         consilium-synth.py: no blank finding headers, the
                         actual_state text is in consilium-summary.md.

Run standalone (harness gate) or under pytest:
  python test_adversary_finding_fields_regress.py
  python test_adversary_finding_fields_regress.py --script /tmp/patched-adversary.py
  pytest test_adversary_finding_fields_regress.py -q
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "adversary_lg.py"
SYNTH = DEFAULT_SCRIPT.parent / "consilium-synth.py"
_SCRIPT_OVERRIDE: Path | None = None

# The key set a sonnet-scoped reviewer emits; values are illustrative.
SONNET_FINDING = {
    "id": "F-1",
    "criterion": "crit-3",
    "producer_claim": "partially met",
    "plain_criteria_wording": "configuration read from one place",
    "actual_state": "Two modules read the environment directly instead of the config object",
    "decision": "criteria not met",
}
# The key set a haiku-scoped reviewer emits in its preliminary pass.
HAIKU_FINDING = {
    "finding": "README verification gap",
    "severity": "moderate",
    "detail": "executor did not run the documented commands",
    "location": "T4.md, L7-9",
}
PEER_FINDING = {
    "severity": "major",
    "issue": "Parser regex rejects spelled-out units",
    "evidence_path": "src/app/parser.py:49",
    "fix_hint": "Extend the alternation with the spelled-out forms",
}

# Runs inside the adversary venv (the module needs langgraph at import).
DRIVER = r"""
import importlib.util, json, sys
from pathlib import Path
mode, script, arg = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("adversary_under_test", script)
m = importlib.util.module_from_spec(spec)
sys.modules["adversary_under_test"] = m
spec.loader.exec_module(m)

if mode == "validate":
    findings = json.loads(Path(arg).read_text(encoding="utf-8"))
    out = m.Pass2Output.model_validate({"verdict": "rework_required", "findings": findings})
    print(json.dumps([f.model_dump() for f in out.findings], ensure_ascii=False))
else:
    eng = Path(arg)
    findings = json.loads((eng / "_findings.json").read_text(encoding="utf-8"))

    class Stand(m.Invoker):
        name = "stand-in"
        def invoke(self, role, config, prompt):
            if "PASS 1" in prompt:
                body = {"preliminary_view": "v", "preliminary_findings": [],
                        "reviewer_role": role, "iteration": 1, "pass": 1}
            else:
                body = {"verdict": "rework_required", "reviewer_role": role,
                        "iteration": 1, "pass": 2, "findings": findings, "summary": "s"}
            return 0, json.dumps(body, ensure_ascii=False), "", 0.0

    res = m.run_two_pass("sonnet-scoped", eng, 1, Stand())
    print(json.dumps(res))
"""


def script_path() -> Path:
    return _SCRIPT_OVERRIDE or DEFAULT_SCRIPT


class _Skip(unittest.SkipTest):
    """Missing optional prerequisite: SKIP loudly, never FAIL."""


def venv_python() -> str:
    for rel in ("Scripts/python.exe", "bin/python"):
        cand = DEFAULT_SCRIPT.parent / ".venv-adversary-lg" / rel
        if cand.exists():
            return str(cand)
    raise _Skip("adversary venv absent — build scripts/.venv-adversary-lg from "
                "scripts/requirements-adversary-lg.txt")


def _drive(mode: str, arg: str):
    # A throwaway copy of the script cannot see lib/ next to itself.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        p for p in (str(DEFAULT_SCRIPT.parent), os.environ.get("PYTHONPATH", "")) if p)}
    r = subprocess.run([venv_python(), "-c", DRIVER, mode, str(script_path()), arg],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, stdin=subprocess.DEVNULL, check=False, timeout=120)
    assert r.returncode == 0, f"driver rc={r.returncode}\n{r.stderr[-1500:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _validate(findings: list) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "findings.json"
        f.write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
        return _drive("validate", str(f))


# ------------------------------------------------------------------ A-E. model

def test_sonnet_shape_maps_to_issue():
    (got,) = _validate([SONNET_FINDING])
    assert got["issue"] == SONNET_FINDING["actual_state"], f"issue={got['issue']!r}"
    for k, v in SONNET_FINDING.items():
        assert got.get(k) == v, f"reviewer key {k!r} must survive, got {got.get(k)!r}"


def test_haiku_shape_maps_issue_and_evidence():
    (got,) = _validate([HAIKU_FINDING])
    assert got["issue"] == HAIKU_FINDING["finding"], f"issue={got['issue']!r}"
    assert got["evidence_path"] == HAIKU_FINDING["location"], got["evidence_path"]
    assert got["severity"] == "minor", got["severity"]


def test_canonical_finding_untouched():
    (got,) = _validate([PEER_FINDING])
    assert got == PEER_FINDING, got


def test_severity_scale():
    cases = {"high": "major", "HIGH": "major", "blocker": "critical", "Critical": "critical",
             "important": "major", "medium": "minor", "moderate": "minor", "low": "minor",
             "minor": "minor", "whatever": "minor"}
    got = _validate([{"severity": s, "issue": "x"} for s in cases])
    wrong = {s: g["severity"] for (s, want), g in zip(cases.items(), got) if g["severity"] != want}
    assert not wrong, f"severity mis-mapped: {wrong}"


def test_bare_string_finding_is_its_issue():
    (got,) = _validate(["Criteria say a dark mode toggle; only light theme exists"])
    assert got["issue"].startswith("Criteria say"), got


# --------------------------------------------------------------- F. end to end

BLANK_HEADER = re.compile(r"^### \d+\. \*\*\w+\*\* — \s*$", re.MULTILINE)
BLANK_NAIVE = re.compile(r"^- \*\*\w+\*\*: \s*$", re.MULTILINE)


def test_sonnet_findings_render_in_consilium_summary():
    with tempfile.TemporaryDirectory() as td:
        eng = Path(td) / "eng"
        eng.mkdir()
        (eng / "criteria.md").write_text("# criteria\n", encoding="utf-8")
        (eng / "iteration").write_text("1", encoding="utf-8")
        (eng / "_findings.json").write_text(
            json.dumps([SONNET_FINDING, HAIKU_FINDING], ensure_ascii=False), encoding="utf-8")
        res = _drive("e2e", str(eng))
        assert res.get("status") == "ok", res
        r = subprocess.run([sys.executable, str(SYNTH), str(eng), "--iter", "1"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, check=False, timeout=60)
        assert r.returncode == 0, f"synth rc={r.returncode}\n{r.stderr[-800:]}"
        summary = (eng / "consilium-summary.md").read_text(encoding="utf-8")
    blanks = BLANK_HEADER.findall(summary) + BLANK_NAIVE.findall(summary)
    assert not blanks, f"{len(blanks)} blank finding line(s) in consilium-summary.md: {blanks}"
    assert SONNET_FINDING["actual_state"] in summary, "sonnet finding text missing from summary"
    assert HAIKU_FINDING["finding"] in summary, "haiku-shaped finding text missing from summary"


# --------------------------------------------------------------------- runner

def _run_standalone() -> int:
    import traceback

    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except unittest.SkipTest as e:
            skipped += 1
            print(f"  SKIP  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}")
            if isinstance(e, AssertionError):
                print(f"        {e}")
            else:
                traceback.print_exc()
    tail = f", {skipped} skipped" if skipped else ""
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} passed{tail}  (target: {script_path()})")
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--script" in argv:
        _SCRIPT_OVERRIDE = Path(argv[argv.index("--script") + 1]).resolve()
    sys.exit(_run_standalone())
