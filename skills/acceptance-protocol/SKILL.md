---
name: acceptance-protocol
domain: meta
triggers:
  - "loaded by every *-manager agent via skills frontmatter"
  - "writing acceptance verdict (ACCEPT / REJECT / DIRECTED)"
  - "adjudicating producer vs adversary findings (consilium SUSTAINED / OVERRULED / FALSE_POSITIVE)"
  - "appending per-engagement reflection on M/L"
  - "deciding whether to escalate at round 3"
description: |
  [PROTOCOL] Tier-aware per-engagement acceptance methodology shared by all agency
  managers (marketing / dev / design). Defines per-tier (S/M/L) protocols: S has no
  manager phase, M adds Opus adversary, L adds cross-family consilium. Managers are JUDGES
  between producer and adversary, not re-runners. Reference-only — loaded by
  `*-manager` agents via skills frontmatter, not triggered by keywords.
---

# Acceptance protocol (tier-aware)

> **Naming note:** throughout this protocol, **"director"** denotes the per-engagement
> **acceptor** role — implemented by the `*-manager` agents (`dev-manager`,
> `design-manager`, `marketing-manager`). The senior `*-director` agents are a *separate*
> role: the system-optimizers that improve the skill/agent corpus (see
> `system-optimization-protocol`); they never accept engagements. Read every "director"
> below as "manager / acceptor". (Script names like `director-verdict-check.py` are
> unchanged — they check the verdict artefact, not the agent name.)

Acceptance scales with engagement tier. The same engagement at tier S, M, and L receives different rigour:

| Tier | Director phase? | Adversary | Validator coverage |
|---|---|---|---|
| S | No (producer self-attest + mechanical + human glance) | None | Per domain + ux_heavy, minimal set |
| M | Yes, lightweight (judge between producer + 1 adversary) | Opus adversary in fresh subprocess | Per domain + ux_heavy, typical 1-3 |
| L | Yes, full (judge between producer + consilium of 5) | Opus + 2× Codex + Sonnet + Haiku consilium | All applicable validators |

Tier is read from `engagement/criteria.md` frontmatter `size: S|M|L`. The acceptance phase **dispatches to the matching section below**.

## Where this skill ends and per-domain manager starts

This skill defines GENERIC acceptor behavior shared by all 3 domain managers (`dev-manager`, `design-manager`, `marketing-manager`). The agent files contain only domain-specific contracts:

- **Required validators per domain** (e.g., security-auditor for dev; critique + accessibility for design; reality-checker + skeptic for marketing)
- **Domain red flags that force REJECT** (e.g., migration without rollback for dev; brand-token-propagation failure for design; ranking-without-source-date for marketing)
- **Domain-specific anti-patterns** (e.g., "don't edit source files" for dev; "don't open Figma" for design; "don't rewrite copy" for marketing)
- **Common scope-sync questions** (domain-flavored)
- **Tool-unavailability special cases** (Playwright/Figma for design; Yandex APIs for marketing)

Tier dispatch, verdict template, mechanical post-check, scope-sync protocol, escalation, iteration loop — **all live here, in this skill**. If you're modifying generic acceptor behavior, edit this skill (one place, three managers benefit).

## Role boundary

Directors do not plan, do not dispatch executors, do not write deliverables, **do not re-run validators independently**. They judge the lead's handoff against criteria, informed by adversary findings (M/L) or producer self-attestation (S).

| Action | Lead | Director |
|---|---|---|
| Capture intake | ✗ | ✗ (secretary does) |
| Plan engagement | ✓ | ✗ |
| Dispatch executors | ✓ | ✗ |
| Run validators (security / accessibility / code-reviewer / etc.) | ✓ (required before handoff) | ✗ (judges results) |
| Run adversary (M/L only) | ✗ (script invocation, not lead authoring) | Triggers via `adversary_lg.py` |
| Judge against criteria | ✗ | ✓ |
| Write verdict | ✗ | ✓ (M/L only) |
| Return to user | Lead on S; director on M/L | ✓ |

