"""Validator-output checks: JSON sanity, verdicts, methodology, trace schema.

Three checks live here:
  - check_validator_outputs: every validator named in validation-log.md has
    a JSON output file with parseable JSON + verdict + (for numerical
    validators) methodology declaration. The biggest single check in
    handoff-precheck: ~130 lines including in-function constants.
  - check_findings_dispositioned: every confirmed Medium+ finding in the
    current iteration's latest validator outputs is fixed, ruled out of
    scope, or waived on the record; not parked in handoff §7/§11.
  - check_trace_schema: delegate to trace-schema-check.py for ux_heavy
    traces/*.json validation.
"""

from __future__ import annotations

import json
import re
import sys
from itertools import pairwise
from pathlib import Path

from .common import read_iteration_counter, run


# Validators that are recommended but not strictly required — missing output -> warn, not fail
OPTIONAL_VALIDATORS = {"test-reviewer", "documentation-reviewer", "prompt-reviewer", "feasibility-assessor"}


def check_validator_outputs(eng: Path) -> dict:
    """Every validator named in validation-log.md must have a JSON output file."""
    log = eng / "validation-log.md"
    if not log.exists():
        return {"name": "validator-outputs", "status": "skip", "detail": "validation-log.md not present"}
    text = log.read_text(encoding="utf-8")

    # Find every '### {name}' block. Validator agent names are lowercase-hyphenated
    # (code-reviewer, security-auditor, skeptic, ...); filtering to name.islower()
    # excludes prose section headings like "### Phase 6a" / "### Transport note"
    # that the bare regex mis-counted as phantom validators (2026-05-30 field test).
    # A validator agentType is lowercase-hyphenated and never contains a slash. A
    # slash-command token (`/critique`, `/design-review`) is NOT a validator agentType —
    # it can never produce a {name}-iter-N.json output file, so listing one in
    # validation-log.md must not be counted as a REQUIRED validator (else guaranteed
    # false-fail). validation-pipeline historically listed `/critique` as a mandatory
    # design validator (recorded in the skill-evolution log). islower()
    # also excludes prose headings like "### Phase 6a" (2026-05-30 field test).
    blocks = [
        name
        for name in re.findall(
            r"^###\s+(?P<name>[\w\-./]+).*?(?=^###\s|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if name.islower() and "/" not in name
    ]
    if not blocks:
        return {"name": "validator-outputs", "status": "skip", "detail": "no validators logged yet"}

    outputs_dir = eng / "validation-outputs"
    if not outputs_dir.exists():
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": f"{len(blocks)} validators logged but engagement/validation-outputs/ missing entirely — runs unverifiable",
            "fix": "Lead must capture each validator's JSON return into validation-outputs/{name}-iter-N-{timestamp}.json.",
        }

    # For each validator name, expect at least one matching output file
    files = list(outputs_dir.glob("*.json"))
    missing_critical = []
    missing_optional = []
    for name in set(blocks):
        if not any(f.name.startswith(name) for f in files):
            if name in OPTIONAL_VALIDATORS:
                missing_optional.append(name)
            else:
                missing_critical.append(name)

    if missing_critical:
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": f"required validators logged without output file: {missing_critical}",
            "fix": "Capture missing validator JSON returns into validation-outputs/.",
        }
    if missing_optional:
        return {
            "name": "validator-outputs",
            "status": "warn",
            "detail": f"optional validators logged without output file: {missing_optional} (not blocking, but recommended)",
            "fix": "Optional validators (test-reviewer, prompt-reviewer, etc.): capture if you ran them.",
        }

    # Sanity: each output file is parseable JSON AND has structural fields
    bad_json = []
    no_verdict = []
    bad_verdict = []
    no_methodology = []
    # Validator verdicts (methodology validators) + adversary verdicts (consilium roles).
    # Updated 2026-05-09 after agent-grep audit: collected ALL status values used by validator
    # agents (security, accessibility, code-reviewer, completeness, feasibility, pre/post-deploy,
    # test-reviewer, interview-checker, etc). Each validator emits ONE of these.
    valid_verdicts = {
        # Approval-style validators
        "approved", "approved_with_suggestions",
        # Rework-needed style
        "changes_required", "needs_improvement", "needs_more",
        # Hard block
        "blocked",
        # Binary check style
        "pass", "passed", "fail", "failed", "clean",
        # Coverage / gating
        "complete", "warning", "not_verifiable",
        # Adversary verdicts (consilium roles)
        "satisfied", "rework_required", "suspicious_too_clean",
        # canonical verdicts (validator_lg.canonicalize_validator_output)
        "approved_with_caveats", "suspicious", "skipped",
    }
    # Validators where methodology declaration is OBLIGATORY (numerical / formula-driven)
    methodology_required = {
        "accessibility-validator", "performance-validator", "security-auditor",
        "ux-review", "anti-pattern-detector",
    }
    # Adversary roles emit a different schema (preliminary/2-pass) — distinguish for checks
    adversary_roles = {
        "peer-opus", "codex-blind", "codex-informed", "sonnet-scoped", "haiku-scoped",
    }
    for f in files:
        # Skip Pass-1 preliminary files — they don't have a verdict (intentional)
        if "-preliminary-" in f.name:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            bad_json.append(f.name)
            continue
        verdict = data.get("verdict") or data.get("status")
        if verdict is None:
            no_verdict.append(f.name)
        elif str(verdict).lower() not in valid_verdicts:
            bad_verdict.append(f"{f.name}: verdict={verdict!r}")
        # Methodology declaration check — only for validators where it matters
        # Skip for adversary roles (their schema has _two_pass / _invocation instead)
        validator_name = data.get("validator", "") or data.get("reviewer_role", "") or f.stem.split("-iter-")[0]
        if validator_name in adversary_roles:
            continue
        if validator_name in methodology_required:
            if not data.get("methodology") and not data.get("metrics", {}).get("methodology"):
                no_methodology.append(f.name)

    problems = []
    warnings = []
    if bad_json:
        problems.append(f"unparseable JSON: {bad_json}")
    if no_verdict:
        problems.append(f"missing 'verdict' (or 'status') field: {no_verdict}")
    if bad_verdict:
        problems.append(f"invalid verdict values: {bad_verdict}")
    if no_methodology:
        warnings.append(f"missing 'methodology' field (formula/standard): {no_methodology}")

    if problems:
        return {
            "name": "validator-outputs",
            "status": "fail",
            "detail": "; ".join(problems),
            "fix": "Each validator-output JSON needs a recognized 'verdict' (or 'status'): approved | approved_with_caveats | changes_required | blocked | satisfied | rework_required | suspicious | skipped (full vocabulary in validation-pipeline skill + validator_lg canonical map).",
        }
    if warnings:
        return {
            "name": "validator-outputs",
            "status": "warn",
            "detail": "; ".join(warnings),
            "fix": "Add 'methodology' field to numerical/formula-driven validator outputs (e.g. 'WCAG 2.1 luminance ratio 4.5:1'). Director needs this for re-run convergence.",
        }

    return {"name": "validator-outputs", "status": "pass", "detail": f"{len(set(blocks))} validators, {len(files)} output files, all valid JSON with verdict + methodology"}


