# Verdict format

> Loaded from `acceptance-protocol` SKILL.md. The verdict is written by the human (S) or the manager (M/L).

**Contents:** Binary verdict rule · Canonical form (machine-parseable) · M/L ACCEPT template · M/L REJECT template · S-tier verdict template · Adjudication marker reference · Path verification

The verdict is binary: **ACCEPT** or **REJECT**. There is no third option. `ACCEPT CONDITIONAL`, `ACCEPT pending X`, `ACCEPT — user to verify Y` are all forbidden — they push QA back onto the user, which is exactly what the agency model exists to prevent.

If validation cannot be completed (Docker not running, Playwright unavailable, DB unreachable, secrets missing): the verdict is **REJECT** with reason `validation incomplete: <specific tool/artefact>`. Coordinate with the lead and (if needed) escalate ONCE to the user to bring validation environment online — then re-review. Do not defer the verification itself to the user.

## Canonical form (machine-parseable, structurally enforced)

Before writing any M/L verdict, the manager MUST verify that the current iteration's pre-human **Consilium fidelity/provenance cross-check** exists in `acceptance-log.md` and is reconciled. A missing or unreconciled fidelity/provenance flag, any constituent `REJECT`/`rework_required`, or any SUSTAINED suppressed critical makes `ACCEPT` forbidden: write `REJECT`, or obtain a DIRECTED/escalation resolution before the verdict.

`engagement/acceptance-log.md` (append, never overwrite). M/L tier verdicts MUST include the **Adversary findings adjudication** section with explicit markers per consilium signal — `director-verdict-check.py` enforces this mechanically.

### M/L tier ACCEPT template

```markdown
## Iteration {N} — {YYYY-MM-DD HH:MM}

### Human directive received
- Decision: PROCEED_TO_VERDICT | DIRECTED_VERDICT (cite human-directive.md)
- {if DIRECTED_VERDICT: human's mandatory addresses + overrides applied below}

### Mechanical pre-check
- handoff-precheck.py exit 0 (tier={M|L}, {N} checks pass)

### Adversary findings adjudication (REQUIRED — structural gate)

**Convergent findings** (≥2 reviewers agree, from consilium-summary §Findings):
- finding-1 ({severity}): {issue summary} — SUSTAINED | OVERRULED
  Rationale: {1-2 lines, especially required if OVERRULED}
- finding-2 ({severity}): {issue} — SUSTAINED | OVERRULED
  Rationale: ...

**Cross-family disagreements** (mandatory if any from consilium-summary §Disagreements):
- {ra}={va} vs {rb}={vb}: SIDED WITH {ra | rb} | SPLIT
  Rationale: {director's manual verification of disputed finding — required for cross-family}

**Naive-layer catches** (mandatory if any from consilium-summary §Naive-layer catches):
- {haiku/sonnet finding}: REAL | FALSE_POSITIVE
  Rationale: ...

**Suspicious_too_clean flags** (mandatory if any):
- {role-name}: ACKNOWLEDGED — {1 line: do you trust this verdict, why}

### Criteria trace (REQUIRED on ACCEPT)
| # | Criterion | Status | Evidence path | Verified by |
|---|---|---|---|---|
| 1 | ... | ✅ | engagement/ui/hero.md L1-L8 | adversary-confirmed ✓ |
| 2 | ... | ✅ | https://staging/dashboard | adversary verified URL 200 ✓ |

### Verdict: ACCEPT

{1-3 lines tying adjudications above into final ACCEPT rationale}

Delivered to user:
- {deliverable list}

Notes for user:
- {only criteria.md-approved deferrals or scope-sync.md waivers}

Engagement archival:
- engagement/ → engagement-archived/{YYYY-MM-DD}-{name}/  (per protocol §archival)
```

### M/L tier REJECT template

```markdown
## Iteration {N} — {YYYY-MM-DD HH:MM}

### Human directive received
- Decision: PROCEED_TO_VERDICT | DIRECTED_VERDICT | REJECT_NOW

(if REJECT_NOW: skip adjudication section, write minimal verdict citing human-directive.md and lead's rework directives)

### Mechanical pre-check
- {pass / fail with names}

### Adversary findings adjudication (REQUIRED — structural gate)

(same structure as ACCEPT template; markers required per signal)

### Verdict: REJECT

Blocking items (each with concrete action — not advice):
1. {Criterion 2 unmet} — Action: {produce X per criteria.md §"Done when" item 2}
2. {Convergent finding-1 SUSTAINED} — Action: {fix per finding's fix_hint}
3. {Naive Haiku catch REAL: dark mode missing} — Action: {implement toggle + capture dark-mode screen}

(Verdict is REJECT, not CONDITIONAL. No "user to verify".)
```

### S-tier verdict template (no director, human writes directly)

```markdown
## Iteration {N} — {YYYY-MM-DD HH:MM}

### Mechanical pre-check
- handoff-precheck.py exit 0 (tier=S, 6 checks pass)

### Criteria check
- crit-1: ✓ | ✗ {1-line evidence}
- crit-2: ✓ | ✗

### Verdict: ACCEPT | REJECT
{1-3 lines: what was delivered (ACCEPT) or what to rework / abandon (REJECT)}
```

### Adjudication marker reference

| Signal type | Required marker(s) |
|---|---|
| Convergent finding (≥2 reviewers) | `SUSTAINED` or `OVERRULED` per finding |
| Cross-family disagreement | `SIDED WITH <reviewer>` or `SPLIT` per disagreement |
| Naive-layer catch | `REAL` or `FALSE_POSITIVE` per catch |
| Suspicious_too_clean | `ACKNOWLEDGED` per flagged reviewer |

`director-verdict-check.py` parses verdict text and verifies that each consilium signal has a corresponding marker. Missing markers → handoff-precheck FAIL on `director-verdict` check.

## Path verification

After writing ACCEPT, BEFORE archival, run:
```bash
python ~/.claude/scripts/handoff-paths-check.py engagement/acceptance-log.md --json
```
Every path in criteria-trace's "Evidence path" column must resolve to a real file. Phantom paths in ACCEPT are particularly insidious — they look like trail-of-evidence but reference vapour. Non-zero exit → fix verdict before posting to user.
