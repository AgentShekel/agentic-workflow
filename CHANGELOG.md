# Changelog

All notable changes to agentic-workflow.

## v0.2.5 — 2026-05-28 (Doc refresh — engagement_lg.py architectural section + SkillOpt symmetry)

Documentation-only release. After v0.2.4 shipped the Windows-compatibility bugfix, an audit of the four narrative docs (`README.md`, `README.ru.md`, `ARCHITECTURE.md`, `ARCHITECTURE.ru.md`) surfaced eight gaps where structural changes from v0.2.2 / v0.2.3 / v0.2.4 had been mentioned in version banners but had not propagated into the corresponding catalog sections. All eight closed in this release. **Zero code changes.**

### Gaps closed

1. **v0.2.4 banner** added on top of v0.2.3 in all 4 docs — Windows `.CMD` argv truncation, cp1251 encoding mojibake, and `consilium_synth_completed` verdict-map fix, with the three-engine scope and the `--invoker mock` latency caveat.
2. **"Two LangGraph engines" → "Three"** in `README.md`, `README.ru.md`, and the 5-layer Mermaid diagram of both `ARCHITECTURE.md` and `ARCHITECTURE.ru.md` (`O3[Validator bridge]` joined by `O4[Engagement bridge]`; renumbered `O5`–`O8`; classDef list updated to include `O8`).
3. **`engagement_lg.py` row added to the main scripts table** (§5) in `ARCHITECTURE.md` and `ARCHITECTURE.ru.md` — full description: 11 nodes including `_barrier_dispatch_node`, 3 HITL pause points (`criteria_lock` / `danger_gate` / `human_directive`), three execution modes (`--dry-run` / `--mock` / `--real`), subprocess delegation to `validator_lg.py` and `adversary_lg.py`, 3 new payload types (`engagement_completed`, `phase_skipped`, `dryrun_marker`).
4. **`engagement_lg.py` description added to the `Scripts` section of both READMEs** — same shape as the ARCHITECTURE table row, lighter prose.
5. **NEW §8.5 "Engagement-level orchestration (engagement_lg.py)"** in both ARCHITECTURE docs — own Mermaid `flowchart TB` with the full `START → INT → CL → PLAN → DG → DISP → (Send) SPEC → BAR → VAL → CONS → HD → MGR → ARCH → END` graph including rework-loop edges and REJECT_NOW short-circuit. Sub-sections: State (EngagementState 20-field TypedDict, `specialist_results` Annotated[list, operator.add] reducer for parallel Send branches, `mock` bool propagation), Three execution modes (decision table), Subprocess delegation vs sub-graphs (4-point rationale + open promotion path), HITL pause points (3-row table mirroring HITL interrupt/4b), Event ledger payload types added.
6. **`lib/precheck/` added to Shared libraries** in both ARCHITECTURE docs (was singular `lib/ledger.py` only). 8 topic modules enumerated: `common` / `criteria` / `handoff` / `iteration` / `validators` / `acceptance` / `danger` + `__init__` re-exports. Clarification that `handoff-precheck.py` is now CLI/dispatcher-only and imports from the package; byte-identical JSON output to the pre-refactor monolith.
7. **`SkillOpt golden sets` section added to `README.md`** (parity with `README.ru.md` which had it since v0.2.1) — 3-domain table + dry-run validation reference.
8. **`Director as system-optimizer` subsection expanded** in both READMEs (5 lines → ~15 lines) — full 4-step loop description: Reflect (cluster signals + read negative memory) → Codex proposes (cross-family, bounded edits L = 4–6 patches × ≤10 lines) → Golden-set gate (9 scenarios total) → Promote / reject (with rejection-buffer feedback). Trigger threshold (≥3 same-class signals) made explicit. Judge-only / never-per-engagement / human-as-commons-maintainer constraints stated.

### Files changed

```
README.md          | edited — v0.2.4 banner + 3 engines + SkillOpt golden section + expanded SkillOpt loop description
README.ru.md       | edited — v0.2.4 banner + 3 engines + expanded SkillOpt loop description
ARCHITECTURE.md    | edited — v0.2.4 banner + 5-layers mermaid + engagement_lg.py scripts row + lib/precheck/ + NEW §8.5
ARCHITECTURE.ru.md | edited — same as EN
CHANGELOG.md       | this entry
```

### What this release does NOT do

- No code changes.
- No new files in `scripts/`, `agents/`, `skills/`.
- No new dependencies.
- No banner-stack collapse (v0.2 / v0.2.1 / v0.2.2 / v0.2.3 / v0.2.4 / v0.2.5 all kept; collapse deferred until the stack actively obstructs the reader).

## v0.2.4 — 2026-05-28 (Windows compatibility — multi-line argv + encoding + verdict-map fixes)

Bugfix release. Subscription-mode adversary smoke + S-tier dev field test on Windows surfaced three latent issues that were invisible to mock-mode testing. All three fixed in the four scripts that touch the claude CLI subprocess or consume LLM output.

### Windows `claude.CMD` multi-line argv truncation