# Severities that may not reach handoff without a recorded disposition. Validators emit
# both scales (medium/high/critical and minor/major/critical); low/minor/info/nit stay advisory.
BLOCKING_SEVERITIES = {"medium", "major", "high", "critical", "blocker", "severe", "important"}

# Consilium roles run AFTER handoff and are adjudicated by the manager, not dispositioned
# by the lead, so their outputs are not this check's business.
_CONSILIUM_ROLES = ("peer-opus", "codex-blind", "codex-informed", "sonnet-scoped", "haiku-scoped")

_OUTPUT_NAME_RE = re.compile(r"^(?P<name>.+?)-iter-(?P<iter>\d+)-(?P<rest>.+)\.json$")

# A disposition word near a finding id. Deliberately absent: "deferred", "backlog",
# "follow-up". Parking a finding is the failure this check exists for; a deferral counts
# only as an out-of-scope ruling or a waiver (engagement-protocol, "acceptable form of deferral").
_DISPOSITION_RE = re.compile(
    r"\b(fixed|resolved|waived|waiver|out[- ]of[- ]scope|false[ _-]positive|refuted|not reproduced)\b",
    re.IGNORECASE,
)
_DISPOSED_STATUSES = {
    "fixed", "resolved", "waived", "out_of_scope", "out-of-scope",
    "false_positive", "false-positive", "refuted", "not_reproduced",
}
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
# Phrasings that mention a disposition word without disposing anything: negations ("not fixed",
# "has not been fixed", "isn't fixed", "not a false positive") and future / partial forms ("to be
# fixed", "will be resolved", "partially fixed"; review 2026-10-10). "not reproduced" stays a
# disposition (it means refuted).
_NEGATED_RE = re.compile(
    r"\bnot\s+(?:(?:yet|been|fully|completely|entirely|really)\s+)*(?:fixed|resolved|waived|addressed)\b"
    r"|\b(?:is|was|are|were|has|have)n'?t\s+(?:been\s+)?(?:fully\s+)?(?:fixed|resolved|waived|addressed)\b"
    r"|\bnot\s+(?:a\s+)?false[ _-]positive\b|\bnot\s+out[- ]of[- ]scope\b"
    r"|\bun(?:fixed|resolved)\b|\bstill\s+open\b"
    r"|\b(?:to|will|would|should|must|shall|could|can|may|might|needs?\s+to|going\s+to|planned\s+to|scheduled\s+to)\s+be\s+"
    r"(?:fully\s+)?(?:fixed|resolved|waived|addressed)\b"
    r"|\b(?:partially|partly|half)[ -](?:fixed|resolved|addressed)\b",
    re.IGNORECASE,
)
_SCOPE_RE = re.compile(r"\b(waived|waiver|out[- ]of[- ]scope)\b", re.IGNORECASE)
_PARKED_RE = re.compile(r"\b(backlog|deferred|defer|follow[- ]?up|later|todo)\b", re.IGNORECASE)