**Re-running a validator is allowed only on L-tier and only when adversary findings explicitly identify a validator-coverage gap.** Maximum 1 re-run per validator per iteration. Sweep-style "re-run everything" is forbidden — same brain produces same verdict, no new information.

## Tier dispatch (read criteria.md frontmatter, jump to matching section)

```yaml
# engagement/criteria.md frontmatter
---
engagement: ...
domain: ...
size: S | M | L      # ← dispatch by this field
ux_heavy: ...
tools_required: ...
---
```

If `size` is missing or invalid → treat as M (safe default). Verify via `python ~/.claude/scripts/handoff-precheck.py engagement/` (it reports tier in TL;DR).

---

## S-tier acceptance

**No director phase.** Producer (Sonnet typically) self-attests, mechanical checks gate, human accepts.

### Steps

1. **Producer writes `handoff.md`** (1 page max), including a self-attestation block: `## Self-attestation` with **1 honest concern** (not "all good" — a real reservation).
2. **Lead runs mechanical pre-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=S → 6 critical checks (criteria-frontmatter, whitelist, preflight, handoff-paths, danger-scan, verdict-canonical). Exit 0 = green.
3. **Human reads handoff.md** (it's short, actually read it, not skim).
4. **Human writes verdict** in `engagement/acceptance-log.md`:
   ```markdown
   ### Verdict: ACCEPT
   {1-line rationale}

   ## Iteration 1 — {YYYY-MM-DD HH:MM}
   ### Criteria check
   {brief — bulletpoint per done-when, ✓ / ✗}
   ### Notes
   {if any}
   ```
   Or `### Verdict: REJECT` with directive ("rework X" or "abandon — not worth fixing").

### S-tier iteration

**1 iteration max.** REJECT → human gives directive (rework / abandon), not auto-loop. If S-engagement needs more than 1 round, criteria are wrong (route to `agency-intake` for re-spec) or scope was understated (auto-promote to M, see below).

### When NOT to use S-tier acceptance

- `ux_heavy: true` AND the change touches accessibility-sensitive surfaces → run accessibility-validator before accepting (tier-independent rule)
- `danger-scan` flagged ops without user-OK → REJECT regardless of tier

---

## M-tier acceptance

**Human-as-supreme-judge flow with lightweight director.** Adversary pass injected between mechanical checks and human review. Director writes formal verdict per human's directive.

### Steps

1. **Lead completes work**, writes `handoff.md` (full schema: §1 Diff, §2 Deliverables, §3 Criteria trace, §5 Validation log, §7 Self-acceptance with ≥2 concerns, §6 Exercised if ux_heavy).
2. **Lead runs methodology validators per domain:**
   - dev: code-reviewer + security-auditor (if auth/data) + reality-checker
   - marketing: skeptic + reality-checker on data claims
   - design: critique + accessibility-validator (UI) + ux-review (if ux_heavy)
   - cross-domain: include each domain's required set
3. **Lead runs mechanical pre-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=M → 13 checks. Exit 0 required (some skip until acceptance phase artefacts exist).
4. **Director (or lead) triggers adversary pass with two-pass protocol:**
   ```bash
   python ~/.claude/scripts/adversary_lg.py engagement/ --consilium M
   ```
   Pass 1: subprocess on curated copy (no handoff visible) → preliminary findings. Pass 2: subprocess on full engagement + preliminary findings injected → final adversary JSON. Outputs:
   - `engagement/validation-outputs/peer-opus-iter-{N}-preliminary-{ts}.json`
   - `engagement/validation-outputs/peer-opus-iter-{N}-{ts}.json`
5. **Synthesize:**
   ```bash
   python ~/.claude/scripts/consilium-synth.py engagement/
   ```
   Writes `engagement/consilium-summary.md`.
6. **HUMAN reads consilium-summary.md as supreme judge.**

   **Chat-driven flow (default — no markdown writing required):**

   The director (or coordinating agent) **presents the consilium summary inline in chat** with the decision menu. Easiest way — use the helper:

   ```bash
   python ~/.claude/scripts/consilium-present.py engagement/
   ```

   This script reads `consilium-summary.md` and outputs a chat-ready summary with:
   - Aggregate verdict + 1-line rationale
   - Reviewer roster (verdicts + findings count per role)
   - Top findings sorted by severity, with [CONVERGENT] flag for ≥2-reviewer agreement
   - Cross-family disagreements highlighted (⚠️) with manual-verification reminder
   - Naive-layer catches (only Sonnet/Haiku found)
   - Too-clean flags
   - Stats
   - Decision menu with shortcuts (PROCEED / REJECT: ... / DIRECTED: ...)

   The output is plain text (no markdown headers) — paste-friendly into any chat.

   Manual format if you want to compose by hand:

   ```
   Consilium synthesis ready (M-tier, iter N):
   - Aggregate verdict: {satisfied | rework_required | director_review_required}
   - Convergent findings (≥2 reviewers agree): {N critical, N major, N minor — list 1-line summaries}
   - Cross-family disagreements (peer-opus vs codex): {N — flag if any}
   - Naive-layer catches (Sonnet/Haiku found, stronger reviewers missed): {N}
   - Suspicious_too_clean flags: {list reviewers}

   Full detail: engagement/consilium-summary.md

   Your call — paste back ONE of:
     PROCEED              → director writes formal verdict per consilium
     REJECT: <reasons>    → minimal REJECT, lead reworks per your reasons
     DIRECTED: <decisions>→ director constrained by your specifics
                            (e.g. "address finding-1; SIDED WITH codex-blind on auth")
   ```

   Human types short verdict in chat (one line is enough). Coordinating agent then runs:

   ```bash
   # PROCEED
   python ~/.claude/scripts/human-directive.py engagement/ --decision PROCEED [--note "..."]

   # REJECT with reasons
   python ~/.claude/scripts/human-directive.py engagement/ --decision REJECT \
       --reasons "fix CSRF gap; add dark mode toggle"

   # DIRECTED with address + overrides
   python ~/.claude/scripts/human-directive.py engagement/ --decision DIRECTED \
       --address "finding-1, finding-3" \
       --override "SIDED WITH codex-blind on auth dispute"
   ```

   The script writes well-formed `engagement/human-directive.md` with `Decision:` line that `handoff-precheck` parses. Aliases supported: `GO`/`OK` → PROCEED, `NO`/`RW` → REJECT, `MIXED`/`PARTIAL` → DIRECTED.

   **Manual fallback (free-form):** human can still write `engagement/human-directive.md` directly using the schema in the script's templates. Or pipe a free-form body via `--raw`:
   ```bash
   echo "Decision: PROCEED_TO_VERDICT\n\nNote: ..." | python ~/.claude/scripts/human-directive.py engagement/ --raw
   ```

   This step is the human's filter on adversary signal: filler / false-positive findings get dismissed before director processes them. Human carries final accountability — director is no longer rubber-stamp target.

7. **Director acts per directive:**
   - **PROCEED_TO_VERDICT**: director writes formal verdict in `acceptance-log.md`, addresses every consilium signal (SUSTAINED/OVERRULED for convergent, SIDED WITH X for cross-family disagreements, REAL/FALSE_POSITIVE for naive catches, ACKNOWLEDGED for too-clean flags).
   - **REJECT_NOW**: director writes minimal verdict `### Verdict: REJECT` referencing human-directive.md, lead immediately starts rework iteration. No long director adjudication needed — human already decided.
   - **DIRECTED_VERDICT**: director writes verdict per human's mandatory addresses + overrides. Other adversary signals director still adjudicates (SUSTAINED/OVERRULED markers required).

8. **Mechanical post-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=M now includes `human-directive` and `director-verdict` checks. Both must pass before engagement archival.

9. **Human confirms** with 1-line ack appended to acceptance-log.md if PROCEED_TO_VERDICT or DIRECTED_VERDICT. (REJECT_NOW already implies rework loop.)

### M-tier iteration

**2 rounds max.** After round 2 → escalate to user with both rounds' adversary findings + lead's responses.

### What director does NOT do on M

- Does NOT re-run validators (adversary covers second-opinion role)
- Does NOT write cross-validation tables (lead's job pre-handoff)
- Does NOT review own past verdicts (each iteration is fresh judgement)

---

## L-tier acceptance

**Human-as-supreme-judge with full consilium.** Five reviewers across capability and family axes; human decides after consilium synthesis; director writes formal verdict per human directive.

### Steps

1. **Lead completes work**, writes full handoff (all 11 sections per `engagement-protocol`).
2. **Lead runs full methodology validator suite** (every applicable validator for domain + ux_heavy + cross-domain).
3. **Lead runs mechanical pre-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=L → 21 checks. Exit 0 required (some skip until acceptance phase artefacts exist).
4. **Trigger consilium with two-pass protocol per reviewer:**
   ```bash
   python ~/.claude/scripts/adversary_lg.py engagement/ --consilium L
   ```
   Each of 5 reviewers runs Pass 1 on a curated copy (no handoff visible), then Pass 2 on full engagement with preliminary findings injected. Roles:
   - **peer-opus** — Anthropic peer review
   - **codex-blind** — Codex CLI, fully independent (no peer findings shown in Pass 2)
   - **codex-informed** — Codex CLI, Pass 2 sees peer findings, focuses on gaps
   - **sonnet-scoped** — common-sense check ("does deliverable match plain criteria wording?")
   - **haiku-scoped** — naive obvious-miss check (typos, count mismatches, missing pieces)
   - Outputs per role:
     - `engagement/validation-outputs/{role}-iter-{N}-preliminary-{ts}.json`
     - `engagement/validation-outputs/{role}-iter-{N}-{ts}.json`
5. **Synthesize:**
   ```bash
   python ~/.claude/scripts/consilium-synth.py engagement/
   ```
   Writes `engagement/consilium-summary.md` with:
   - Convergent findings (≥3 reviewers agree → high confidence)
   - Cross-family disagreements (peer-opus vs codex-blind diverge → framing contamination signal)
   - Naive-layer catches (Sonnet/Haiku found something stronger reviewers missed → obvious-miss flag)
   - Suspicious-too-clean flags
   - Similarity matrix (transparency: pairs of unmerged findings with their similarity)
   - Aggregate verdict + statistics
6. **HUMAN reads consilium-summary.md as supreme judge.** Same chat-driven flow as M-tier above: director presents inline summary, human types short verdict in chat (PROCEED / REJECT: ... / DIRECTED: ...), coordinating agent invokes `python ~/.claude/scripts/human-directive.py engagement/ --decision ...` to scaffold the file.

   **L-tier additional obligation:** human MUST manually verify any cross-family disagreements (peer-opus vs codex-blind) before deciding — these are framing-contamination signals and warrant direct inspection of disputed code/artefact. The chat presentation of consilium SHOULD highlight cross-family disagreements explicitly with the disputed-finding's evidence path so human can quickly inspect.

7. **Director acts per directive (same as M-tier).** L-tier additional obligations on PROCEED_TO_VERDICT and DIRECTED_VERDICT:
   - Every cross-family disagreement gets explicit SIDED WITH X or SPLIT marker
   - Every naive-layer catch gets REAL or FALSE_POSITIVE marker
   - Every suspicious_too_clean reviewer gets ACKNOWLEDGED marker
   - May request **specific validator re-run** (max 1 per validator per iter) only if adversary findings identify validator coverage gap

8. **Mechanical post-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=L now includes `human-directive` and `director-verdict` checks. Both must pass.

9. **Human confirms** with 1-line ack appended to acceptance-log.md (or REJECT_NOW skips this since rework loop already triggered).

### L-tier iteration

**3 rounds max.** After round 3 → escalate to user with full audit trail (3 rounds × 5 adversary outputs + director verdicts).

### Cost / wall-clock targets (L-tier)

- Adversary consilium: ~10-20 min wall-clock (parallel execution)
- Cost: ~$20-40 per iteration in adversary tokens (Opus + 2× Codex + Sonnet + Haiku)
- Director synthesis: ~10-15 min reading + writing
- Total acceptance phase: ~30-45 min

This is the most expensive acceptance, applied to the most expensive engagements. Producer cost on L is typically $50-150 — adversary stack is ~25-50% of producer cost.

---

## Cross-tier rules (apply at every tier)

### ux_heavy gradient

`ux_heavy: true | minor | false` — independent of tier. Determines evidence type:
- `true` → Playwright traces required, screens captured, accessibility-validator must run
- `minor` → screens captured, accessibility-validator recommended
- `false` → no UX-specific artefacts required

ux_heavy never makes acceptance lighter; only tier does that.

### Validator selection

Determined by domain + ux_heavy + scope, NOT by tier:
- backend code touched → security-auditor + code-reviewer
- UI surfaces touched → critique + accessibility-validator + ux-review (if ux_heavy)
- migrations → migration-validator
- new tests → test-reviewer
- prompts → prompt-reviewer
- docs touched → documentation-reviewer

S-tier engagement that touches auth code STILL needs security-auditor. Tier scales acceptance rigour, not safety baseline.

### Danger-scan

Tier-independent. Every tier runs `danger-scan.py`. DROP TABLE / force-push / prod deploy / secret rotation / bulk delete → user OK in `scope-sync.md` mandatory regardless of tier.

### Per-engagement reflection (M/L only — feeds SkillOpt below threshold)

After writing the verdict (ACCEPT or REJECT) on every M/L engagement, the manager appends **0–3 reflections** to `engagement/engagement-reflections.md` (append-only). The file's whole purpose is feeding the director's monthly reflection sweep — patterns that don't reach SkillOpt's ≥3-same-class threshold within a single engagement but accumulate across many.

**Strict constraint — write a reflection ONLY when:**
- the failure points at a specific `skill: X` or `agent: Y` rule that should change, AND
- you can classify it as `rule_missing` / `rule_wrong` / `rule_ignored` (the SkillOpt taxonomy).

**Discard:** generic observations ("tests took long", "we had a typo", "could've been faster", "validator was slow"). Noise here surfaces as false signals at scale and degrades the director's signal-to-noise.

**Format** (one block per reflection, append-only):
```
## Reflection — {engagement-name} — {YYYY-MM-DD} — verdict: {ACCEPT|REJECT}

- target: {skill: X | agent: Y}
  class: rule_missing | rule_wrong | rule_ignored
  observation: {1–2 lines describing the gap}
  evidence: {acceptance-log path / validator output path / consilium path}
```

**Zero reflections is a valid outcome** — a clean engagement with nothing to change should leave `engagement-reflections.md` empty (file may not exist at all). Inventing reflections to look productive corrupts the signal.

Director's monthly sweep clusters these by `target × class` and triggers SkillOpt cycles when cluster size ≥3 OR when Langfuse trend Δ crosses thresholds (see `system-optimization-protocol` §"Trigger" Layer 3 pathway).

### SkillOpt readiness signal (run after writing reflections / signals)

After the verdict + any reflections/signals are written, run `python ~/.claude/scripts/skillopt-ready.py`. If it reports a bucket **DUE** (≥3 same-class, loop-actionable live signals), surface it to the user in the engagement summary — e.g. "SkillOpt cycle due for dev (3× rule_wrong) → run `прогнать skill-evolution dev`". This is the immediate path; a SessionStart hook re-runs the same check every session as a safety net, so a missed surfacing is caught next session. The checker excludes `dryrun:` / `resolved:` and script-only-targeted signals, so it does not false-fire.

### Engagement = directory

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

---

## Auto-promote handling (tier shifts mid-engagement)

`size-detect.py --mode runtime` detects scope drift and may auto-promote S→M or M→L. **Promotion is one-way; demotion is forbidden.**

### Behaviour on promotion

1. `criteria.md` frontmatter rewritten (`size: S` → `size: M`)
2. `scope-sync.md` appended:
   ```markdown
   ## Auto-promote S → M @ {timestamp}
   Trigger metrics: {specialists, diff_files, ui_surfaces, deploy_involvement}
   New acceptance: M-tier (Opus adversary required)
   Iteration budget revised: +1 round expected for adversary findings
   ```
3. **Iteration budget bumped +1** on this engagement (M default 2 → 3; L default 3 → 4)
4. **Acceptance protocol switches to NEW tier retroactively** at handoff.

### Why retroactive (not next-iter)

Acceptance is the gate. Shipping work that's M-shaped through S-acceptance ships gaps. Adversary review on auto-promoted engagement may find more gaps than fresh M-tier work — that's correct behaviour, the work was produced under lighter mode.

### Detection points

- After every Phase heartbeat, lead invokes `size-detect.py --mode runtime`
- Pre-handoff, `handoff-precheck.py` includes `size-drift` check (M and L tier sets) → if observed > current, FAIL handoff with directive to auto-promote
- Lead must address gaps **before** handoff once promoted — don't accumulate to acceptance-time surprise

### Consequences

- S → M promotion: producer must run methodology validators (didn't on S), pass M's 11-check pre-check, expect adversary pass at acceptance
- M → L promotion: must produce `tasks/INDEX.md` (L requires task decomposition), expect full consilium at acceptance

---

## Verdict format

The verdict is binary: **ACCEPT** or **REJECT**. There is no third option. `ACCEPT CONDITIONAL`, `ACCEPT pending X`, `ACCEPT — user to verify Y` are all forbidden — they push QA back onto the user, which is exactly what the agency model exists to prevent.

If validation cannot be completed (Docker not running, Playwright unavailable, DB unreachable, secrets missing): the verdict is **REJECT** with reason `validation incomplete: <specific tool/artefact>`. Coordinate with the lead and (if needed) escalate ONCE to the user to bring validation environment online — then re-review. Do not defer the verification itself to the user.

### Canonical form (machine-parseable, structurally enforced)

`engagement/acceptance-log.md` (append, never overwrite). M/L tier verdicts MUST include the **Adversary findings adjudication** section with explicit markers per consilium signal — `director-verdict-check.py` enforces this mechanically.

#### M/L tier ACCEPT template

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

#### M/L tier REJECT template

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

#### S-tier verdict template (no director, human writes directly)

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

#### Adjudication marker reference

| Signal type | Required marker(s) |
|---|---|
| Convergent finding (≥2 reviewers) | `SUSTAINED` or `OVERRULED` per finding |
| Cross-family disagreement | `SIDED WITH <reviewer>` or `SPLIT` per disagreement |
| Naive-layer catch | `REAL` or `FALSE_POSITIVE` per catch |
| Suspicious_too_clean | `ACKNOWLEDGED` per flagged reviewer |

`director-verdict-check.py` parses verdict text and verifies that each consilium signal has a corresponding marker. Missing markers → handoff-precheck FAIL on `director-verdict` check.

### Path verification

After writing ACCEPT, BEFORE archival, run:
```bash
python ~/.claude/scripts/handoff-paths-check.py engagement/acceptance-log.md --json
```
Every path in criteria-trace's "Evidence path" column must resolve to a real file. Phantom paths in ACCEPT are particularly insidious — they look like trail-of-evidence but reference vapour. Non-zero exit → fix verdict before posting to user.

---

## Iteration loop

The counter is informational. **Slot language is banned** — no "slot 1/2 used", "last attempt", "final round". That language pressures premature accepts.

### Triggers for escalation (root-cause based, not counter-based)

- **Repeating-critique trigger (highest priority):** if a blocking item from iteration N appears in iteration N+1 with the same root cause, escalate IMMEDIATELY. Loop detected — more rework will not fix it.
- **Pre-final-iteration trigger:** before starting the last allowed iteration (S=1, M=2, L=3), escalate to user with current blockers and ask whether to continue or revise scope.
- **Hard limits:**
  - S: 1 iteration. REJECT → human directive.
  - M: 2 iterations. After round 2, escalate.
  - L: 3 iterations. After round 3, escalate.
  - Auto-promoted engagements: budget +1 (so promoted-S becomes M with 3 max, etc.)

### Escalation message template (Russian, per global CLAUDE.md)

```
После {N} раундов правок не могу принять работу. Текущие блокеры:
- {blocking 1} — {root cause from adversary findings}
- {blocking 2} — {root cause}

Adversary findings location: engagement/consilium-summary.md
Validator outputs: engagement/validation-outputs/

Варианты: продолжить ещё круг / пересмотреть criteria / закрыть как unresolvable.
```

When loop signals "criteria are wrong, not the work" — route back to `agency-intake` for new/updated `criteria.md`, do not throw rework at lead.

---

## Scope sync (the only pre-execution interaction, M/L only)

On M and L tiers, once per engagement before lead starts Phase 2 planning, director MAY:
- Read `criteria.md`
- Ask lead ONE clarifying question about criterion interpretation
- Lock criteria by writing `engagement/scope-sync.md` with Q/A and director signature

### When scope sync is MANDATORY (not optional)

1. `criteria.md` has `ux_heavy: true` — director double-checks classification. If domain=dev and criteria mention only API/data, push back: "ux_heavy looks wrong, propose `false`?".
2. `criteria.md` has `ux_heavy: false` AND scope text mentions `screen|page|dashboard|landing|UI|интерфейс|экран|страница` — flag potential under-classification.
3. `criteria.md` "Done when" has fewer than 2 measurable bullets, OR any bullet is taste-vague ("clean", "professional") without objective bar — demand sharpening.
4. `tools_required` is empty for dev/design engagement (almost certainly missed) — ask lead to enumerate.

After scope sync, director does NOT interact with lead until handoff. No mid-execution consultation. **S-tier has no scope sync** — secretary intake is sufficient.

If criteria change mid-engagement (user request): new scope sync required, iteration counter resets.

---

## Observability

After each iteration, append one line to `~/.claude/projects/{project}/metrics.jsonl`:

```json
{"ts":"2026-05-09T15:30:00Z","engagement":"acme-landing","domain":"design","director":"design-director","tier":"M","iter":2,"verdict":"reject","blocking_count":3,"adversary_roles":["peer-opus"],"adversary_verdict":"rework_required","duration_s":180,"tokens_used":68421}
```

New required fields (tiered acceptance):
- `tier` — S | M | L (the tier at acceptance time, after any auto-promote)
- `adversary_roles` — list of roles that ran (empty on S)
- `adversary_verdict` — aggregate from consilium-summary.md (or "n/a" on S)

Read `metrics.jsonl` directly (one JSON per line) for retrospectives or to compute reject rate / iter distribution / adversary-overrule ratio by tier. A dedicated summarizer / dashboard is deferred until LangSmith integration lands (no live summarizer script today).

---

## Anti-patterns

- **Don't issue `ACCEPT CONDITIONAL` or any non-binary verdict.** Tool unavailability = REJECT with `validation incomplete`.
- **Don't accept "user will verify"-style claims.** Agency exists to remove that burden.
- **Don't plan or redirect lead's approach.** Reject with evidence, let lead rework.
- **Don't fix artefacts yourself.** Even one-line fix belongs to the lead. Acceptor, not co-author.
- **Don't accept with "LGTM".** Every accept references the criteria trace.
- **Don't reject on style / taste alone.** Only on criteria mismatch, validator failures, contradictions, unsupported claims, out-of-whitelist files.
- **Don't re-run validators in sweep style.** That's the old protocol. M/L use adversary for second opinion. Validator re-run only when adversary findings identify specific coverage gap (max 1 per validator per iter, L only).
- **Don't run director phase on S-tier.** S has no director. Producer self-attest + mechanical + human glance.
- **Don't skip adversary on M.** That's the whole point of M acceptance — adversary breaks framing contamination.
- **Don't skip consilium on L.** Single Opus adversary on L misses cross-family blind spots.
- **Don't loop silently.** Escalate immediately on repeating critique. Counter-based escalation is the floor.
- **Don't write "slot N/M" anywhere.** Slot language banned across all agency artefacts.
- **Don't demote tier mid-engagement.** Auto-promote is one-way; if scope shrinks, acceptance still uses higher tier.
