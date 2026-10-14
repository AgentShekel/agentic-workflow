#!/usr/bin/env python3
"""Executable golden-scenario runner (stage-4 pilot).

Runs a validator agent headlessly on a scenario fixture the way `scripts/validator_lg.py`
dispatches it in production (`claude -p --agent <name>`, Read/Glob/Grep only, same prompt),
normalises the output with validator_lg's own status derivation and canonical maps, and grades
it programmatically against the scenario's pass-criteria.

Variants are built from the live agent file: `baseline` is the file as it is, any other variant
applies one edit from golden/known-bad.md to an in-memory copy and passes it via `--agents`.
The working corpus is never modified.

Deviations from production dispatch, all deliberate: `--agents` (to mutate the agent without
touching the corpus; proven wired by --probe), `--output-format stream-json --verbose` (to keep
the full tool trajectory), `--no-session-persistence`, and cwd = a fresh copy of the fixture,
which plays the project root production would inherit.

Layout follows references/anthropic-evals/report/runner-scaffold.mjs:
  <out>/<variant>/results.jsonl   one row per (case, rep) that produced a scorable output
  <out>/<variant>/errors.jsonl    attempts that did not, with a failure class
  <out>/<variant>/traces/<case>_rep<k>.json
  <out>/summary.json

Usage:
  python golden_exec.py --selftest
  python golden_exec.py --probe --out <new dir>
  python golden_exec.py --variants baseline,KB-design-01 --reps 3 --out <new dir>
  python golden_exec.py --regrade <existing out dir>
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_DIR", Path.home() / ".claude"))
SKILL = CLAUDE_DIR / "skills" / "system-optimization-protocol"
EXEC = SKILL / "golden" / "exec"
KNOWN_BAD = SKILL / "golden" / "known-bad.md"
VALIDATOR_LG = CLAUDE_DIR / "scripts" / "validator_lg.py"
CLAUDE_BIN = shutil.which("claude") or "claude"
TIMEOUT_S = 600

VALIDATOR = "accessibility-validator"
# mirrors validator_lg.CONTRAST_TOOL_RULE (the only shell command a validator may run)
CONTRAST_TOOL_RULES = ("Bash(python ~/.claude/scripts/contrast.py:*)", "Bash(python3 ~/.claude/scripts/contrast.py:*)")
CASES = ["design/scenario-03", "design/scenario-04"]


# --------------------------------------------------------------------------- production normalisation
def _load_lg_maps() -> tuple[dict, dict]:
    """Read _VERDICT_MAP / _SEVERITY_MAP literally from validator_lg.py (no import side effects)."""
    tree = ast.parse(VALIDATOR_LG.read_text(encoding="utf-8"))
    maps = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
            if name in ("_VERDICT_MAP", "_SEVERITY_MAP"):
                maps[name] = ast.literal_eval(node.value)
    return maps["_VERDICT_MAP"], maps["_SEVERITY_MAP"]


VERDICT_MAP, SEVERITY_MAP = _load_lg_maps()


def derive_status(data: dict) -> dict:
    """Mirror of validator_lg.ValidatorOutput._derive_status (pre-validation)."""
    if data.get("status"):
        return data
    data = dict(data)
    for alt in ("verdict", "result", "overall", "outcome", "decision"):
        if data.get(alt):
            data["status"] = data[alt]
            return data

    def _as_int(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return 0

    count_keys = ("critical_findings", "major_findings", "minor_findings",
                  "critical_count", "major_count", "critical", "major")
    if any(k in data for k in count_keys):
        crit = _as_int(data.get("critical_findings", data.get("critical_count", data.get("critical", 0))))
        major = _as_int(data.get("major_findings", data.get("major_count", data.get("major", 0))))
        data["status"] = "rework_required" if (crit > 0 or major > 0) else "satisfied"
        return data
    data["status"] = "error"
    return data


def canonicalize(raw: dict) -> dict:
    """Mirror of validator_lg.canonicalize_validator_output (verdict + findings)."""
    status = str(raw.get("status") or "").strip().lower()
    verdict = VERDICT_MAP.get(status, status or "error")
    findings = []
    for idx, f in enumerate(raw.get("findings") or []):
        f = f if isinstance(f, dict) else {}
        sev = f.get("severity")
        findings.append({
            "id": f"{VALIDATOR}#{idx}",
            "severity": "info" if sev is None else SEVERITY_MAP.get(str(sev).strip().lower(), "info"),
            "category": f.get("category"),
            "issue": str(f.get("message") or f.get("issue") or f.get("description") or f.get("detail") or ""),
            "fix": f.get("fix"),
            "evidence": f.get("evidence") or f.get("source"),
            "location": f.get("location"),
        })
    metrics = {k: v for k, v in raw.items()
               if isinstance(v, (int, float)) and k not in {"status", "findings", "summary", "methodology"}} or None
    return {"verdict": verdict, "findings": findings, "metrics": metrics}


def extract_json(text: str):
    """Same algorithm as validator_lg._extract_json."""
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = "\n".join(l for l in text.split("\n") if not l.startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    first = text.find("{")
    if first == -1:
        return None
    depth = 0
    for i in range(first, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[first:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def schema_problem(raw) -> str | None:
    """Unscorable output: goes to errors.jsonl, never into the score (eval-audit §2)."""
    if not isinstance(raw, dict):
        return "not a JSON object"
    if str(raw.get("status") or "").strip().lower() in ("", "error"):
        return f"no usable status ({raw.get('status')!r})"
    if not isinstance(raw.get("findings", []), list):
        return "findings is not a list"
    if any(not isinstance(f, dict) for f in raw.get("findings") or []):
        return "a finding is not an object"   # production's list[Finding] rejects these
    return None


# --------------------------------------------------------------------------- grader helpers
RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*:\s*1\b")
# A quoted WCAG bar, not a measurement, is decided by context, not by value: a model that
# measures "~3.0:1" is reporting a real 3.04:1 pair. Context is read on both sides, bounded by
# the neighbouring ratio, so "3:1 is required" and "requires 4.5:1" drop while
# "normal text contrast ratio is 3.04:1" keeps its number.
BEFORE_BAR = re.compile(r"(requir\w*|minimum(?: of)?|threshold(?: of)?|at least|needs?|must be|>=|≥|instead of|"
                        r"below|under|than)\s*(?:the\s*|a\s*|of\s*)?(?:wcag\s*)?(?:aa\s*)?$")
AFTER_BAR = re.compile(r"^\s*(?:is |are )?(?:the )?(?:required|requirement|minimum|threshold|bar|needed)")
HIGH = {"critical", "high"}
LOCATING = ("file", "line", "selector", "element", "location", "pattern", "wcagCriterion",
            "category", "issue", "message", "description", "evidence", "metrics", "ratio", "token")
NEGATED = re.compile(r"(?:(?:\bnot\b|n't|\bno need to\b|\bwithout\b)\s+(?:\w+\s+){0,2}|\bun)$")


def _loc(f: dict) -> str:
    """Text a finding uses to say WHAT it is about. Excludes fix / impact, which talk about
    remedies and consequences and drag in unrelated words ("darken", "keep the heading")."""
    return json.dumps({k: f.get(k) for k in LOCATING if k in f}, ensure_ascii=False).lower()


def _measured(f: dict) -> list[float]:
    """Ratios the finding reports as measured: N:1 in its locating text plus numeric ratio
    fields, minus the WCAG thresholds it quotes."""
    loc = _loc(f)
    ms = list(RATIO_RE.finditer(loc))
    vals = []
    for i, m in enumerate(ms):
        lo = max(ms[i - 1].end() if i else 0, m.start() - 40)
        hi = min(ms[i + 1].start() if i + 1 < len(ms) else len(loc), m.end() + 30)
        if BEFORE_BAR.search(loc[lo:m.start()]) or AFTER_BAR.search(loc[m.end():hi]):
            continue
        vals.append(float(m.group(1)))
    for k in ("ratio", "contrastRatio", "contrast_ratio", "measured"):
        v = f.get(k) if k in f else (f.get("metrics") or {}).get(k) if isinstance(f.get("metrics"), dict) else None
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return [v for v in vals if 1.0 <= v < 21.0]


def _is_contrast(loc: str) -> bool:
    return "contrast" in loc or "1.4.3" in loc


def _affirmed(rx: re.Pattern, text: str) -> bool:
    """rx matches somewhere not directly negated ("do not replace", "undocumented")."""
    return any(not NEGATED.search(text[max(0, m.start() - 30):m.start()]) for m in rx.finditer(text))


# --------------------------------------------------------------------------- scenario 03
TARGET_BG = re.compile(r"1f2937|surface-dark")
DARK_WORD = re.compile(r"dark[ -](?:mode|theme|surface|panel|background)|theme=[\"']?dark")
OTHER_DARK_BG = re.compile(r"111827|--color-surface(?!-)")      # the page surface, also dark
LIGHT_BG = re.compile(r"ffffff|#fff\b|white|light[ -](?:mode|theme)")


def grade_s03(raw: dict, canon: dict) -> dict:
    """Outcome rule: ONE finding flags the failing dark-theme text
    colour (--color-text-secondary / #6b7280) on a dark surface, reports a measured ratio below
    4.5, is critical/high, and the verdict blocks. Naming the page surface #111827 instead of the
    panel's #1f2937 still passes; the light theme or white does not. Strict (precision only):
    the exact panel pair and 3.04:1 within rounding."""
    per = []
    for rf, cf_ in zip(raw.get("findings") or [], canon["findings"]):
        loc = _loc(rf)
        fg = "6b7280" in loc or "text-secondary" in loc
        right_bg = TARGET_BG.search(loc) is not None
        other_dark = OTHER_DARK_BG.search(loc) is not None and not right_bg
        light_only = LIGHT_BG.search(loc) is not None and not (right_bg or other_dark or DARK_WORD.search(loc))
        dark = right_bg or other_dark or (DARK_WORD.search(loc) is not None and not light_only)
        about = _is_contrast(loc) and fg and dark
        ratios = _measured(rf)
        accurate = any(2.8 <= r <= 3.3 for r in ratios)
        per.append({"about": about, "wrong_bg": about and other_dark,
                    "high": cf_["severity"] in HIGH,
                    "ratio_ok": any(r < 4.5 for r in ratios),
                    "ratio_accurate": accurate,
                    "strict_fields": accurate and right_bg and ("text-secondary" in loc or "6b7280" in loc)})
    catch = [p for p in per if p["about"] and p["high"] and p["ratio_ok"]]
    blocks = canon["verdict"] == "changes_required"
    passed = blocks and bool(catch)
    return {"pass": passed,
            "pass_strict": passed and any(p["strict_fields"] for p in catch),
            "detected": any(p["about"] for p in per),
            "detected_high": any(p["about"] and p["high"] for p in per),
            # diagnostic: caught, but against the page surface rather than the panel
            "wrong_pair_only": bool(catch) and all(p["wrong_bg"] for p in catch),
            "ratio_accurate": any(p["about"] and p["ratio_accurate"] for p in per),
            "blocks": blocks, "n_findings": len(per)}


# --------------------------------------------------------------------------- scenario 04
TITLE_REF = re.compile(r"hero__title|brand-accent|2f9e44|hero__badge|\bh1\b|display heading|"
                       r"hero (?:title|heading|headline)|spring collection is here|"
                       r"white (?:text )?on (?:the )?green|green badge")
FOCUS_REF = re.compile(r"focus|outline|1\.4\.11")           # the CTA is the only focusable element
DOC_REF = re.compile(r"\breadme\b|\bdocumented\b|ring-on-imagery|design[ -]system (?:exception|documents|allows)")
REPLACE_DEMAND = re.compile(r"\b(replace|swap|change|darken|lighten|use a (?:darker|different)|switch)\b")
LARGE_TEXT = re.compile(r"large[ -]text|3\s*:\s*1|24\s*px|18\s*pt|14\s*pt")
COMPLIANT = re.compile(r"\b(meets|passes|compliant|satisf\w+|acceptable|applies|is fine|approved|"
                       r"documented as|allowed|permitted|sufficient|exceeds)\b")
# a focus finding is a complaint about the ring only if it reports a problem; validators also
# list passing checks as findings ("keyboard focus is visible")
RING_PROBLEM = re.compile(r"\b(deviat\w*|invisible|not visible|insufficient|missing|lacks?|fails?|violat\w*|"
                          r"inconsistent|instead of|non-?standard|differs?|unclear|hard to see|poor|"
                          r"low contrast|weak)\b")
VIOLATES = re.compile(r"\b(fails?|failing|violat\w*|insufficient|below|does not meet|non-?compliant)\b")


def grade_s04(raw: dict, canon: dict) -> dict:
    """Documented large-text pair (3.45:1 on a 40px/700 heading) and documented imagery focus
    ring must not be flagged as violations: verdict approved(_with_caveats), zero
    critical/high anywhere, no finding demanding a token or colour change on the title, any
    title finding closes as compliant under the large-text bar, any focus-ring finding cites
    the documentation affirmatively at the lowest severity. Semantics are read by regex, so this
    grader is a screen; the stored traces are the ground truth for any surprising row."""
    any_high, swap_demand, title, ring = False, False, [], []
    for rf, cf_ in zip(raw.get("findings") or [], canon["findings"]):
        loc, fix = _loc(rf), str(rf.get("fix") or "").lower()
        sev = cf_["severity"]
        any_high |= sev in HIGH
        # a demand to swap the documented token fails the scenario whichever element it names
        swap_demand |= "brand-accent-inverse" in fix + " " + loc and _affirmed(REPLACE_DEMAND, fix + " " + loc)
        if _is_contrast(loc) and TITLE_REF.search(loc):
            ok_words, bad_words = _affirmed(COMPLIANT, loc), _affirmed(VIOLATES, loc)
            closes = LARGE_TEXT.search(loc) is not None and ok_words
            demands = _affirmed(REPLACE_DEMAND, fix)
            title.append({"severity": sev, "closes_compliant": closes, "demands_change": demands,
                          "bad": sev in HIGH | {"medium"} or demands or not closes or (bad_words and not ok_words)})
        elif FOCUS_REF.search(loc) and "hover" not in loc and _affirmed(RING_PROBLEM, loc):
            cites = _affirmed(DOC_REF, loc)
            ring.append({"severity": sev, "cites_doc": cites,
                         "bad": sev not in {"low", "info"} or not cites or _affirmed(REPLACE_DEMAND, fix)})
    verdict_ok = canon["verdict"] in ("approved", "approved_with_caveats")
    passed = (verdict_ok and not any_high and not swap_demand
              and not any(t["bad"] for t in title) and not any(r["bad"] for r in ring))
    return {"pass": passed,
            # scenario revised 2026-10-06: the ring may be raised at the validator's lowest
            # severity (low or info), so strict and ordinary coincide
            "pass_strict": passed,
            "verdict_ok": verdict_ok, "any_high": any_high, "swap_demand": swap_demand,
            "title_findings": title, "ring_findings": ring}


GRADERS = {"design/scenario-03": grade_s03, "design/scenario-04": grade_s04}


def score(case: str, raw: dict) -> tuple[dict, dict]:
    raw = derive_status(raw)
    canon = canonicalize(raw)
    return canon, GRADERS[case](raw, canon)


# --------------------------------------------------------------------------- variants
def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    fm_txt, body = (m.group(1), text[m.end():]) if m else ("", text)
    desc = re.search(r"^description:\s*\|\s*\n((?:[ \t]+.*\n?)+)", fm_txt, re.MULTILINE)
    mod = re.search(r"^model:\s*(\S+)", fm_txt, re.MULTILINE)
    # `tools:` as a YAML block list or an inline comma list; the agent file is the source of truth
    blk = re.search(r"^tools:\s*\n((?:[ \t]+-[ \t]+\S.*\n?)+)", fm_txt, re.MULTILINE)
    inl = re.search(r"^tools:[ \t]*(\S.*)$", fm_txt, re.MULTILINE)
    if blk:
        tools = [t.strip().lstrip("-").strip() for t in blk.group(1).splitlines() if t.strip()]
    elif inl:
        tools = [t.strip() for t in inl.group(1).split(",")]
    else:
        tools = ["Read", "Glob", "Grep"]
    return {"description": re.sub(r"\s+", " ", desc.group(1)).strip() if desc else VALIDATOR,
            "model": mod.group(1) if mod else None, "tools": tools}, body


def _known_bad_edit(edit_id: str) -> dict:
    text = KNOWN_BAD.read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(edit_id)}\b.*?```json\s*\n(.*?)\n```", text, re.DOTALL | re.MULTILINE)
    if not m:
        raise SystemExit(f"edit {edit_id} not found in {KNOWN_BAD}")
    return json.loads(m.group(1))


def _apply(body: str, edit: dict) -> str:
    anchor = edit["target"].split("::", 1)[1] if "::" in edit["target"] else None
    op = edit["op"]
    if op == "append":
        return body.rstrip("\n") + "\n" + edit["content"] + "\n"
    if not anchor or body.count(anchor) != 1:
        raise SystemExit(f"anchor not found exactly once for {op}: {str(anchor)[:60]!r}")
    if op == "replace":
        return body.replace(anchor, edit["content"])
    if op == "insert_after":
        return body.replace(anchor, anchor + "\n" + edit["content"])
    if op == "delete":
        return body.replace(anchor, "")
    raise SystemExit(f"unsupported op {op}")


def build_agents_json(variant: str, tmp: Path) -> tuple[Path, str]:
    fm, body = _split_frontmatter((CLAUDE_DIR / "agents" / f"{VALIDATOR}.md").read_text(encoding="utf-8"))
    if "@" in variant:                       # e.g. baseline@sonnet: same body, model overridden
        variant, fm["model"] = variant.split("@", 1)
    if variant == "probe":
        # a marker that does not conflict with the task: if it shows up, the --agents prompt ran
        body = (body.rstrip("\n")
                + '\n\nAlways include the top-level field "probe": "PROBE-WIRED" in your JSON output.\n')
    elif variant != "baseline":
        edit = _known_bad_edit(variant)
        if not edit["target"].startswith(f"agents/{VALIDATOR}.md"):
            raise SystemExit(f"{variant} targets {edit['target']}, not {VALIDATOR}")
        body = _apply(body, edit)
    spec = {VALIDATOR: {"description": fm["description"], "prompt": body,
                        "tools": fm["tools"]}}
    if fm["model"]:
        spec[VALIDATOR]["model"] = fm["model"]
    p = tmp / f"agents-{variant}-{fm['model'] or 'default'}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p, fm["model"] or ""


# --------------------------------------------------------------------------- one attempt
def _parse_stream(stdout: str) -> tuple[dict | None, list, list]:
    events, tools = [], []
    result = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(ev)
        if ev.get("type") == "result":
            result = ev
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools.append({"name": block.get("name"), "input": block.get("input")})
    return result, events, tools


def run_once(variant: str, case: str, rep: int, out: Path, agents_file: Path, want_model: str) -> tuple[str, dict]:
    base = {"case": case, "rep": rep, "variant": variant}
    tname = f"{case.replace('/', '__')}_rep{rep}.json"
    tdir = out / variant / "traces"
    work = Path(tempfile.mkdtemp(prefix="golden-exec-"))
    try:
        shutil.copytree(EXEC / case, work, dirs_exist_ok=True)       # fresh state per (case, rep)
        eng = work / "engagement"
        prompt = (f"Run validator '{VALIDATOR}' on engagement at {eng}. "
                  f"Output JSON only to stdout matching the validator's standard schema. "
                  f"No prose, no markdown fences.")
        cmd = [CLAUDE_BIN, "-p", "--agents", str(agents_file), "--agent", VALIDATOR, prompt,
               "--allowedTools", "Read", "Glob", "Grep", *CONTRAST_TOOL_RULES,
               "--add-dir", str(eng), "--add-dir", str(eng.parent),
               "--output-format", "stream-json", "--verbose", "--no-session-persistence"]
        t0 = time.monotonic()
        try:
            r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", check=False,
                               errors="replace", stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as te:
            tdir.mkdir(parents=True, exist_ok=True)
            (tdir / tname).write_text(json.dumps({**base, "timeout_s": TIMEOUT_S,
                                                  "partial_stdout": str(te.stdout or "")[-4000:]}, ensure_ascii=False, indent=2), encoding="utf-8")
            return "error", {**base, "class": "timeout"}
        wall = round(time.monotonic() - t0, 1)
        result, events, tools = _parse_stream(r.stdout)
        trace = {**base, "rc": r.returncode, "stderr": (r.stderr or "")[-2000:], "wall_s": wall,
                 "tools": tools, "result_event": result, "events": events}
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / tname).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        row = {**base, "wall_s": wall}
        if r.returncode != 0 or not isinstance(result, dict):
            return "error", {**row, "class": "harness", "rc": r.returncode, "stderr": (r.stderr or "")[-400:]}
        served = sorted((result.get("modelUsage") or {}).keys())
        if want_model and (not served or not all(want_model in m for m in served)):
            return "error", {**row, "class": "served_model_mismatch", "served": served}
        if result.get("is_error"):
            return "error", {**row, "class": "harness", "detail": str(result.get("result"))[:400]}
        return grade_trace(case, trace, row, served, result)
    except Exception:  # noqa: BLE001 -- never let one attempt abort the batch
        return "error", {**base, "class": "runner_exception", "detail": traceback.format_exc()[-800:]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def grade_trace(case: str, trace: dict, row: dict, served, result: dict) -> tuple[str, dict]:
    raw = extract_json(result.get("result") or "")
    raw = derive_status(raw) if isinstance(raw, dict) else raw
    problem = schema_problem(raw)
    if problem:
        return "error", {**row, "class": "unscorable_output", "detail": problem,
                         "result_head": str(result.get("result"))[:400]}
    canon, grade = score(case, raw)
    read = sorted({str((t.get("input") or {}).get("file_path") or (t.get("input") or {}).get("pattern") or "")
                   .replace("\\", "/").split("/engagement/")[-1] for t in trace.get("tools") or [] if t.get("name") == "Read"})
    calc = sum(1 for t in trace.get("tools") or []
               if t.get("name") == "Bash" and "contrast.py" in str((t.get("input") or {}).get("command")))
    return "ok", {**row, "served_model": served, "verdict": canon["verdict"], "grade": grade, "calc_calls": calc,
                  "n_findings": len(canon["findings"]), "files_read": read,
                  "cost_usd": result.get("total_cost_usd"), "num_turns": result.get("num_turns"),
                  "usage": result.get("usage"), "probe": raw.get("probe")}


# --------------------------------------------------------------------------- self-test (oracle / null / known false passes)
def selftest() -> int:
    S3, S4 = "design/scenario-03", "design/scenario-04"
    dark = "dark theme --color-text-secondary #6b7280 on --color-surface-dark #1f2937"
    cases = [
        (S3, "oracle", {"status": "changes_required", "findings": [{"severity": "major", "category": "color-contrast",
            "issue": f"{dark} is 3.04:1, below 4.5:1", "evidence": "3.04:1, token --color-text-secondary"}]}, True, True),
        (S3, "oracle-token-names-only", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": "Contrast of --color-text-secondary on --color-surface-dark is 3.04:1"}]}, True, True),
        (S3, "oracle-numeric-ratio-field", {"status": "changes_required", "findings": [{"severity": "critical",
            "issue": f"low contrast: {dark}", "ratio": 3.04}]}, True, True),
        (S3, "verdict-field-not-status", {"verdict": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark} contrast 3.04:1"}]}, True, True),
        # real haiku output 2026-10-06 (pilot2 s03 baseline rep1): "~3.0:1" is a measurement
        (S3, "measured-3.0-not-a-threshold", {"status": "changes_required", "findings": [{"severity": "critical",
            "wcagCriterion": "1.4.3", "issue": "Dark mode --color-text-secondary (#6b7280) has only ~3.0:1 contrast ratio against --color-surface-dark (#1f2937). WCAG AA requires 4.5:1 for normal text."}]}, True, True),
        (S3, "only-thresholds-quoted", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark}: WCAG AA requires 4.5:1 for normal text and at least 3:1 for large text"}]}, False, False),
        (S3, "null-empty", {"status": "approved", "findings": []}, False, False),
        # real haiku output 2026-10-06: light pair miscalculated, dark pair never named
        (S3, "light-miscalc", {"status": "changes_required", "findings": [{"severity": "major", "wcagCriterion": "1.4.3",
            "issue": "Secondary text color #4b5563 on white background (#ffffff) has contrast ratio of approximately 4.48:1",
            "fix": "Darken secondary text color. Change --color-text-secondary from #4b5563 to #3a4350"}]}, False, False),
        (S3, "fg-on-light-surface", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": "Contrast of #6b7280 on the light white surface is 3.04:1"}]}, False, False),
        (S3, "wrong-ratio-quotes-threshold", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark} measures 5.2:1; large text needs 3:1, normal 4.5:1"}]}, False, False),
        (S3, "ratio-and-pair-in-different-findings", {"status": "changes_required", "findings": [
            {"severity": "major", "issue": f"contrast concern on {dark}"},
            {"severity": "major", "issue": "contrast of the badge is 2.1:1"}]}, False, False),
        (S3, "detected-not-blocking", {"status": "approved", "findings": [{"severity": "major",
            "issue": f"{dark} contrast 3.04:1"}]}, False, False),
        (S3, "detected-low-severity", {"status": "changes_required", "findings": [{"severity": "minor",
            "issue": f"{dark} contrast 3.04:1"}]}, False, False),
        # real haiku output (pilot2 s03 baseline rep2): dark-mode, but the page surface, not the panel
        (S3, "wrong-dark-bg-111827", {"status": "changes_required", "findings": [{"severity": "critical",
            "wcagCriterion": "1.4.3", "issue": "Dark-mode secondary text color (#6b7280) on dark surface (#111827) has contrast ratio of 3.6:1, below WCAG AA minimum of 4.5:1"}]}, True, False),   # outcome rule: the outcome counts
        (S3, "threshold-after-number", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark}: contrast 5.2:1; 3:1 is required for large text"}]}, False, False),
        (S3, "measurement-after-normal-text", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark}: normal text contrast ratio is 3.04:1"}]}, True, True),
        (S3, "measured-then-for-normal-text", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": "Contrast of #6b7280 on #1f2937 measures 3.04:1 for normal text"}]}, True, True),
        (S3, "bar-after-below", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": f"{dark} contrast falls below 4.5:1 for normal text"}]}, False, False),
        (S3, "strict-via-metrics", {"status": "changes_required", "findings": [{"severity": "major",
            "category": "color-contrast", "issue": f"{dark} low contrast", "metrics": {"ratio": 3.04, "token": "--color-text-secondary"}}]}, True, True),
        (S4, "oracle", {"status": "approved", "findings": []}, True, True),
        # real haiku output (pilot3 s04 baseline rep5): an exemplary approval, positive notes as findings
        (S4, "exemplary-positive-notes", {"status": "approved", "findings": [
            {"severity": "minor", "issue": "Hero title: white (#ffffff) on brand-accent (#2f9e44) = 3.45:1 ratio at 40px/700. Documented as large-text-only pair approved in design-system/README.md for WCAG AA at 3:1 threshold."},
            {"severity": "minor", "issue": "Focus ring on imagery: 2px solid white outline (focus.ring-on-imagery) documented as exception in design-system/README.md. Worst-case contrast = 3.36:1"},
            {"severity": "minor", "issue": "Link includes :focus-visible styling with white outline — keyboard focus is visible"}]}, True, True),
        (S4, "title-fails-even-large", {"status": "approved", "findings": [{"severity": "info",
            "issue": "Hero title contrast 3.45:1 fails AA even for large text"}]}, False, False),
        (S4, "ring-undocumented-word", {"status": "approved", "findings": [{"severity": "info",
            "issue": "CTA focus ring is undocumented and violates the default design system"}]}, False, False),
        (S4, "do-not-replace", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "hero__title brand-accent-inverse contrast 3.45:1 meets the 3:1 large-text bar",
            "fix": "None needed; do not replace brand-accent-inverse"}]}, True, True),
        (S4, "title-colour-change-no-token-name", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "hero__title contrast 3.45:1 meets the 3:1 large-text bar but is close",
            "fix": "darken the badge background to #237a35"}]}, False, False),
        (S4, "ring-poor-contrast", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "Focus ring has poor contrast"}]}, False, False),
        (S4, "hover-not-ring", {"status": "approved", "findings": [{"severity": "minor",
            "wcagCriterion": "2.4.7", "issue": "CTA link has no :hover or :active state defined"}]}, True, True),        (S4, "oracle-title-resolved", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "hero__title brand-accent-inverse contrast 3.45:1 meets the 3:1 large-text threshold (40px/700); compliant"}]}, True, True),
        (S4, "oracle-ring-documented-low", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "CTA uses a 2px outline focus ring instead of the default; documented in design-system README (ring-on-imagery)"}]}, True, True),
        (S4, "overeager-title", {"status": "changes_required", "findings": [{"severity": "major",
            "issue": "hero__title contrast 3.45:1 below 4.5:1"}]}, False, False),
        (S4, "low-sev-swap-demand", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "hero title fails contrast", "fix": "replace brand-accent-inverse with a darker token"}]}, False, False),
        (S4, "low-sev-title-no-threshold", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "h1 contrast 3.45:1 is low"}]}, False, False),
        (S4, "ring-undocumented", {"status": "approved", "findings": [{"severity": "minor",
            "issue": "CTA focus outline deviates from the default focus ring"}]}, False, False),
        (S4, "ring-major", {"status": "approved", "findings": [{"severity": "major",
            "issue": "hero__cta outline focus style; documented exception in README but still flagged"}]}, False, False),
    ]
    bad = 0
    for case, label, raw, exp, exp_strict in cases:
        _, g = score(case, raw)
        ok = g["pass"] == exp and g["pass_strict"] == exp_strict and (g["pass"] or not g["pass_strict"])
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case} {label}: pass={g['pass']} strict={g['pass_strict']} "
              f"(expected {exp}/{exp_strict})")
    schema_cases = [("empty-object", {}, True), ("status-error", {"status": "error", "error": "x"}, True),
                    ("status-error-padded", {"status": " ERROR ", "findings": []}, True),
                    ("findings-not-list", {"status": "approved", "findings": "none"}, True),
                    ("finding-not-object", {"status": "approved", "findings": [42]}, True),
                    ("valid", {"status": "approved", "findings": []}, False)]
    for label, raw, cls in schema_cases:
        got = schema_problem(derive_status(raw)) is not None
        ok = got == cls
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] schema {label}: unscorable={got} (expected {cls})")
    total = len(cases) + len(schema_cases)
    print(f"{total - bad}/{total} self-test checks passed")
    return 1 if bad else 0


# --------------------------------------------------------------------------- summary / regrade
def summarise(out: Path) -> dict:
    summary = {}
    for vd in sorted(p for p in out.iterdir() if p.is_dir()):
        rows = [json.loads(l) for l in (vd / "results.jsonl").read_text(encoding="utf-8").splitlines()] if (vd / "results.jsonl").exists() else []
        errs = [json.loads(l) for l in (vd / "errors.jsonl").read_text(encoding="utf-8").splitlines()] if (vd / "errors.jsonl").exists() else []
        per = {}
        for c in sorted({r["case"] for r in rows} | {e["case"] for e in errs}):
            rs = [r for r in rows if r["case"] == c]
            per[c] = {"scored": len(rs), "errors": [e["class"] for e in errs if e["case"] == c],
                      "pass": sum(bool(r["grade"]["pass"]) for r in rs),
                      "pass_strict": sum(bool(r["grade"]["pass_strict"]) for r in rs),
                      # did the mechanism engage, separately from whether the run passed
                      "engaged": sum(bool(r["grade"].get("detected") or r["grade"].get("title_findings")) for r in rs),
                      "no_findings": sum(r.get("n_findings", 0) == 0 for r in rs),
                      "verdicts": [r["verdict"] for r in sorted(rs, key=lambda r: r["rep"])]}
        summary[vd.name] = per
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def regrade(out: Path) -> int:
    """Re-grade stored traces in place (no model calls). Handles both trace shapes:
    stream-json (`result_event`) and the earlier single-envelope json (`envelope`)."""
    for vd in sorted(p for p in out.iterdir() if p.is_dir()):
        oks, errs = [], []
        traced = set()
        # The run's intended model is not the agent file's CURRENT model (it may have changed since):
        # an explicit @model variant names it; otherwise a run is eligible when one model family
        # served every call, as a live run's assertion would have required.
        want = vd.name.split("@", 1)[1] if "@" in vd.name else None
        for tf in sorted((vd / "traces").glob("*.json")):
            t = json.loads(tf.read_text(encoding="utf-8"))
            key = (t["case"], t["rep"])
            traced.add(key)
            row = {k: t[k] for k in ("case", "rep", "variant")} | {"wall_s": t.get("wall_s")}
            if "timeout_s" in t:
                errs.append({**row, "class": "timeout"})
                continue
            result = t.get("result_event") or t.get("envelope")
            # same eligibility as a live run, so a regrade never moves an attempt into the score
            if not isinstance(result, dict) or t.get("rc"):
                errs.append({**row, "class": "harness"})
                continue
            served = sorted((result.get("modelUsage") or {}).keys())
            fams = {f for m in served for f in ("haiku", "sonnet", "opus") if f in m}
            if not served or len(fams) != 1 or (want and want not in fams):
                errs.append({**row, "class": "served_model_mismatch", "served": served})
                continue
            if result.get("is_error"):
                errs.append({**row, "class": "harness", "detail": str(result.get("result"))[:400]})
                continue
            kind, r = grade_trace(t["case"], t, row, served, result)
            (oks if kind == "ok" else errs).append(r)
        # attempts that died before writing a trace exist only in the old errors file: keep them
        old = vd / "errors.jsonl"
        if old.exists():
            for line in old.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                if (e.get("case"), e.get("rep")) not in traced:
                    errs.append(e)
        for name, items in (("results.jsonl", oks), ("errors.jsonl", errs)):
            (vd / name).write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    print(json.dumps(summarise(out), ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--probe", action="store_true", help="prove --agents overrides the user-level agent")
    ap.add_argument("--regrade", default=None, help="re-grade an existing out dir from its traces")
    ap.add_argument("--variants", default="baseline")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.regrade:
        return regrade(Path(a.regrade))
    out = Path(a.out or tempfile.mkdtemp(prefix="golden-exec-out-"))
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; use a fresh dir (or --regrade it)")
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="golden-exec-agents-"))
    variants = ["probe"] if a.probe else [v.strip() for v in a.variants.split(",") if v.strip()]
    cases = [c.strip() for c in a.cases.split(",") if c.strip()][: 1 if a.probe else None]
    reps = 1 if a.probe else a.reps
    agents = {v: build_agents_json(v, tmp) for v in variants}
    jobs = [(v, c, k) for v in variants for c in cases for k in range(1, reps + 1)]
    print(f"resolved scope: {len(variants)} variant(s) x {len(cases)} case(s) x {reps} rep(s) = {len(jobs)} runs -> {out}", flush=True)
    probe_rows = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_once, v, c, k, out, agents[v][0], agents[v][1]): (v, c, k) for v, c, k in jobs}
        for fu in cf.as_completed(futs):
            v, c, k = futs[fu]
            kind, row = fu.result()
            vd = out / v
            vd.mkdir(parents=True, exist_ok=True)
            with (vd / ("results.jsonl" if kind == "ok" else "errors.jsonl")).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            probe_rows.append(row)
            tag = row.get("grade", {}).get("pass") if kind == "ok" else row.get("class")
            print(f"  {v:14s} {c:20s} rep{k}: {kind} {tag} {row.get('verdict', '')}", flush=True)
    if a.probe:
        wired = any(r.get("probe") == "PROBE-WIRED" for r in probe_rows)
        print("PROBE:", "WIRED (--agents prompt reached the model)" if wired else "NOT WIRED")
        return 0 if wired else 2
    print(json.dumps(summarise(out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