def _latest_outputs(outputs_dir: Path, iteration: int | None) -> tuple[int | None, dict]:
    """Latest final output per validator for the current iteration.

    Timestamps come in two shapes in the corpus (`20260603T135725Z` and `20260603-162718`);
    plain filename order sorts '-' before 'T' and picks the older file, so order by digits.
    """
    parsed = []
    for f in outputs_dir.glob("*.json"):
        m = _OUTPUT_NAME_RE.match(f.name)
        if not m:
            continue
        name, rest = m.group("name"), m.group("rest")
        if name.startswith(_CONSILIUM_ROLES) or any(t in rest for t in ("preliminary", "pass1", "pass2")):
            continue
        parsed.append((name, int(m.group("iter")), re.sub(r"\D", "", rest), f))
    if not parsed:
        return iteration, {}
    if iteration is None:
        iteration = max(p[1] for p in parsed)
    latest: dict[str, tuple[str, Path]] = {}
    for name, it, stamp, f in parsed:
        if it == iteration and (name not in latest or stamp > latest[name][0]):
            latest[name] = (stamp, f)
    return iteration, {name: f for name, (_, f) in latest.items()}


# A boundary is a heading that starts with "Iteration N" ("## Iteration 2 — 2026-05-07",
# "## **Iteration 2**", "## Iteration 2 rework"), unless it is a recap / summary of another one
# ("### Iteration 1 — recap" inside iteration 2).
_ITER_HEAD_RE = re.compile(
    r"^#{1,6}[ \t]*[*_]*[ \t]*Iteration[ \t]+(\d+)\b(?![^\n]*\b(?:recap|summary|retro(?:spective)?|history)\b)",
    re.MULTILINE | re.IGNORECASE)
_TABLE_RULE_RE = re.compile(r"^[\s|:-]*$")
_STALE_SLACK_S = 120  # a copy or checkout writes the log and the outputs seconds apart, a re-run is minutes
# Id-free lines that may create a ruling: a label ending in ":" ("Fixed:", "Out of scope per
# criteria.md:") or a line that opens with a ruling keyword ("**Adjudication: OUT-OF-SCOPE.** ...").
# Prose that merely contains a disposition word does not: the engine writes "adversarial-verify:
# 2 confirmed / 1 refuted of 3" into every validator block, and "refuted" used to rule the
# lead's lines below it (review 2026-10-10).
_LABEL_RE = re.compile(r"^\s*(?:[-*]\s*)?[*_]*[^:\n]{0,80}:\s*[*_]*\s*$")
_RULING_START_RE = re.compile(r"^\s*(?:[-*]\s*)?[*_]*\s*(?:adjudication|ruling|disposition|resolution|decision)\b",
                              re.IGNORECASE)
# An id-free LABEL that announces open items ends the ruling above it ("Open:", "Remaining:",
# "**Pending**:"). Only label-shaped lines count: in an accepted engagement's log a
# scope ruling is followed by "Itemised:" and by wrapped continuation lines that end in
# "→ backlog.", and those must keep the ruling.
_OPEN_LABEL_RE = re.compile(
    r"^\s*(?:[-*]\s*)?[*_]*\s*(?:still\s+)?(?:open|remaining|pending|outstanding|to-?do|needs?\s+work|not\s+yet\b[^:]*|"
    r"unaddressed|unresolved|deferred|backlog|follow[- ]?ups?)\b[^:\n]{0,40}:\s*[*_]*\s*$", re.IGNORECASE)


