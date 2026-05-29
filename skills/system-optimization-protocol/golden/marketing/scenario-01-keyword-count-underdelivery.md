# Scenario 01 — keyword-count-underdelivery

## Situation

A marketing engagement (M-tier) has `criteria.md` "Done when":
- ≥200 missed-demand keywords from Wordstat, clustered by intent
- Each cluster has ≥3 keywords and an intent label

`marketing-keyword-researcher` runs and returns
`engagement/executor-reports/marketing-keyword-researcher.md` claiming
"Wordstat semantic core: 47 missed-demand keywords across 8 clusters."
The producer self-attests handoff §3 criteria trace as ✅. `critique`
validator and `completeness-validator` run as part of `validator_lg.py
--auto` validation set.

## Expected behavior (before-edit baseline)

- `completeness-validator` flags criterion-vs-deliverable count mismatch
  with severity ≥ high: criterion specifies ≥200, deliverable has 47.
- `critique` independently flags the same gap.
- `canonical.verdict` for both validators resolves to `changes_required`.
- Findings cite the specific criterion bullet and the specific count
  reported in the executor-report.

## Failure mode it must catch

`rule_ignored` — `completeness-validator` agent body / `validation-pipeline`
skill mentions "verify criteria trace" but the validator implementation
treats a ✅ self-attest in handoff §3 as authoritative without
cross-checking against the actual deliverable count. Result:
engagement ships claiming "criteria met" with 4x undercount; user
launches campaign expecting 200-keyword semantic core but builds out
47-keyword ad-groups; PPC budget burns on a much narrower target.

## Pass criteria

- `completeness-validator` JSON output has at least one finding with
  `severity ∈ {critical, high}` AND `category` mentioning
  "criteria-trace" / "count-mismatch" / "deliverable-undercount".
- The finding cites BOTH the criterion bullet (verbatim or by `crit-N`
  reference) AND the actual count from the executor-report.
- `canonical.verdict` from `completeness-validator` resolves to
  `changes_required`.
- Ledger emits `validator_completed` event with `verdict=REJECT` AND
  `canonical_verdict="changes_required"` for `completeness-validator`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for marketing
domain parity with dev)
