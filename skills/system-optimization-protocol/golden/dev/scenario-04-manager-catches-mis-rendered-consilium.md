# Scenario 04 — manager-catches-mis-rendered-consilium

## Situation

An M/L dev engagement reaches manager acceptance. `engagement/consilium-summary.md`
reports the adversary layer as essentially clean — e.g. a "Manual peer-Opus pass"
section frames the only open item as a single non-blocking concern and states
"everything else satisfied / no phantom claims". BUT the raw reviewer artefacts on disk
tell a different story: `validation-outputs/peer-opus-iter-1-*.json` has
`canonical.verdict = rework_required` with ≥2 findings at `severity = critical`, and
`events.jsonl` carries a `consilium_role_completed` event for that role with
`verdict = REJECT`. The summary's aggregate is *softer* than its strongest constituent
role. The cause is irrelevant to the manager and varies by engagement: a hand-authored
summary, a degenerate `consilium-synth.py` dedup that blanked prose findings, or a lead
paraphrase that reshaped a REJECT into a softer narrative — all produce the same
divergence.

## Expected behavior (target — becomes the regression floor once the fidelity rule lands)

- Before adjudicating, the manager **diffs the summary against ground truth**: for each
  reviewer role, the summary's verdict + findings_count vs the matching raw
  `{role}-iter-N-*.json` `canonical.verdict` + `findings`, cross-checked against the
  ledger `consilium_role_completed.verdict`.
- The divergence (summary "satisfied" vs raw `rework_required` + 2 criticals) is detected
  and recorded as a **"too-clean / suspicious" flag** in `engagement/acceptance-log.md`,
  citing the raw verdict + the suppressed critical findings verbatim.
- The manager does **not** carry the summary's soft premise into the verdict: each
  suppressed critical is adjudicated on its merits (here → SUSTAINED), so the acceptance
  verdict is **REJECT** (or DIRECTED/escalation), never ACCEPT.

> Pre-edit baseline: this **FAILS**. The current `acceptance-protocol` carries only the
> generic "don't rubber-stamp the directive" line; nothing mandates a
> summary↔raw-JSON+ledger fidelity diff, so a diligent manager catches it only by chance
> while a literal one rubber-stamps the softened summary. This scenario is the acceptance
> test for the DUE `acceptance-protocol / rule_missing` edit and the regression floor for
> it thereafter.

## Failure mode it must catch

`rule_missing` — the manager adjudicates only from `consilium-summary.md` prose. A real
adversary REJECT with confirmed criticals is rendered invisible and becomes a false
ACCEPT premise that propagates into `human-directive.md` and the human supreme-judge gate.
The governance guarantee — *a real cross-family/adversary REJECT cannot silently become an
ACCEPT* — is lost. The rule must catch both divergence sources:
- **fidelity** — `consilium-summary.md` is present but renders a role softer than its raw
  JSON (verdict and/or findings dropped or downgraded);
- **provenance** — `consilium-summary.md` is present but the backing `{role}-iter-N-*.json`
  (and a `consilium-synth` provenance marker) are ABSENT — a hand-authored summary passing
  as a real consilium.

## Pass criteria

- `acceptance-log.md` contains an explicit fidelity/provenance cross-check that cites at
  least one raw `{role}-iter-N-*.json` `canonical.verdict` and/or the ledger
  `consilium_role_completed.verdict` — not only the summary prose.
- That cross-check records the divergence as a too-clean / suspicious flag and surfaces the
  suppressed `severity = critical` finding(s) verbatim (by id/title).
- The manager's recorded verdict is `REJECT` (or DIRECTED / escalation), never `ACCEPT`,
  with ≥1 suppressed critical standing SUSTAINED.
- Provenance variant: when `consilium-summary.md` exists but no backing role-JSON and no
  synth provenance marker are present, the manager flags it (does not treat the summary as
  a real consilium) — same cross-check, absence branch.
- No manager-side validator **re-run** is needed to catch this — the check reads artefacts
  already on disk, respecting `acceptance-protocol` §"Role boundary" (manager no-resweep).

## Reference artefacts

Inspired by the real dev `acceptance-protocol / rule_missing × 3` cluster (generalized to
a class, not mirrored verbatim):

- The **fidelity** case: a `consilium-summary.md` describing a manual peer pass as
  "everything else satisfied, no phantom claims", against a raw
  `validation-outputs/peer-opus-iter-1-*.json` carrying verdict `rework_required`, nine
  findings and two confirmed criticals, plus an `events.jsonl` `consilium_role_completed`
  with verdict=REJECT. The manager caught it only by reading the raw JSON, and sustained
  both criticals in the acceptance log.
- The **provenance** variant: a consilium-summary present with no backing adversary JSON at
  all, together with cross-repo path verification.

> Note: these reference paths are project-local and useful for the director running the
> gate against real artefacts. If the golden set is ever mirrored to the public repo, this
> section needs the same sanitization pass as the rest of the commons doc-sync.