def _current_iteration_text(text: str, iteration: int | None) -> str:
    """Only the `Iteration <current>` region(s) of validation-log.md.

    Index ids repeat across iterations, so an iter-1 `code-reviewer#0: FIXED` would cover a
    different iter-2 `#0` (Codex review 2026-10-09). engagement-protocol already puts rework
    under a new `## Iteration N` section; when the log has such headings, a disposition counts
    only inside the current one. A log with none was written fresh by the engine for this
    run, so all of it is current.
    """
    heads = list(_ITER_HEAD_RE.finditer(text))
    if not heads or iteration is None:
        return text
    bounds = [h.start() for h in heads[1:]] + [len(text)]
    return "\n".join(text[h.start():end] for h, end in zip(heads, bounds) if int(h.group(1)) == iteration)


def _cites(own_id: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w-])" + re.escape(own_id) + r"(?![\w])", text))


def _disposed_lines(texts: list[str], own_ids: set[str] = frozenset()) -> list[str]:
    """Lines whose finding ids count as dispositioned.

    The LINE is the unit (Codex review 2026-10-09: a section-wide match let
    `#0: FIXED` carry `#1: deferred to backlog`, and `not fixed` matched `fixed`):
      - a line with a disposition word, not negated, disposes the ids on it;
      - a ruling line with NO ids (a heading or "Adjudication: OUT-OF-SCOPE.") rules the ids
        below it in the same section, so a lead can rule a group once and itemise it
        (seen in an accepted engagement). A line that parks its id
        ("-> backlog", "deferred") inherits only a scope or waiver ruling, never "fixed":
        out-of-scope-then-backlog is a coherent ruling, fixed-then-backlog is not;
      - a negated or still-open line inherits nothing;
      - only a heading, a label ending in ":" or a line opening with a ruling keyword creates a
        ruling; it lasts through its own paragraph, labels without a disposition ("Itemised:"),
        table rows and indented continuation lines; a label announcing open items ("Open:",
        "Remaining:"), a negated line or a new unindented prose paragraph ends it
        (review 2026-10-10: `Fixed: / #0 / Open: / #1` disposed of #1, and the engine's
        "adversarial-verify: ... refuted ..." line ruled every lead line below it);
      - an id line is judged per clause, split on `;` and on a comma before another id, so
        `#0: FIXED; #1: deferred` disposes only #0, while `#0, #2: fixed` still covers both;
      - a direct disposition next to a parking word ("fixed in a follow-up") counts only for a
        scope / waiver ruling.
    """
    kept = []
    for text in texts:
        starts = [0] + [m.start() for m in _HEADING_RE.finditer(text)] + [len(text)]
        for a, b in pairwise(starts):
            ruling, in_par = None, False  # ruling in force, and whether we are in its paragraph
            for line in text[a:b].splitlines():
                if not line.strip():
                    in_par = False
                    continue
                has_ids = bool(_INDEX_ID_RE.search(line)) or any(_cites(own, line) for own in own_ids)
                if not has_ids:
                    if _TABLE_RULE_RE.match(line):
                        continue
                    negated = bool(_NEGATED_RE.search(line))
                    creates = (line.lstrip().startswith("#") or _LABEL_RE.match(line) or _RULING_START_RE.match(line))
                    if creates and _DISPOSITION_RE.search(line) and not negated:
                        kind = "scope" if _SCOPE_RE.search(line) else "other"
                        ruling = "scope" if "scope" in (ruling, kind) else kind
                        in_par = True
                    elif negated or _OPEN_LABEL_RE.search(line):  # "Not fixed:", "Open:", "Remaining:"
                        ruling = None
                    elif _LABEL_RE.match(line) or line.lstrip().startswith("|") or line[:1] in " \t" or in_par:
                        pass  # "Itemised:", a table row, a wrapped continuation, the ruling's own paragraph
                    else:
                        ruling = None  # a new prose paragraph
                    continue
                for clause in _CLAUSE_SPLIT_RE.split(line):
                    if not (_INDEX_ID_RE.search(clause) or any(_cites(own, clause) for own in own_ids)):
                        continue
                    if _NEGATED_RE.search(clause):
                        continue
                    direct = _DISPOSITION_RE.search(clause) and (
                        not _PARKED_RE.search(clause) or _SCOPE_RE.search(clause))
                    if direct or ruling == "scope" or (ruling and not _PARKED_RE.search(clause)):
                        kept.append(clause)
    return kept


