# Scenario 03 — dark-mode-contrast-fail

## Situation

A design engagement (M-tier, `ux_heavy: true`) updates the dark-mode
color palette in `engagement/design-system/tokens.css`. New tokens:
- `--color-text-secondary: #6b7280` on `--color-surface-dark: #1f2937`
  background — measured contrast 3.8:1.

WCAG AA requires 4.5:1 for normal body text, 3:1 for large text only.
The engagement's `criteria.md` "Done when" includes "dark mode meets
WCAG AA contrast across all surfaces". Light-mode tokens are unchanged
and pass.

`accessibility-validator` runs as part of `validator_lg.py --auto`
validation set on both light and dark theme screenshots captured under
`engagement/screens/iter-1/{light,dark}/`.

## Expected behavior (before-edit baseline)

- `accessibility-validator` measures contrast pair on dark theme,
  computes ratio < 4.5:1, flags finding with severity ≥ high.
- Finding cites the specific token pair (`--color-text-secondary` on
  `--color-surface-dark`), computed ratio (3.8:1), and target (4.5:1).
- `canonical.verdict` resolves to `changes_required`.

## Failure mode it must catch

`rule_wrong` — `accessibility-validator` color-contrast check currently
runs against light-mode screens only (legacy default), missing the dark
theme entirely. Result: contrast violations introduced on dark surfaces
slip through; the validator reports "color-contrast: OK (4.6:1 average
on light surfaces)" while the dark theme has 3.8:1 violations on the
exact same text role.

## Pass criteria

- `accessibility-validator` JSON output has at least one finding from
  the **dark theme** screenshot pass (not light-only).
- The finding has `severity ∈ {critical, high}` AND `category` includes
  "color-contrast" verbatim.
- The finding's `metrics` or evidence field reports the measured ratio
  (must be a number < 4.5) AND the token / class name responsible.
- `canonical.verdict` from `accessibility-validator` resolves to
  `changes_required`.
- Ledger emits `validator_completed` event with `verdict=REJECT` AND
  `canonical_verdict="changes_required"` for `accessibility-validator`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for design
domain parity with dev)
