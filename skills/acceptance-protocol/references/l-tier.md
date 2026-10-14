# L-tier acceptance

> Loaded from `acceptance-protocol` SKILL.md when `criteria.md` frontmatter `size: L`.

**Contents:** Steps (1–9) · L-tier iteration · Cost / wall-clock targets

**Human-as-supreme-judge with full consilium.** Five reviewers across capability and family axes; human decides after consilium synthesis; director writes formal verdict per human directive.

## Steps

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

   > The consilium runs IN-SESSION — see the Runbook in [m-tier.md](m-tier.md) §step 4 (applies M and L alike: never silently skip; "adversary_lg hangs" is a stale waiver).

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

   > **(M/L) Before step 6**, complete the **Consilium fidelity/provenance cross-check** and append it to `acceptance-log.md` — see [cross-tier-rules.md](cross-tier-rules.md) §"Consilium fidelity + provenance cross-check".

6. **HUMAN reads consilium-summary.md as supreme judge.** Same chat-driven flow as M-tier (see [m-tier.md](m-tier.md) §step 6): director presents inline summary, human types short verdict in chat (PROCEED / REJECT: ... / DIRECTED: ...), coordinating agent invokes `python ~/.claude/scripts/human-directive.py engagement/ --decision ...` to scaffold the file.

   **L-tier additional obligation:** human MUST manually verify any cross-family disagreements (peer-opus vs codex-blind) before deciding — these are framing-contamination signals and warrant direct inspection of disputed code/artefact. The chat presentation of consilium SHOULD highlight cross-family disagreements explicitly with the disputed-finding's evidence path so human can quickly inspect.

7. **Director acts per directive (same as M-tier — see [m-tier.md](m-tier.md) §step 7).** L-tier additional obligations on PROCEED_TO_VERDICT and DIRECTED_VERDICT:
   - Every cross-family disagreement gets explicit SIDED WITH X or SPLIT marker
   - Every naive-layer catch gets REAL or FALSE_POSITIVE marker
   - Every suspicious_too_clean reviewer gets ACKNOWLEDGED marker
   - May request **specific validator re-run** (max 1 per validator per iter) only if adversary findings identify validator coverage gap

   Verdict templates: [verdict-format.md](verdict-format.md).

8. **Mechanical post-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=L now includes `human-directive` and `director-verdict` checks. Both must pass.

9. **Human confirms** with 1-line ack appended to acceptance-log.md (or REJECT_NOW skips this since rework loop already triggered).

## L-tier iteration

**3 rounds max.** After round 3 → escalate to user with full audit trail (3 rounds × 5 adversary outputs + director verdicts). Escalation triggers + template: [process-rules.md](process-rules.md) §"Iteration loop".

## Cost / wall-clock targets (L-tier)

- Adversary consilium: ~10-20 min wall-clock (parallel execution)
- Cost: ~$20-40 per iteration in adversary tokens (Opus + 2× Codex + Sonnet + Haiku)
- Director synthesis: ~10-15 min reading + writing
- Total acceptance phase: ~30-45 min

This is the most expensive acceptance, applied to the most expensive engagements. Producer cost on L is typically $50-150 — adversary stack is ~25-50% of producer cost.