# `deploy-reviewer#3/#4`, `infrastructure-reviewer#1/#2/#3`, `skeptic#0, #2`: leads list
# several indices after one name, and only the first carries it.
# Left-bounded and case-insensitive ("Code-reviewer#0" is code-reviewer#0, not "ode-reviewer#0");
# a comma continues the list only with "#" ("skeptic#0, #2"), so "code-reviewer#3, 4 tests" is #3.
_INDEX_ID_RE = re.compile(r"(?<![\w-])([A-Za-z][\w-]*)#(\d+)((?:\s*/\s*#?\d+|\s*,\s*#\d+)*)")
_CLAUSE_SPLIT_RE = re.compile(r";|,\s*(?=[A-Za-z][\w-]*#\d)")


def _index_ids(text: str) -> set[str]:
    ids = set()
    for m in _INDEX_ID_RE.finditer(text):
        for n in [m.group(2), *re.findall(r"\d+", m.group(3))]:
            ids.add(f"{m.group(1).lower()}#{int(n)}")
    return ids


def check_findings_dispositioned(eng: Path) -> dict:
    """A confirmed Medium+ validator finding may not reach handoff without a disposition.

    The adversarial-verify step drops refuted findings before the output is written
    (engagement-workflow validate phase), so every Medium+ finding left in a validator's
    latest output for the current iteration is a confirmed one. Each needs one of:
      - a newer re-run of the same validator in this iteration that no longer reports it;
      - a `status` on the finding itself (fixed / resolved / waived / out_of_scope / ...);
      - its id cited in validation-log.md or scope-sync.md inside a section that records a
        disposition (fixed, out of scope, waiver, false positive).
    The id is the finding's own `id`, else `{validator}#{index}` into its findings list, the
    form leads already cite. handoff.md does not count: listing a confirmed Medium in §7 or
    §11 is the silent deferral this check closes.

    Index ids repeat across iterations: when validation-log.md carries `Iteration N` headings,
    only the current iteration's region counts (see _current_iteration_text).
    """
    outputs_dir = eng / "validation-outputs"
    if not outputs_dir.exists():
        return {"name": "findings-dispositioned", "status": "skip", "detail": "no validation-outputs/ yet"}
    iteration, latest = _latest_outputs(outputs_dir, read_iteration_counter(eng))
    if not latest:
        return {"name": "findings-dispositioned", "status": "skip",
                "detail": f"no validator outputs for iteration {iteration}"}

    loaded = {}
    for name, f in sorted(latest.items()):
        try:
            loaded[name] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # unparseable JSON is validator-outputs' failure, not this one's
            continue
    # A finding's own id is only usable when it is distinctive: a bare "2" matches any digit.
    own_ids = {str(x["id"]) for d in loaded.values() if isinstance(d, dict)
               for k in ("findings", "criticalIssues", "suggestions") for x in (d.get(k) or [])
               if isinstance(x, dict) and x.get("id") and len(str(x["id"])) >= 3 and not str(x["id"]).isdigit()}
    # Index ids repeat across iterations. From iteration 2 on, a record that is older than this
    # iteration's outputs and has no `Iteration N` sections was written for an earlier iteration,
    # so its index ids do not count (own ids still do). The engine rewrites validation-log.md each
    # run and a lead appends after it, so a current log is always newer than the outputs.
    # Judged per validator: re-running one validator after the lead wrote the log invalidates only
    # that validator's index ids, not every other validator's dispositions (review 2026-10-10).
    output_mtime = {name.lower(): f.stat().st_mtime for name, f in latest.items()}
    records = []  # (text, mtime, may an old record lend index ids: False when it is unheaded)
    log = eng / "validation-log.md"
    if log.exists():
        text = log.read_text(encoding="utf-8-sig")
        headed = bool(_ITER_HEAD_RE.search(text))
        records.append((_current_iteration_text(text, iteration), log.stat().st_mtime, headed))
    sync = eng / "scope-sync.md"
    if sync.exists():  # a waiver is a standing ruling, but its index ids name one iteration's list
        records.append((sync.read_text(encoding="utf-8-sig"), sync.stat().st_mtime, False))
    disposed_text = "\n".join(_disposed_lines([t for t, _, _ in records], own_ids))
    # A record older than its validator's latest output (beyond a copy / checkout jitter) was written
    # against an earlier list of findings, so its index ids name different findings now. This holds
    # for headed logs too (Codex review 2026-10-14: a validator re-run later in iteration 2 kept the
    # old `#0: FIXED`); `Iteration N` regions only narrow WHICH text counts.
    disposed_index_ids = set()
    for text, mtime, _headed in records:
        for fid in _index_ids("\n".join(_disposed_lines([text], own_ids))):
            if mtime + _STALE_SLACK_S >= output_mtime.get(fid.split("#")[0], 0):
                disposed_index_ids.add(fid)

    open_findings = []
    total = 0
    for name, data in loaded.items():
        if not isinstance(data, dict):
            continue
        # The reviewer's own schema is criticalIssues + suggestions (agents/code-reviewer.md); some
        # outputs carry it with `findings` empty. Index ids run through
        # findings, then criticalIssues, then suggestions, and the fail detail prints each id.
        items = [x for k in ("findings", "criticalIssues", "suggestions") for x in (data.get(k) or [])]
        for i, x in enumerate(items):
            if not isinstance(x, dict):
                continue
            sev = str(x.get("severity", "")).strip().lower()
            if sev not in BLOCKING_SEVERITIES:
                continue
            total += 1
            if str(x.get("status", "")).strip().lower() in _DISPOSED_STATUSES:
                continue
            if f"{name}#{i}" in disposed_index_ids:
                continue
            own_id = str(x.get("id") or "")
            if own_id in own_ids and _cites(own_id, disposed_text):  # only distinctive ids (see own_ids)
                continue
            where = x.get("file") or x.get("location") or ""
            text = next((str(x[k]) for k in ("message", "issue", "title", "description", "problem") if x.get(k)), "")
            open_findings.append(f"{name}#{i} ({sev}) {where}: {text[:80]}".strip())

    if open_findings:
        shown = open_findings[:8]
        more = f" (+{len(open_findings) - 8} more)" if len(open_findings) > 8 else ""
        return {
            "name": "findings-dispositioned",
            "status": "fail",
            "detail": f"iteration {iteration}: {len(open_findings)} confirmed Medium+ finding(s) without a disposition: {shown}{more}",
            "fix": "Fix and re-run the validator, or record the disposition in validation-log.md (under "
                   f"`## Iteration {iteration}` once the log has iteration sections) citing the id "
                   "(`code-reviewer#3: FIXED in <commit>`, or out of scope per criteria.md), or a waiver in scope-sync.md. "
                   "Listing it in handoff §7/§11 is not a disposition (engagement-protocol: the only acceptable deferral "
                   "is criteria.md out-of-scope or a director-approved scope-sync.md waiver).",
        }
    return {"name": "findings-dispositioned", "status": "pass",
            "detail": f"iteration {iteration}: {total} Medium+ finding(s) across {len(latest)} validators, all dispositioned"}


