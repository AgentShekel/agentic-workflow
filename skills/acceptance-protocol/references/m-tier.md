# M-tier acceptance

> Loaded from `acceptance-protocol` SKILL.md when `criteria.md` frontmatter `size: M`.

**Contents:** Steps (1–9) · Adversary runbook · M-tier iteration · What director does NOT do on M

**Human-as-supreme-judge flow with lightweight director.** Adversary pass injected between mechanical checks and human review. Director writes formal verdict per human's directive.

## Steps

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

   > **Runbook — the consilium runs IN-SESSION (M and L alike).** `adversary_lg.py` dispatches each
   > reviewer as a `claude -p` subprocess that rides your subscription: it self-bootstraps its venv,
   > self-discovers the claude binary even when off PATH, and grants the reviewer read-only
   > Read/Glob/Grep on the engagement. It is NOT a separate "director sub-process stack" and is NOT
   > "unavailable" inside an agent session. If a role errors on permissions/PATH/venv, that is a bug
   > to fix or escalate ONCE — **never silently skip the consilium or substitute independent-validator
   > judgment for it** (this exact misdiagnosis skipped the consilium on every engagement before the
   > 2026-06-01 dispatch-gap fix).
   >
   > **The hang is fixed — "adversary_lg hangs" is NOT valid grounds to waive (2026-06-02).** The
   > empty-timeout reviewer hang (a headless `claude -p`/`codex` blocking on inherited stdin) was
   > fixed and then field-confirmed: a later engagement ran
   > the full L consilium clean — 5/5 roles × 2 iterations, real per-role JSON + a script-generated
   > `consilium-summary.md`, and cross-family Codex caught a real path-traversal the validators
   > missed. A `criteria.md` §note that waives the consilium on "adversary_lg hangs / empty timeout"
   > grounds is now STALE and INVALID — the engine runs in-session; run it. (Cross-repo deliverables
   > — a donor->host transplant — need the host repo granted to the claude-family reviewers: set
   > `criteria.md` `extra_roots:` or pass `adversary_lg.py --extra-add-dir <host-repo>` per Finding B,
   > do not waive.)

5. **Synthesize:**
   ```bash
   python ~/.claude/scripts/consilium-synth.py engagement/
   ```
   Writes `engagement/consilium-summary.md`.

   > **(M/L) Before step 6**, complete the **Consilium fidelity/provenance cross-check** and append it to `acceptance-log.md` — see [cross-tier-rules.md](cross-tier-rules.md) §"Consilium fidelity + provenance cross-check".

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
   - **PROCEED_TO_VERDICT**: director writes formal verdict in `acceptance-log.md`, addresses every consilium signal (SUSTAINED/OVERRULED for convergent, SIDED WITH X for cross-family disagreements, REAL/FALSE_POSITIVE for naive catches, ACKNOWLEDGED for too-clean flags). Verdict templates: [verdict-format.md](verdict-format.md).
   - **REJECT_NOW**: director writes minimal verdict `### Verdict: REJECT` referencing human-directive.md, lead immediately starts rework iteration. No long director adjudication needed — human already decided.
   - **DIRECTED_VERDICT**: director writes verdict per human's mandatory addresses + overrides. Other adversary signals director still adjudicates (SUSTAINED/OVERRULED markers required).

8. **Mechanical post-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=M now includes `human-directive` and `director-verdict` checks. Both must pass before engagement archival.

9. **Human confirms** with 1-line ack appended to acceptance-log.md if PROCEED_TO_VERDICT or DIRECTED_VERDICT. (REJECT_NOW already implies rework loop.)

## M-tier iteration

**2 rounds max.** After round 2 → escalate to user with both rounds' adversary findings + lead's responses. Escalation triggers + template: [process-rules.md](process-rules.md) §"Iteration loop".

## What director does NOT do on M

- Does NOT re-run validators (adversary covers second-opinion role)
- Does NOT write cross-validation tables (lead's job pre-handoff)
- Does NOT review own past verdicts (each iteration is fresh judgement)
