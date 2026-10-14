#!/usr/bin/env python3
"""Regression guard — consilium-summary.md shows reviewers that returned nothing.

When codex-blind and codex-informed write only *.raw.txt (no final JSON),
consilium-synth.py used to build the roster from the finals on disk, so the summary
listed the remaining reviewers, said nothing about the missing ones, and an L
consilium with zero cross-family reviewers could aggregate to "satisfied". Findings
with issue="" rendered as blank "**MINOR** — " lines.

  A. RAW-ONLY ROLE       no --tier: L inferred from files on disk; codex roles with
                         only pass1 raw.txt are FAILED rows naming the raw file.
  B. NO ARTEFACTS        --tier L, only peer-opus ran: the other 4 are FAILED with
                         "no output on disk" (a crash leaves no raw.txt).
  C. UNPARSEABLE FINAL   a final JSON that does not parse is FAILED, not skipped,
                         and its raw.txt names stay listed.
  C2. ALL FAILED         exit 1, a WARN per role, no summary written (precheck counts any
                         non-empty summary as a consilium), a stale one is flagged.
  D. NOT SATISFIED       present reviewers all satisfied + a FAILED role: aggregate
                         is director_review_required, rationale and --json name it.
  E. REWORK DOMINATES    rework_required stays rework_required; rationale adds the
                         missing roles.
  F. EMPTY TEXT          a finding with no text: WARN on stderr, a visible marker in
                         Findings and Naive-layer catches, no blank line, counted in --json.
  G. ALIAS TEXT          an old output with issue="" and the text in actual_state
                         renders that text on re-synth.
  H. M TIER CLEAN        peer-opus alone, with or without --tier M: no FAILED, still
                         satisfied (no false alarm on M).
  I. ITER SCOPED         iter-1 codex raw.txt does not mark iter 2 as failed.
  J. ADVERSARY WIRING    adversary_lg passes --tier to the synth (static), and a live
                         mock L consilium with both codex roles failing reports them
                         FAILED end to end.

Run standalone (harness gate) or under pytest:
  python test_consilium_failed_roles_regress.py
  python test_consilium_failed_roles_regress.py --script /tmp/patched-consilium-synth.py
  pytest test_consilium_failed_roles_regress.py -q
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

SCRIPTS = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPT = SCRIPTS / "consilium-synth.py"
ADVERSARY = SCRIPTS / "adversary_lg.py"
_SCRIPT_OVERRIDE: Path | None = None

TS = "20261006T080149Z"
L_ROSTER = ("peer-opus", "codex-blind", "codex-informed", "sonnet-scoped", "haiku-scoped")
BLANK_HEADER = re.compile(r"^### \d+\. \*\*\w+\*\* — \s*$", re.MULTILINE)
BLANK_NAIVE = re.compile(r"^- \*\*\w+\*\*: \s*$", re.MULTILINE)
EMPTY_MARK = "[EMPTY FINDING TEXT"


def script_path() -> Path:
    return _SCRIPT_OVERRIDE or DEFAULT_SCRIPT


def final(role: str, verdict: str = "satisfied", findings: list | None = None) -> dict:
    return {"verdict": verdict, "reviewer_role": role, "iteration": 1, "pass": 2,
            "findings": findings or [], "summary": f"{role} {verdict}"}


def make_eng(td: str, files: dict[str, object]) -> Path:
    eng = Path(td) / "eng"
    out = eng / "validation-outputs"
    out.mkdir(parents=True)
    (eng / "criteria.md").write_text("# criteria\n", encoding="utf-8")
    for name, body in files.items():
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        (out / name).write_text(text, encoding="utf-8")
    return eng


def synth(eng: Path, *args: str) -> tuple[int, str, str, str]:
    r = subprocess.run([sys.executable, str(script_path()), str(eng), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, check=False, timeout=60)
    p = eng / "consilium-summary.md"
    return r.returncode, r.stdout, r.stderr, (p.read_text(encoding="utf-8") if p.exists() else "")


def roster_row(summary: str, role: str) -> str:
    m = re.search(rf"^\| {re.escape(role)} \|.*$", summary, re.MULTILINE)
    return m.group(0) if m else ""


def raw_only_l_files(iter_n: int = 1) -> dict[str, object]:
    return {
        f"peer-opus-iter-{iter_n}-{TS}.json": final("peer-opus"),
        f"sonnet-scoped-iter-{iter_n}-{TS}.json": final("sonnet-scoped"),
        f"haiku-scoped-iter-{iter_n}-{TS}.json": final("haiku-scoped"),
        f"codex-blind-iter-{iter_n}-pass1-{TS}.raw.txt": "# stdout\nplease send the material\n",
        f"codex-informed-iter-{iter_n}-pass1-{TS}.raw.txt": "# stdout\nplease send the material\n",
    }


# ---------------------------------------------------------------- A-C. roster

def test_raw_only_roles_listed_as_failed():
    with tempfile.TemporaryDirectory() as td:
        rc, _, _, s = synth(make_eng(td, raw_only_l_files()), "--iter", "1")
    assert rc == 0, f"rc={rc}"
    for role in ("codex-blind", "codex-informed"):
        row = roster_row(s, role)
        assert "FAILED" in row, f"{role} must be a FAILED roster row, got {row!r}"
        assert f"{role}-iter-1-pass1-{TS}.raw.txt" in s, f"{role} raw file name missing"
    assert "## Failed reviewers" in s, "no Failed reviewers section"
    assert "FAILED" not in roster_row(s, "peer-opus"), "a role with a final is not failed"


def test_tier_flag_catches_role_with_no_artefacts():
    with tempfile.TemporaryDirectory() as td:
        eng = make_eng(td, {f"peer-opus-iter-1-{TS}.json": final("peer-opus")})
        rc, _, err, s = synth(eng, "--iter", "1", "--tier", "L")
    assert rc == 0, f"rc={rc}\n{err[-600:]}"
    for role in L_ROSTER[1:]:
        row = roster_row(s, role)
        assert "FAILED" in row and "no output on disk" in row, f"{role}: {row!r}"


def test_unparseable_final_is_failed():
    files = raw_only_l_files()
    files[f"codex-blind-iter-1-{TS}.json"] = '{"verdict": "satisfied", "findings": ['
    with tempfile.TemporaryDirectory() as td:
        rc, _, _, s = synth(make_eng(td, files), "--iter", "1", "--tier", "L")
    assert rc == 0, f"rc={rc}"
    row = roster_row(s, "codex-blind")
    assert "FAILED" in row and "unparseable" in row, row
    assert f"codex-blind-iter-1-pass1-{TS}.raw.txt" in row, f"raw file dropped: {row!r}"


def test_all_failed_warns_and_flags_stale_summary():
    files = {f"{r}-iter-2-pass1-{TS}.raw.txt": "# stdout\nno json\n" for r in L_ROSTER}
    with tempfile.TemporaryDirectory() as td:
        eng = make_eng(td, files)
        stale = "# Consilium synthesis — iter 1\n\n**Aggregate verdict:** satisfied\n"
        (eng / "consilium-summary.md").write_text(stale, encoding="utf-8")
        rc, _, err, s = synth(eng, "--iter", "2", "--tier", "L")
    assert rc == 1, f"rc={rc} (no outputs must stay exit 1)"
    for role in L_ROSTER:
        assert f"WARN: {role} returned no review" in err, f"{role} not warned: {err!r}"
    assert "NOT rewritten" in err and "iter 1" in err, f"stale summary not flagged: {err!r}"
    assert s == stale, "an all-failed run must not write a summary the precheck gate would count"


# ------------------------------------------------------------ D-E. aggregate

def test_failed_role_blocks_satisfied():
    with tempfile.TemporaryDirectory() as td:
        rc, out, _, s = synth(make_eng(td, raw_only_l_files()), "--iter", "1", "--json")
    assert rc == 0, f"rc={rc}"
    data = json.loads(out)
    assert data["aggregate_verdict"] == "director_review_required", data["aggregate_verdict"]
    assert "codex-blind" in data["rationale"] and "codex-informed" in data["rationale"], data
    assert sorted(f["role"] for f in data["failed_roles"]) == ["codex-blind", "codex-informed"], data
    assert "**Aggregate verdict:** director_review_required" in s


def test_rework_still_dominates():
    files = raw_only_l_files()
    files[f"peer-opus-iter-1-{TS}.json"] = final("peer-opus", "rework_required", [
        {"severity": "major", "issue": "Locator regex rejects units", "evidence_path": "a.py:1"}])
    with tempfile.TemporaryDirectory() as td:
        rc, out, _, _ = synth(make_eng(td, files), "--iter", "1", "--json")
    assert rc == 0, f"rc={rc}"
    data = json.loads(out)
    assert data["aggregate_verdict"] == "rework_required", data
    assert "codex-blind" in data["rationale"], data["rationale"]


# ------------------------------------------------------------- F-G. findings

def test_empty_finding_text_warns_and_is_marked():
    files = {
        f"peer-opus-iter-1-{TS}.json": final("peer-opus"),
        f"sonnet-scoped-iter-1-{TS}.json": final("sonnet-scoped", "rework_required", [
            {"severity": "major", "issue": "", "decision": "criteria not met"}]),
    }
    with tempfile.TemporaryDirectory() as td:
        rc, out, err, s = synth(make_eng(td, files), "--iter", "1", "--json")
    assert rc == 0, f"rc={rc}"
    blanks = BLANK_HEADER.findall(s) + BLANK_NAIVE.findall(s)
    assert not blanks, f"blank finding line(s): {blanks}"
    assert s.count(EMPTY_MARK) >= 2, "marker must show in Findings AND Naive-layer catches"
    assert "WARN" in err and "empty" in err.lower(), f"no stderr warning: {err!r}"
    assert json.loads(out)["empty_findings"] == 1, out


def test_alias_text_rendered_on_resynth():
    files = {
        f"peer-opus-iter-1-{TS}.json": final("peer-opus"),
        f"sonnet-scoped-iter-1-{TS}.json": final("sonnet-scoped", "rework_required", [
            {"issue": "", "criterion": "crit-7",
             "actual_state": "Stubs read os.environ directly"}]),
    }
    with tempfile.TemporaryDirectory() as td:
        rc, _, _, s = synth(make_eng(td, files), "--iter", "1")
    assert rc == 0, f"rc={rc}"
    assert "Stubs read os.environ directly" in s, "actual_state text must render"
    assert EMPTY_MARK not in s


# ---------------------------------------------------------- H-I. no false alarm

def test_m_tier_clean_unchanged():
    for extra in ([], ["--tier", "M"]):
        with tempfile.TemporaryDirectory() as td:
            eng = make_eng(td, {f"peer-opus-iter-1-{TS}.json": final("peer-opus")})
            rc, out, _, s = synth(eng, "--iter", "1", "--json", *extra)
        assert rc == 0, f"rc={rc} {extra}"
        data = json.loads(out)
        assert data["aggregate_verdict"] == "satisfied", (extra, data)
        assert data.get("failed_roles") == [], (extra, data)
        assert "FAILED" not in s and "## Failed reviewers" not in s, extra


def test_other_iteration_artefacts_ignored():
    files = raw_only_l_files(iter_n=1)
    files[f"peer-opus-iter-2-{TS}.json"] = final("peer-opus")
    with tempfile.TemporaryDirectory() as td:
        rc, out, _, s = synth(make_eng(td, files), "--iter", "2", "--json")
    assert rc == 0, f"rc={rc}"
    assert json.loads(out).get("failed_roles") == [], out
    assert "FAILED" not in s


# --------------------------------------------------------- J. adversary wiring

def test_adversary_passes_tier_to_synth():
    src = ADVERSARY.read_text(encoding="utf-8")
    m = re.search(r"\[sys\.executable, str\(synth_script\).*?\]", src, re.DOTALL)
    assert m, "synth invocation not found in adversary_lg.py"
    assert '"--tier", tier' in m.group(0), f"synth argv lacks --tier: {m.group(0)}"


def _venv_python() -> str:
    for rel in ("Scripts/python.exe", "bin/python"):
        cand = SCRIPTS / ".venv-adversary-lg" / rel
        if cand.exists():
            return str(cand)
    raise unittest.SkipTest("adversary venv absent — build scripts/.venv-adversary-lg from "
                            "scripts/requirements-adversary-lg.txt")


def test_live_mock_l_consilium_reports_failed_codex():
    py = _venv_python()
    with tempfile.TemporaryDirectory() as td:
        eng = Path(td) / "eng"
        eng.mkdir()
        (eng / "criteria.md").write_text("# criteria\n", encoding="utf-8")
        env = {**os.environ, "ADVERSARY_MOCK_FAIL": "codex-blind,codex-informed"}
        r = subprocess.run([py, str(ADVERSARY), str(eng), "--consilium", "L",
                            "--invoker", "mock", "--no-checkpoint"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, stdin=subprocess.DEVNULL, check=False, timeout=300)
        p = eng / "consilium-summary.md"
        s = p.read_text(encoding="utf-8") if p.exists() else ""
    assert s, f"no consilium-summary.md (rc={r.returncode})\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
    for role in ("codex-blind", "codex-informed"):
        assert "FAILED" in roster_row(s, role), f"{role} row: {roster_row(s, role)!r}"
    assert "aggregate_verdict=satisfied" not in r.stdout, r.stdout[-800:]
    m = re.search(r"rationale: .*", r.stdout)
    assert m and "codex-blind" in m.group(0), r.stdout[-800:]


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
                print(f"        {str(e)[:400]}")
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