def check_trace_schema(eng: Path, scripts_dir: Path, ux_heavy: str) -> dict:
    """Validate trace JSON files against schema. Skipped if ux_heavy=false or no traces."""
    if ux_heavy not in {"true", "minor"}:
        return {"name": "trace-schema", "status": "skip", "detail": f"ux_heavy={ux_heavy}, traces not applicable"}
    traces_dir = eng / "traces"
    if not traces_dir.exists() or not list(traces_dir.rglob("*.json")):
        if ux_heavy == "true":
            return {"name": "trace-schema", "status": "fail", "detail": "ux_heavy=true requires traces/ but none present"}
        return {"name": "trace-schema", "status": "skip", "detail": f"no traces (ux_heavy={ux_heavy} permits)"}
    code, out = run([sys.executable, str(scripts_dir / "trace-schema-check.py"), str(traces_dir), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "trace-schema", "status": "pass", "detail": f"{data.get('total', 0)} traces valid"}
        bad = [f["file"] for f in data.get("files", []) if f.get("status") == "fail"]
        return {
            "name": "trace-schema",
            "status": "fail",
            "detail": f"{data.get('fail_count')} traces violate schema: {bad}",
            "fix": "Conform traces to engagement-protocol §Trace JSON schema (action/selector/expected/observed/verdict).",
        }
    except json.JSONDecodeError:
        return {"name": "trace-schema", "status": "fail", "detail": f"trace-schema-check error: {out[:200]}"}
