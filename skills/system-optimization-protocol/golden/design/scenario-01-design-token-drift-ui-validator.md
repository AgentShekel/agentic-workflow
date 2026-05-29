# Scenario 01 — design-token-drift-ui-validator

## Situation

A design engagement (M-tier) ships `engagement/ui/dashboard.html` containing
inline styles `style="background:#1a73e8; color:#ffffff;"` on primary CTA
buttons. The engagement's `design-research.md` (produced by
`design-system-researcher`) explicitly listed semantic tokens
`--color-primary` and `--color-on-primary` mapped to those exact hex
values. The ui-designer ignored the token layer and used raw hex.
`critique` validator and `design-ui-designer` self-attest were run as
part of `validator_lg.py --auto` on this iteration.

## Expected behavior (before-edit baseline)

- `critique` validator flags the raw-hex usage with severity ≥ high in its
  JSON output `findings` array, citing both `dashboard.html` and the
  ignored tokens from `design-research.md`. `canonical.verdict` resolves
  to `changes_required`.
- An accompanying `design-ui-designer` self-attest section in the
  executor-report acknowledges the deviation (or the validator catches
  the omission).
- Findings reach `validation-outputs/` and flow into
  `consilium-summary.md` synthesis on M/L tiers.

## Failure mode it must catch

`rule_ignored` — `design-ui-designer` agent body OR `ui-styling-guide`
skill mentions "use tokens, not raw hex" but no enforcing validator step
binds the rule to artefacts. Result: visually identical UI ships, but
later theme changes (dark mode rollout, brand refresh) require search-
and-replace across raw hex strings rather than flipping token values.
The drift surfaces 3 months later as "dark-mode looks broken on the
dashboard, the rest of the app works fine."

## Pass criteria

- `critique` validator output has at least one finding with
  `severity ∈ {critical, high}` AND `category` mentioning "token" /
  "design-system" / "hex" / "hardcoded color".
- The finding's `evidence` field includes a concrete file path
  (`engagement/ui/dashboard.html` or equivalent) AND a line / selector
  reference.
- `canonical.verdict` from `critique` resolves to one of
  `changes_required` / `suspicious` (not `approved` /
  `approved_with_caveats`).
- Ledger emits `validator_completed` event with `verdict=REJECT` for
  `critique`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for design
domain parity with dev)