`shutil.which("claude")` on Windows returns the npm-installed `claude.CMD` wrapper. The wrapper forwards `%*` to the underlying `claude.exe` — but **CMD line-parsing treats newlines as command separators**, so a multi-line `prompt` argv truncates at the first `\n` before `claude.exe` ever sees it. Single-line prompts (e.g., `validator_lg.py`'s `f"Run validator '{validator}' on engagement at {eng}. Output JSON only..."`) survive cleanly; multi-line prompts (`adversary_lg.py`'s ~2KB `PROMPT_PASS1_PEER`, the four-line `engagement_lg.py` lead/specialist/manager prompts) silently lose 95% of their content. The reviewer then responds with "не хватает данных" or "I'll acknowledge the system reminders but note that no actual user task has been provided" — and the engagement silently fails with "Pass 1 produced no JSON".

**Fix (4 scripts, identical pattern):** `find_claude_cmd()` / `_find_claude_cmd()` resolves `.CMD` → underlying `claude.exe` via the standard npm wrapper layout `<dir>/node_modules/@anthropic-ai/claude-code/bin/claude.exe`. Falls back to `.CMD` if `.exe` is missing (degrades gracefully). Unix/macOS path unaffected (no `.CMD` ever returned).

```python
def find_claude_cmd() -> Optional[str]:
    for c in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(c)
        if p:
            if Path(p).suffix.lower() == ".cmd":
                exe = Path(p).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
                if exe.exists():
                    return str(exe)
            return p
    return None
```

Applied to `scripts/adversary_lg.py`, `scripts/validator_lg.py`, `scripts/engagement_lg.py`. Each script has its own `_find_claude_cmd` copy by historical convention; a future refactor could extract to `scripts/lib/claude_path.py`.

### `subprocess.run(text=True)` encoding (cp1251 mojibake on Russian locale)

Independent issue: Python's `subprocess.run(..., text=True)` without `encoding=` uses `locale.getpreferredencoding()`, which on Russian Windows is `cp1251`. A reviewer (claude, codex) returning UTF-8 Russian — likely in any agency engagement that mixes the project's Russian protocol-language with the reviewer's natural response — gets decoded as cp1251 → mojibake (`РџСЂРёРЅСЏС‚Рѕ` instead of `Принято`). Confirmed via the first adversary smoke's `peer-opus-iter-1-pass1-*.raw.txt` artefact.

**Fix:** add `encoding="utf-8", errors="replace"` to every `subprocess.run(..., text=True)` call. Applied to 10 sites across the four scripts:

| File | Sites | Roles |
|---|---|---|
| `scripts/adversary_lg.py` | 5 | `_invoke_claude`, `_invoke_codex`, consilium-synth call, consilium-present call, human-directive call |
| `scripts/validator_lg.py` | 2 | `invoke_validator` (claude --agent), human-directive call |
| `scripts/engagement_lg.py` | 6 | size-detect, _invoke_lead, _invoke_specialist, _invoke_manager, validator_lg subprocess, adversary_lg subprocess, archive subprocess |
| `scripts/lib/precheck/common.py` | 1 | generic `run()` subprocess helper |

`errors="replace"` chosen over `errors="strict"` so a single malformed byte in a 100k stream doesn't crash the whole pipeline. Malformed sequences surface as `�` replacement characters — visible in the output rather than corrupting downstream parsing.

### `adversary_lg.py` `consilium_synth_completed` verdict normalization

After subscription-mode subprocess smoke testing, the ledger surfaced `WARN: ledger emit failed (consilium_synth_completed): verdict must be one of {None, 'N/A', 'ACCEPT', 'REJECT', 'DIRECTED'}, got 'satisfied'`. `_make_finalize_node` was passing the raw natural verdict (`satisfied` / `rework_required` / `suspicious_too_clean`) from `consilium-synth.py` straight into `_ledger_emit(verdict=...)`, which fails the ledger schema validation. The synth still wrote `consilium-summary.md` correctly; only the corresponding ledger event was dropped.

**Fix:** inline `VERDICT_MAP` mirror of the per-role mapping already used in `_make_run_role_node`:

```python
_agg = data.get("aggregate_verdict")
_ledger_verdict = {
    "satisfied": "ACCEPT",
    "rework_required": "REJECT",
    "suspicious_too_clean": "REJECT",
}.get(_agg, "N/A")
_ledger_emit(
    "consilium_synth_completed",
    node="finalize",
    payload={
        "summary_path": data.get("summary_path"),
        "aggregate_verdict": _agg,  # raw, for downstream consumers
        "unique_findings": data.get("unique_findings"),
        "tier": tier,
    },
    verdict=_ledger_verdict,  # normalized, for ledger schema
)
```

After fix, mock re-smoke confirms `consilium_synth_completed verdict=ACCEPT` is now emitted and ledger validation passes.

### Validation

