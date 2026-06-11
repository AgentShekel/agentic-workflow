# Cross-tier rules (apply at every tier)

> Loaded from `acceptance-protocol` SKILL.md. These apply at S, M, and L unless a rule states M/L only.

**Contents:** Consilium fidelity + provenance cross-check (M/L) · ux_heavy gradient · Validator selection · Danger-scan · Per-engagement reflection (M/L) · SkillOpt readiness signal · Engagement = directory

## Consilium fidelity + provenance cross-check (M/L only - REQUIRED before human gate)

Before step 6 presents `engagement/consilium-summary.md` to the human supreme judge, the manager/director MUST read the current iteration's acceptance artefacts already on disk and append this cross-check to `engagement/acceptance-log.md`. Present any flags and suppressed criticals with the summary. This is evidence adjudication, **not a validator re-run or re-sweep**; the `Role boundary` remains intact.

```markdown
### Consilium fidelity/provenance cross-check
- {role}: summary={verdict}/{findings_count}; raw=`engagement/validation-outputs/{role}-iter-{N}-*.json` `canonical.verdict`={verdict}, findings={count}; ledger `engagement/events.jsonl` `consilium_role_completed.verdict`={verdict}
- Provenance: final role JSON={present|absent}; `consilium-synth.py` mechanical-aggregation provenance marker={present|absent}
- FIDELITY DIVERGENCE | PROVENANCE ABSENT - too-clean / suspicious: {details or none}
- Suppressed critical `{id/title}`: `{verbatim raw id/title or issue}` - SUSTAINED | OVERRULED ({merits rationale})
```

Repeat the role line for every expected reviewer role, using the matching final, non-`preliminary` raw JSON and latest matching ledger event. Diff the summary's per-role verdict + findings count against raw `canonical.verdict` + `findings` and the ledger verdict.

If the summary renders a role softer by downgrading its verdict or dropping/downgrading findings, record a **FIDELITY DIVERGENCE - too-clean / suspicious** flag citing the raw path and verdict. Reproduce every suppressed `severity=critical` finding verbatim by raw id/title, or exact raw `issue` where that is the schema field, and adjudicate each on its merits. A confirmed suppressed critical is `SUSTAINED` and blocks ACCEPT.

If `consilium-summary.md` exists but no backing final role JSON and no `consilium-synth.py` provenance marker are present, record **PROVENANCE ABSENT - too-clean / suspicious** and do not treat the summary as a real consilium. Either missing element must be reconciled before ACCEPT.

The summary aggregate and final manager verdict may NEVER be softer than the strongest constituent raw/ledger verdict (`rework_required`/`REJECT` dominates `satisfied`/`ACCEPT`). A real adversary or cross-family REJECT cannot silently become ACCEPT. Any unreconciled fidelity/provenance divergence results in REJECT, or is routed to a DIRECTED directive/escalation before verdict - never ACCEPT.

## ux_heavy gradient

`ux_heavy: true | minor | false` — independent of tier. Determines evidence type:
- `true` → Playwright traces required, screens captured, accessibility-validator must run
- `minor` → screens captured, accessibility-validator recommended
- `false` → no UX-specific artefacts required

ux_heavy never makes acceptance lighter; only tier does that.

## Validator selection

Determined by domain + ux_heavy + scope, NOT by tier:
- backend code touched → security-auditor + code-reviewer
- UI surfaces touched → critique + accessibility-validator + ux-review (if ux_heavy)
- migrations → migration-validator
- new tests → test-reviewer
- prompts → prompt-reviewer
- docs touched → documentation-reviewer

S-tier engagement that touches auth code STILL needs security-auditor. Tier scales acceptance rigour, not safety baseline.

## Danger-scan

Tier-independent. Every tier runs `danger-scan.py`. DROP TABLE / force-push / prod deploy / secret rotation / bulk delete → user OK in `scope-sync.md` mandatory regardless of tier.

## Per-engagement reflection (M/L only — feeds SkillOpt below threshold)

