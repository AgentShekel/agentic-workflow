# Scenario 03 — dark-mode-contrast-fail

## Situation

A design engagement (M-tier, `ux_heavy: true`) updates the dark-mode
color palette in `engagement/design-system/tokens.css`. New tokens:
- `--color-text-secondary: #6b7280` on `--color-surface-dark: #1f2937`
  background — WCAG contrast 3.04:1. The pair is applied to body-size
  text (13-14px) through a `[data-theme="dark"]` override of the panel
  background, so the failure is only visible once the theme cascade is
  resolved.

WCAG AA requires 4.5:1 for normal body text, 3:1 for large text only.
The engagement's `criteria.md` "Done when" includes "dark mode meets
WCAG AA contrast across all surfaces". Light-mode tokens are unchanged
and pass.

`accessibility-validator` runs as part of `validator_lg.py --auto`
validation set over the engagement's token and UI source files (the
validator reads source, not screenshots).

## Expected behavior (before-edit baseline)

- `accessibility-validator` measures contrast pair on dark theme,
  computes ratio < 4.5:1, flags finding with severity ≥ high.
- Finding cites the specific token pair (`--color-text-secondary` on
  `--color-surface-dark`), computed ratio (3.04:1), and target (4.5:1).
- `canonical.verdict` resolves to `changes_required`.

## Failure mode it must catch

`rule_wrong` — `accessibility-validator` color-contrast check currently
runs against light-mode screens only (legacy default), missing the dark
theme entirely. Result: contrast violations introduced on dark surfaces
slip through; the validator reports "color-contrast: OK (4.6:1 average
on light surfaces)" while the dark theme has 3.04:1 violations on the
exact same text role.

## Pass criteria

Fields are the ones `accessibility-validator` emits (`wcagCriterion`,
`pattern`, `issue`, `severity`); severities are canonical (see README).

- At least one finding flags the failing **dark-theme** text colour:
  `--color-text-secondary` (or `#6b7280`) on a dark surface. Naming the
  wrong dark background (the page surface `#111827` instead of the panel's
  `#1f2937`) still passes: the outcome, the failing token caught and the
  change blocked, is what matters (outcome rule). The light
  theme or a white background does not pass.
- That finding has `severity ∈ {critical, high}` and is a contrast
  finding (`wcagCriterion` 1.4.3, or `pattern`/`issue` naming contrast).
- The same finding reports a measured ratio below 4.5:1 and the token or
  class responsible.
- Strict (precision, reported separately, not required): the finding names
  the exact pair on `--color-surface-dark` and its ratio is 3.04:1 within
  rounding.
- `canonical.verdict` from `accessibility-validator` resolves to
  `changes_required`.
- Ledger emits `validator_completed` event with `verdict=REJECT` AND
  `canonical_verdict="changes_required"` for `accessibility-validator`
  (engine-level; not checked by the executable runner).

Executable fixture: `golden/exec/design/scenario-03/`, graded by
`scripts/golden_exec.py`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for design
domain parity with dev)