- **First adversary smoke**: synthetic M-tier engagement, `python adversary_lg.py /tmp/adv-smoke --consilium M --json --no-checkpoint` end-to-end with subscription claude CLI. peer-opus returned `verdict=satisfied` with 2 minor real findings (insights about the test harness design — not rubber-stamp), Pass 1 = 89.5s, consilium-summary.md correctly written, 5 events end-to-end in events.jsonl + 1 more after the verdict-map fix (6 total).
- **First S-tier dev field test**: real engagement on an internal FastAPI project. Cascade: `agency-intake → dev-lead (subprocess) → dev-fullstack-engineer (subprocess) → code-reviewer (subprocess) → handoff-precheck → human verdict ACCEPT`. Real diff: 15 LOC net in one route module (`GET /resource/{id}/sub-resource` paginated to mirror the project's house list pattern). All three patches verified working in cascade. Critical secondary signal: `dev-lead`'s first `handoff-precheck` failed on `handoff-paths` (events.jsonl event #12: `precheck_failed verdict=REJECT`), lead self-corrected without operator intervention, iter-3 passed clean — proves reflection-loop is functional in real cascade.

### Latent risk closed

Pre-v0.2.4, all `--invoker mock` smoke tests passed because mock invoker never spawned a subprocess. Real subscription mode was untested on Windows until this session. validator_lg's 2026-05-28 "smoke PASSED" memory note was misleading — single-line `--agent X PROMPT` invocation never hit the bug; the latent risk was in any future multi-line use across all three LangGraph engines. Now fixed in all three.

### What's NOT in this release

- No agent or skill content changes.
- No new ledger payload types.
- No new CLI flags.
- No documentation restructuring.
- Stripped install behavior unchanged (`lib.ledger` import guard preserves zero-dep fallback).
- The `find_claude_cmd` extraction to a shared `scripts/lib/claude_path.py` is deferred (would couple all three LG engines through one more import; the duplicated function body is currently 8 lines × 3 = 24 lines of acceptable duplication).

### Files changed

```
scripts/adversary_lg.py        | 37 +++++++++++++++++++++++++++++--------
scripts/engagement_lg.py       | 29 ++++++++++++++++++++++-------
scripts/lib/precheck/common.py |  4 +++-
scripts/validator_lg.py        | 14 ++++++++++++--
4 files changed, 66 insertions(+), 18 deletions(-)
```

## v0.2.3 — 2026-05-28 (engagement_lg.py end-to-end + `--mock` test mode)

Same-day continuation of v0.2.2. All four remaining remaining node bodies shipped, plus an end-to-end test harness. Three execution modes now available; `--mock` lets you smoke the full graph on a box without claude CLI installed.

### dispatch + specialist Send fan-out

- **`_dispatch_node`** now does state-advance only; actual fan-out routed via `_route_after_dispatch(state) → [Send("specialist", payload), ...]` returning one Send per specialist from `state.specialists`. Empty list short-circuits to `barrier_dispatch`.
- **NEW `_specialist_node` real body** — subprocess `claude -p --agent {specialist}` with prompt asking the specialist to read criteria.md + plan.md and write `executor-reports/{specialist}.md` with `## Criteria acknowledgement` + `## Iteration N` sections.
- **NEW `_barrier_dispatch_node`** — sync point after parallel specialist Send branches; aggregates `specialist_results` (Annotated[list, operator.add] reducer), emits `barrier_passed` + single `phase_completed(dispatch)` event with ok/fail summary.
- Graph wiring: `dispatch → [Send → specialist | barrier_dispatch]; specialist → barrier_dispatch; barrier_dispatch → validate`.

### validate + consilium subprocess wiring

- **`_validate_node` real body** — `_run_validator_lg_subprocess(eng, scripts_dir, mock=False)`: subprocess `validator_lg.py {eng} --auto --json`. Parses JSON output (ok / fail counts), maps validator_lg exit code 0 + fail=0 → ACCEPT, else REJECT. On subprocess error: emits `phase_completed` with REJECT verdict but doesn't raise (validator_lg subprocess failures are recoverable).
- **`_consilium_node` real body** — `_run_adversary_lg_subprocess(eng, tier, scripts_dir, mock=False)`: subprocess `adversary_lg.py {eng} --consilium TIER --auto-synth --json`. Maps `aggregate_verdict` → ACCEPT (satisfied), REJECT (rework_required / suspicious_too_clean), DIRECTED (ambiguous). Adversary_lg writes consilium-summary.md as side effect.

### manager + archive + REJECT_NOW short-circuit

- **`_manager_accept_node` real body** — invokes `claude -p --agent {domain}-manager` via `_invoke_manager_subprocess`. Manager reads handoff + consilium + human-directive + reflections and writes canonical `### Verdict: ACCEPT|REJECT|ABORTED` line in acceptance-log.md. After subprocess returns ok, `_parse_acceptance_verdict(eng)` extracts the verdict and propagates to state.
- **REJECT_NOW short-circuit:** if `state.human_directive_decision == "REJECT_NOW"`, manager subprocess is SKIPPED entirely; verdict forced to REJECT via direct `verdict_written` ledger event. `_route_after_accept` then loops to plan (if iter_n < iter_max) or terminates at END.
- **`_archive_node` real body** — `_run_archive_subprocess(eng, scripts_dir, mock=False)`: subprocess `engagement-archive.py {eng}`. Skipped when `manager_verdict != "ACCEPT"`.

### `--mock` execution mode + end-to-end smoke

- **NEW `--mock` CLI flag** (mutually exclusive with `--real`): real graph paths but subprocess wrappers return canned artefacts instead of calling claude CLI. Enables full end-to-end testing on boxes without claude CLI installed.
- **NEW state field `mock: bool`** propagates from CLI through every subprocess wrapper.
- **5 new mock helpers** write canonical artefacts:
  - `_mock_invoke_lead(domain, eng)` → canned plan.md with per-domain `specialists: [...]` frontmatter
  - `_mock_invoke_specialist(specialist, eng)` → canned executor-reports/{name}.md with criteria-ack + iteration headers
  - `_mock_invoke_manager(domain, eng)` → canned acceptance-log.md with `### Verdict: ACCEPT`
  - `_run_validator_lg_subprocess(..., mock=True)` → simulated ACCEPT result
  - `_run_adversary_lg_subprocess(..., mock=True)` → writes minimal consilium-summary.md + simulated ACCEPT
- **End-to-end smoke harness on synthetic engagements** — 7 paths verified:
  - S-tier dry-run: ACCEPT → archive (no HITL, no consilium)
  - S-tier --mock: same
  - M-tier --mock: PAUSE at human_directive → resume PROCEED → ACCEPT → archive
  - L-tier --mock: same as M-tier with iter_max=3
  - M-tier --mock REJECT_NOW at iter=1: short-circuit → REJECT → loop to plan (rework)
  - M-tier --mock REJECT_NOW at iter=2 (max): short-circuit → REJECT terminal, archive skipped
  - S-tier --real on box without claude CLI: fail-fast with `claude CLI not found in PATH`

### Three execution modes

| Mode | Flag | Subprocess calls | Use case |
|---|---|---|---|
| Dry-run | (default) | None | Skeleton smoke; placeholder semantics |
| Mock | `--mock` | None (canned artefacts) | End-to-end testing without claude CLI |
| Real | `--real` | claude CLI + sibling LG scripts | Production engagement |

Default remains `--dry-run` until field validation promotes `--real` (follow-up).

### Project metrics (v0.2.2 → v0.2.3)

| | v0.2.2 | v0.2.3 |
|---|---|---|
| `engagement_lg.py` | ~1000 lines (initial skeleton) | 1772 lines (final) |
| Engagement nodes wired | 4 dry-run, 2 real (intake+plan) | All 11 nodes wired (3 modes) |
| Execution modes | 2 (--dry-run, --real-with-NotImplementedError) | 3 (--dry-run, --mock, --real) |
| Sub-engine integrations | 0 | 3 (validator_lg, adversary_lg, engagement-archive subprocess wrappers) |
| State fields | 21 | 22 (+ mock) |

### Verification

- Syntax OK on engagement_lg.py.
- Lint: 0 errors, 14 warnings (baseline unchanged).
- Pre-publication checks pass; lint clean.
- End-to-end smoke harness covers 7 paths across 3 tiers and 2 decision paths.

---

## v0.2.2 — 2026-05-28 (modular precheck refactor + engagement_lg.py skeleton + whitelist fix)

Three structural deliverables shipped same day as v0.2.1; bundled into single release. All additive, lint 0 errors, dry-run path preserved across all changes.

### Modular decomposition of `handoff-precheck.py`

`scripts/handoff-precheck.py` reduced from 1264 → 423 lines (CLI/dispatcher only). 21 check functions extracted into `scripts/lib/precheck/` package:

- **`common.py`** (76 lines) — `WHITELIST`, `CRITERIA_FRONTMATTER_REQUIRED`, `read_criteria_meta`, subprocess `run` wrapper.
- **`criteria.py`** (150 lines) — 5 checks: whitelist, criteria-frontmatter, preflight, size-drift, tasks-decomposition.
- **`handoff.py`** (244 lines) — 5 checks: handoff-paths, handoff-sections, cross-val-quotes, self-acceptance-thinness, slot-language + `REQUIRED_HANDOFF_SECTIONS` / `SLOT_LANGUAGE_PATTERNS` / `SCANNED_FILES` / `SLOT_QUOTE_HINTS` constants.
- **`iteration.py`** (168 lines) — 4 checks: iteration-counter, executor-iteration-structure, validator-output-freshness, specialist-criteria-ack.
- **`validators.py`** (183 lines) — 2 checks: validator-outputs (~130 lines including in-function verdict/methodology sets), trace-schema + `OPTIONAL_VALIDATORS` constant.
- **`acceptance.py`** (158 lines) — 4 checks: acceptance-log-paths, verdict-canonical, human-directive, director-verdict + `HUMAN_DIRECTIVE_DECISIONS` constant.
- **`danger.py`** (47 lines) — 1 check: danger-scan.
- **`__init__.py`** (119 lines) — flat-namespace re-exports for backward compat.

Backward compatibility: filename + CLI surface + exit codes + JSON shape all unchanged. Verified byte-identical per-check verdicts against pre-refactor baseline on a real M-tier engagement (modulo one flaky external-subprocess result that re-converged on re-run).

### engagement_lg.py LangGraph skeleton

NEW `scripts/engagement_lg.py` (~1000 lines after formatter): third LangGraph engine in the family, owning the engagement-level lifecycle (intake → plan → dispatch → validate → consilium → accept → archive). Sibling of `validator_lg.py` (phase-level: validation) and `adversary_lg.py` (phase-level: consilium); engagement_lg is the engagement-level orchestrator that calls them.

- **`EngagementState` TypedDict** with 20 fields: identity (engagement, engagement_id), criteria meta (tier, domain, ux_heavy), lifecycle (phase, iter_n, iter_max), per-phase verdicts (intake_status, plan_status, validation_verdict, consilium_verdict, human_directive_decision, manager_verdict, archive_status), specialist fan-out (`specialists: list[str]`, `specialist_results: Annotated[list[dict], operator.add]`), HITL (hitl_enabled, paused_at, human_directive), bookkeeping (started_at, last_phase_at, error), and mode flags (dry_run, interrupt_on_criteria).
- **8 node placeholders** (intake / criteria_lock / plan / danger_gate / dispatch / specialist / validate / consilium / human_directive / manager_accept / archive). All dry-run-safe; advance state with minimum updates so the graph completes deterministically.
- **3 conditional routes** (`_route_after_validate`, `_route_after_consilium`, `_route_after_directive`, `_route_after_accept`) with full rework-loop budget enforcement (`iter_max` per tier: S=1, M=2, L=3).
- **3 HITL pause points** mirroring HITL interrupt/4b: `criteria_lock` (opt-in via `--interrupt-on-criteria`), `danger_gate` (conditional on danger-scan findings), `human_directive` (MANDATORY M/L after consilium).
- **Sub-engine integration:** subprocess delegate (NOT sub-graph) for v0.3 — keeps existing validator_lg.py / adversary_lg.py process-isolated. Promotion to sub-graph deferred until field data shows subprocess overhead matters.
- **venv bootstrap** shares `.venv-adversary-lg` with the two existing LG engines.
- **3 new ledger payload types** added to `lib/ledger.py`: `engagement_completed`, `phase_skipped`, `dryrun_marker` (KNOWN_PAYLOAD_TYPES: 29 → 32).
- **CLI:** `--invoke` (default --dry-run during subsequent release), `--real`, `--status`, `--resume-interrupt THREAD --decision PROCEED_TO_VERDICT|REJECT_NOW|DIRECTED_VERDICT|PROCEED|ABORT`, `--tier-override S|M|L`, `--no-hitl`, `--interrupt-on-criteria`, `--no-checkpoint`, `--json`.

### intake_node + plan_node real bodies

- **`_intake_node` real mode:** runs `size-detect.py --mode runtime --auto-promote --json` subprocess to catch tier drift; on `promoted=true` re-reads criteria.md and emits `size_promoted: "M→L"` in `phase_completed` payload. Validates `criteria.md` frontmatter via `lib.precheck.criteria.check_criteria_frontmatter` — on fail emits REJECT verdict and raises ValueError with fix instructions.
- **`_plan_node` real mode:** subprocess `claude -p --agent {domain}-lead <prompt>` (timeout 600s); prompt asks lead to author `engagement/plan.md` with YAML frontmatter `specialists: [a, b, c]` listing Phase 2 dispatch targets. After subprocess returns ok, `_parse_plan_specialists(plan_path)` extracts the list (accepts inline `[a, b]` or bullet `- a\n - b` forms) and stores it in state. On lead failure OR missing plan.md: raises RuntimeError. On missing `specialists:` frontmatter: warns but does not fail (subsequent release dispatch will be empty fan-out).
- **4 new helpers** in engagement_lg.py: `_find_claude_cmd()`, `_run_size_detect(eng, scripts_dir)`, `_invoke_lead_subprocess(domain, eng, prompt, timeout)`, `_parse_plan_specialists(plan_path)`.
- Dry-run path preserved: `--dry-run` skips both size-detect subprocess and lead-agent subprocess; returns `specialists=[]`, `plan_status=ok` so the graph still completes.

### Bug fix — WHITELIST drift in lib/precheck/common.py

The v0.2 reflection + ledger additions `engagement-reflections.md` (per-engagement reflection layer) and `events.jsonl` (append-only event ledger) to `engagement-protocol/SKILL.md`'s canonical whitelist but missed the parallel hardcoded `WHITELIST` constant in `handoff-precheck.py`. Real engagements with these files failed the whitelist check. Now sync'd: both entries added to `lib/precheck/common.py:WHITELIST`. Visible in pre-v0.2.2 baseline too — pre-existing bug, not a v0.2.2 regression.

### Project metrics (v0.2.1 → v0.2.2)

| | v0.2.1 | v0.2.2 |
|---|---|---|
| Agents | 66 | 66 |
| Skills | 48 | 48 |
| Main scripts | 14 | 15 (+engagement_lg.py) |
| Optional scripts | 3 | 3 |
| `lib/` modules | 1 (ledger.py) | 9 (ledger.py + precheck/{__init__,common,criteria,handoff,iteration,validators,acceptance,danger}) |
| LangGraph engines | 2 (validator_lg, adversary_lg) | 3 (+ engagement_lg) |
| HITL pause points | 2 (validator critical_check, adversary interrupt_apply_directive) | 5 (+ engagement criteria_lock, danger_gate, human_directive) |
| Ledger payload types | 29 | 32 (+ engagement_completed, phase_skipped, dryrun_marker) |
| `handoff-precheck.py` main file | 1264 lines | 423 lines (CLI/dispatch only; -841 → lib/precheck/ pkg) |

### Verification

- `python -m ast` parse on all 9 lib/precheck/*.py + engagement_lg.py + handoff-precheck.py: SYNTAX OK.
- `from lib import precheck; from lib import ledger`: imports cleanly; 32 advertised symbols present in precheck (9 constants/utilities + 21 check functions + 2 dispatch).
- `python engagement_lg.py --help` / `--status` work standalone.
- End-to-end skeleton smoke on a real M-tier engagement: graph completes intake → plan → dispatch → validate(ACCEPT) → consilium(ACCEPT) → PAUSE at human_directive; resume with `--resume-interrupt THREAD --decision PROCEED_TO_VERDICT` advances through manager_accept(ACCEPT) → archive(ok) → END.
- 22 ledger events captured end-to-end including paused/resumed transitions + dryrun_marker.
- subsequent release real-mode smoke: `_intake_node` correctly auto-promoted a real M→L promoted (engagement structurally L per task count, criteria was undersized). `_plan_node` failed fast with `claude CLI not found in PATH` on test box without claude CLI — correct fail-loud behavior.
- Lint sweep: 0 errors, 14 warnings (baseline unchanged).
- Pre-publication checks pass; documentation refresh validated.

### Memory records

- Modular refactor notes.
- engagement_lg design notes.py design doc + multi-week wave plan (skeleton done, bodies deferred).
- Updates to `MEMORY.md` Wave-A/Wave-B sections.

---

## v0.2.1 — 2026-05-28 (WAVE B+C — hot-path optimization, ledger coverage, golden parity)

Incremental refinement of v0.2 — closes 5 follow-up items deferred at the v0.2 cut. All changes additive, no behavior breakage, lint 0 errors.

### Observability (event ledger follow-up)

- **`adversary_lg.py` per-role ledger events.** `_make_run_role_node` now emits `consilium_started` (before two-pass) and `consilium_role_completed` (after two-pass) with payload `{role, iter_n, tier, verdict, findings_count, elapsed_s, delta_signal, ...}`. Top-level verdict mapping: `satisfied → ACCEPT`, `rework_required` / `suspicious_too_clean` → `REJECT`, `fail` → `REJECT`. Two early-return guards (unknown role, missing peer-opus output) emit `consilium_role_completed` with verdict=REJECT so the ledger never misses a started-but-aborted attempt. Smoke-tested end-to-end (5 events, agent attribution correct, verdict propagated).
- **Combined LG-engine emit footprint:** validator_lg.py (8 sites) + adversary_lg.py (5 lifecycle + 2 per-role + 2 early-return = 9 sites) + handoff-precheck.py (per-check). Lifecycle, validator-level, AND per-role events all observable from a single `engagement/events.jsonl`.

### SkillOpt golden-set parity (event ledger follow-up)

- **`golden/design/` × 3 scenarios + README** mapping the three failure classes (rule_ignored / rule_missing / rule_wrong) to design-domain validators:
  - `scenario-01-design-token-drift-ui-validator` (rule_ignored) — critique must flag raw hex when design-research.md lists tokens
  - `scenario-02-accessibility-aria-missing-modal` (rule_missing) — accessibility-validator must fire ≥2 critical findings (aria + focus-trap + escape)
  - `scenario-03-dark-mode-contrast-fail` (rule_wrong) — accessibility-validator must check contrast on dark-theme screens, not light-only
- **`golden/marketing/` × 3 scenarios + README** symmetric set for marketing-domain validators:
  - `scenario-01-keyword-count-underdelivery` (rule_ignored) — completeness-validator must flag criterion-vs-deliverable count mismatch
  - `scenario-02-seo-claim-unsupported-by-data` (rule_missing) — critique must flag uncited Yandex-derived factual claim
  - `scenario-03-brand-voice-pronoun-violation` (rule_wrong) — critique must flag pronoun mismatch against brand-research.md
- **All 3 domains (dev + design + marketing)** now have ≥3 golden scenarios covering the 3 failure classes. Director can run a real SkillOpt cycle once ≥3 real same-class signals accumulate in ANY domain.

### Hot-path optimization

Heavy `SKILL.md` files split into hot-path TL;DR + cold-path `references/{topic}.md` files loaded on-demand. Net effect: −572 lines loaded into every engagement; +515 lines moved to references that load only when relevant.

- **`engagement-protocol/SKILL.md`** 1128 → 963 lines (−165). Four new references:
  - `references/ux-heavy.md` (75 lines) — full 3-level gradient, minor vs true rules, trace JSON schema, lead/director gates. Hot-path keeps a 5-bullet TL;DR.
  - `references/abort.md` (51 lines) — stub `acceptance-log.md` template for ABORTED verdict, archival flow, NOT-an-abort cases.
  - `references/resume.md` (33 lines) — per-artefact reuse-vs-regenerate decision rules, heartbeat resume template.
  - `references/budget.md` (73 lines) — per-tier token envelope, `token-budget.py` / `size-detect.py --auto-promote` flows, retroactive auto-promote consequences.
- **`ui-ux-methodology/SKILL.md`** 664 → 347 lines (−317, biggest single saving). Two new references:
  - `references/quick-reference.md` (244 lines) — full 10-priority-category rule cheat-sheet (Accessibility / Touch / Performance / Style / Layout / Typography / Animation / Forms / Navigation / Charts) with platform / WCAG sources.
  - `references/professional-ui-rules.md` (108 lines) — Common Rules tables + 5-section Pre-Delivery Checklist.
- **`dev-methodology/SKILL.md`** 441 → 351 lines (−90). Two new references:
  - `references/skills-ecosystem.md` (55 lines) — per-category skill catalog with one-line purpose.
  - `references/agents.md` (60 lines) — per-role agent catalog with one-line purpose.
- **`engagement-protocol/references/` directory** now has 7 files total (3 prior at v0.2 — cross-domain / dangerous-ops / archival — + 4 new at v0.2.1).

### Project metrics

| Metric | v0.2 | v0.2.1 |
|---|---|---|
| Agents | 66 | 66 |
| Skills | 48 | 48 |
| Scripts (main) | 14 | 14 |
| Scripts (optional) | 3 | 3 |
| Reference files (`*/references/*.md`) | ~40 | ~48 (+8) |
| Hot-path lines in 3 heavily-loaded skills | 2233 (1128+664+441) | 1661 (963+347+351) |
| Hot-path delta (per engagement load) | — | **−572 lines** |
| Adversary ledger emit sites | 5 | 9 (+ per-role + early-return guards) |
| SkillOpt golden scenarios | 3 (dev only) | 9 (3 × 3 domains) |
| LangGraph engines | 2 | 2 |
| HITL pause points | 2 | 2 |
| Lint errors | 0 | 0 |

### Verification

- `python3 ~/.claude/skills/skill-authoring/scripts/lint_skill.py --all` → 0 errors, 14 warnings (pre-existing, unchanged from v0.2).
- `adversary_lg.py` syntax check passes; per-role smoke test wrote all 5 expected events (legacy_import + ledger_initialized + engagement_started + consilium_started + consilium_role_completed) with correct agent attribution and verdict mapping.
- All 8 new `references/*.md` files structurally valid; all 9 golden scenarios use the canonical format established by `golden/dev/README.md`.

### What is NOT in this release

- observability backend (Langfuse self-hosted vs file-only) — still deferred until ≥3 real engagements accumulate ledger volume.
- modular refactor of `handoff-precheck.py` (60KB god-object) — still deferred until a new check class needs adding.
- `engagement_lg.py` engagement-level state machine — still multi-week, gated on the modular refactor.

### Memory records (for full context)

- Refinement-release notes (per-role ledger events, golden parity across domains, hot-path skill split).

## v0.2 — 2026-05-28 (this sync)

Cumulative delta against v0.1 baseline. Covers incremental refactor passes, the manager/director split, system cleanup, system-wide research with external review, quick-win additions, and the event ledger foundation.

### Architecture changes

- **Manager / director split** (2026-05-28).
  - `*-manager` (NEW): per-engagement ACCEPTOR (3 agents: dev/design/marketing-manager). Loads `acceptance-protocol` skill. Judges between producer and adversary, never re-runs validators.
  - `*-director` (REPURPOSED): per-domain SYSTEM-OPTIMIZER (out-of-band). Loads `system-optimization-protocol` skill. Runs SkillOpt-style skill-evolution loop: reflect → bounded edit → golden gate → promote. **Judge-only — Codex proposes edits via codex-bridge (cross-family).**
  - Origin: SkillOpt (Microsoft) "train the procedure, not the weights" — adapted, not full auto-loop (low volume, subjective output).
- **Gamedev domain fully removed** — 46 gd-* agents + 51 gd-* commands + 11 gd-* skills deleted. Aurelith project (real client work) kept in user memory.
- **Mid-leads soft-consolidated** — engagement-protocol skill +57 lines (canonical Engagement-mode contract + Criteria propagation sections); 3 top-leads -75 lines (heartbeat dupe removed); 8 mid-leads -443 lines total. Net: -461 lines of duplicate body.
- **Layer 5 closure (researchers)** — 3 NEW researcher agents (code-researcher, brand-context-researcher, design-system-researcher) + product-context-validator for cross-domain coherence.

### Skills

- **NEW** `acceptance-protocol` (renamed from director-acceptance-protocol) — per-engagement acceptance methodology (S/M/L tiered).
- **NEW** `system-optimization-protocol` — SkillOpt loop adapted: event-driven reflect → bounded edit (budget L=4-6) → golden-set gate → slow-update 4-bucket → two-level meta.
- **NEW** `engagement-contract` (43 lines) — minimal 6-bullet specialist subset of engagement-protocol. Loaded by 20 specialists via frontmatter instead of inlining the contract (was duplicate in agent bodies).
- **REMOVED** `director-acceptance-protocol` (renamed to acceptance-protocol).
- **Updated** `engagement-protocol` — added §"Authority and conflict resolution" (7-rule precedence), §"Engagement-mode contract", §"Criteria propagation (mid-lead duty)", whitelist entries for `engagement-reflections.md` + `events.jsonl`.
- **Updated** `validation-pipeline` — tier-keyed dispatch matrix (S manual / M validator_lg --auto default / L mandatory), canonical envelope documentation, --interrupt-on-critical flow.
- **Updated** 7 PROTOCOL skills got `triggers:` frontmatter (agency-intake, engagement-protocol, engagement-contract, acceptance-protocol, system-optimization-protocol, validation-pipeline, docs-pipeline).

### Scripts

- **NEW** `lib/__init__.py` + `lib/ledger.py` (~520 lines) — append-only event ledger module. Per-engagement `engagement/events.jsonl`. Schema v1 with 17 fields, 28 KNOWN_PAYLOAD_TYPES, assert guards, forward-only with synthetic `legacy_import` event for pre-ledger engagements, replay-friendly schema versioning. Helpers: `emit_authority_conflict()`, `emit_skill_snapshot()`, `snapshot_skills()`, `hash_input()`.
- **NEW** `validator_lg.py` (LangGraph atomic-validator fan-out via Send; retry edge; auto-plan; --resume; Pydantic I/O; **Opt-in HITL** native HITL via `--interrupt-on-critical` mirroring adversary_lg.py HITL interrupt; **canonical envelope** canonical envelope written next to raw output; ledger wired with 8 emit sites).
- **MOVED** `size-detect.py` → main `scripts/` (was in optional/, but actively invoked by handoff-precheck.py + 3 skills — mis-categorized as optional).
- **REMOVED** `adversary.py` (legacy, replaced by `adversary_lg.py` since 2026-05-14 + per-script comments are historical docs not deps).
- **REMOVED** 5 dead optional scripts (cross-val-template.py, director-sweep.py, validator-retry.py, secondary-init.py, metrics-summary.py).
- **Updated** `adversary_lg.py` — ledger wired (5 emit sites: engagement_started, consilium_synth_completed, interrupt_paused/resumed, human_directive_received). HITL via `interrupt()` already shipped in Phase 2.
- **Updated** `handoff-precheck.py` — ledger wired (per-check `precheck_started` / `precheck_passed` / `precheck_failed` emit). Tier dispatch unchanged.
- **Promoted** validator schema demotion: 5 validators were demoted to haiku in Phase 1, feasibility-assessor reverted to sonnet after anti-pattern scan caught it.

### Acceptance behaviour

- **Tier-keyed validator dispatch** (default): S = manual parallel Task dispatch; M = `validator_lg.py --auto` default; L = `validator_lg.py --auto` mandatory.
- **Per-engagement reflection** (M/L): after writing verdict, manager appends 0-3 actionable reflections to `engagement/engagement-reflections.md` per strict constraint (target = skill/agent rule, class = rule_{missing,wrong,ignored}). Feeds director's monthly reflection sweep — sub-threshold patterns that accumulate across engagements.
- **Authority and conflict resolution invariant** — 7-rule precedence written into engagement-protocol skill. Unresolved conflicts become blocking `authority_conflict` events.
- **Critical-pause HITL** (M/L only): `validator_lg.py --interrupt-on-critical` pauses graph when any validator returns severity=critical finding. Resume via `--resume-interrupt <thread_id> --decision PROCEED|REJECT|DIRECTED [--note]`.

### Observability

- **Event ledger** is now the primary observability surface. Every M/L engagement emits to `events.jsonl` from adversary_lg.py + validator_lg.py + handoff-precheck.py. 28 payload types cover phase transitions, validator outcomes, interrupts, verdicts, reflections, authority conflicts.
- **Canonical validator envelope** — every validator_lg.py output JSON gets a `canonical` block alongside raw fields. Normalized verdicts (6 values) + severities (5 levels) + validator_type (numerical|judgement) + metrics extraction. Ledger `validator_completed` events surface `canonical_verdict` + `output_schema_version="1.0"`.

### SkillOpt loop

- **First exercise** (, dry-run, 2026-05-28): 3 golden scenarios populated for dev domain (spec-code-drift, flaky-test-masking, security-gap), 3 synthetic signals (`dryrun: true`), Codex proposed 3 bounded edits via mcp__codex__codex, judge gate accepted 2 of 3 (66%). Proposal-1 rejected (wrong target file — signal "Traced to" field load-bearing). Anchors all verified in target files. Rejection-buffer pattern exercised end-to-end.
- **Golden sets** for design and marketing domains still empty — future work.

### What is NOT in this release

- observability backend (Langfuse self-hosted vs file-only) — deferred until ≥3 real engagements accumulate ledger volume. The event ledger itself IS in v0.2; the question of "what reads it for analytics" is deferred.
- engagement-protocol TL;DR + references/ split — deferred.
- ui-ux + dev-methodology references/ split — deferred.
- modular refactor of handoff-precheck.py (60KB god-object) — deferred until a new check class needs adding.
- `engagement_lg.py` engagement-level state machine — multi-week, gated.
- Adversary per-role events (consilium_started, consilium_role_completed) — secondary; main lifecycle (init + synth + interrupt) covered.

### Project metrics

| Metric | v0.1 | v0.2 |
|---|---|---|
| Agents | 60 | 66 |
| Skills | 46 | 48 |
| Scripts (main) | 13 | 14 |
| Scripts (optional) | 9 | 3 |
| Mid-lead files | 8 (~99-109 lines each) | 8 (~44-53 lines each) |
| Validator schemas | 23 heterogeneous | + canonical envelope wrapper |
| LangGraph engines | 1 (adversary_lg.py) | 2 (+ validator_lg.py) |
| HITL pause points | 1 (adversary --interrupt) | 2 (+ validator --interrupt-on-critical) |

### Verification

- `python3 ~/.claude/skills/skill-authoring/scripts/lint_skill.py --all` → 0 errors, 14 warnings (pre-existing, unchanged).
- All 4 modified scripts pass `ast.parse` syntax check.
- 20/20 specialists carry `engagement-contract` skill, 0 residual `## Engagement-mode contract` headers.
- Ledger smoke test: 22 events written end-to-end on synthetic M-tier engagement with mock invoker.
- canonical envelope smoke test: every validator output JSON has `canonical` block; ledger event carries `canonical_verdict`.

### Memory records (for full context)

Living architecture records held in private memory (not in this public mirror):

- Incremental-refactor baseline notes.
- Manager/director split + SkillOpt origin notes.
- `project memory` — earlier backlog closure.
- System research notes.
- `project memory` — Codex cross-family consultation prescribed: authority invariant + event ledger.
- `project memory` — quick wins (authority invariant, reflections, specialist dedup, critical-pause HITL, validator_lg --auto default).
- `project memory` — event ledger foundation.
- SkillOpt dry-run findings notes.
- This sync planned (full sync chosen).

## v0.1 — 2026-05-14

Initial public release.

- Tiered acceptance (S/M/L).
- `adversary.py` (stdlib-only) + `adversary_lg.py` (LangGraph).
- `consilium-synth.py` + `consilium-present.py`.
- 60 specialized agents, 46 methodology skills.
- 22 Python orchestration scripts.
- 5-reviewer L-tier consilium (peer-opus + 2× Codex + sonnet + haiku).