After writing the verdict (ACCEPT or REJECT) on every M/L engagement, the manager appends **0–3 reflections** to `engagement/engagement-reflections.md` (append-only). The file's whole purpose is feeding the director's monthly reflection sweep — patterns that don't reach SkillOpt's ≥3-same-class threshold within a single engagement but accumulate across many.

**Strict constraint — write a reflection ONLY when:**
- the failure points at a specific `skill: X` or `agent: Y` rule that should change, AND
- you can classify it as `rule_missing` / `rule_wrong` / `rule_ignored` (the SkillOpt taxonomy).

**`target` semantics (load-bearing).** Point `target` at the skill/agent whose
CONTENT must change to ENFORCE the catch (the rule/validator that would PRODUCE the catching
artefact), NOT at the agent that produced the buggy output. A wrong target sends the optimizer's
edit to the wrong file (right pattern, wrong place → gate-rejected, wasted cycle). If the real fix
is a script, write `target: script: <file>` — recorded for the dev-director sweep but excluded
from the SkillOpt readiness count (the loop edits skills/agents, not scripts).

**Discard:** generic observations ("tests took long", "we had a typo", "could've been faster", "validator was slow"). Noise here surfaces as false signals at scale and degrades the director's signal-to-noise.

**Format** (one block per reflection, append-only):
```
## Reflection — {engagement-name} — {YYYY-MM-DD} — verdict: {ACCEPT|REJECT}

- target: {skill: X | agent: Y}
  class: rule_missing | rule_wrong | rule_ignored
  observation: {1–2 lines describing the gap}
  evidence: {acceptance-log path / validator output path / consilium path}
  resolved: {YYYY-MM-DD — how}   # OPTIONAL — add later if the gap is closed by a direct fix
```

**`resolved:` convention.** Reflections are append-only and never edited away — but when a
reflection's gap is later closed by a direct fix (outside a SkillOpt cycle), append a `resolved:`
line under it. `skillopt-ready.py` then drops it from the readiness count, exactly as it does for a
`resolved:` log signal. A reflection whose issue is also recorded as a log SIGNAL needs no marker:
the checker already treats a log twin (same engagement + taxonomy) as authoritative and skips the
reflection, so the log's `resolved:` covers both.

**Zero reflections is a valid outcome** — a clean engagement with nothing to change should leave `engagement-reflections.md` empty (file may not exist at all). Inventing reflections to look productive corrupts the signal.

These cluster by `target × class` and trigger SkillOpt cycles at cluster size ≥3 (or on Langfuse trend Δ — see `system-optimization-protocol` §"Trigger" Layer 3). `skillopt-ready.py` harvests them automatically (Channel B): it surfaces a due reflection cluster through the same SessionStart reminder as the log channel, so this no longer waits on a manual monthly sweep — the director's pass is now the deeper review over what the checker surfaces.

## SkillOpt readiness signal (run after writing reflections / signals)

After the verdict + any reflections/signals are written, run `python ~/.claude/scripts/skillopt-ready.py`. It reads BOTH channels — log SIGNALs (clustered by domain/class) and orphan reflections (clustered by domain/target/class) — and reports a bucket **DUE** when either reaches ≥3 loop-actionable live entries; surface it in the engagement summary — e.g. "SkillOpt cycle due for dev (3× rule_wrong) → run `прогнать skill-evolution dev`". This is the immediate path; a SessionStart hook re-runs the same check every session as a safety net, so a missed surfacing is caught next session. The checker excludes `dryrun:` / `resolved:` / script-only-targeted signals and reflections that have a log twin, so it does not false-fire or double-count.

## Engagement = directory

All tiers use the same FS state convention:
```
engagement/
├── criteria.md
├── plan.md (M/L only)
├── handoff.md
├── acceptance-log.md (M/L; on S the human writes here)
├── scope-sync.md (if dangerous-ops or scope clarification)
├── validation-log.md
├── validation-outputs/{validator|adversary-role}-iter-N-{ts}.json
├── consilium-summary.md (M/L, after consilium-synth.py runs)
├── executor-reports/ (M/L)
├── tasks/ (L mandatory; M optional with multi-specialist)
├── screens/ (if ux_heavy)
├── traces/ (if ux_heavy true)
└── iteration (plain-text counter)
```
