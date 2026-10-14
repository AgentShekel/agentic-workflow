# Scenario 02 — accessibility-aria-missing-modal

## Situation

A design engagement (M-tier, `ux_heavy: true`) ships a new modal dialog
component at `engagement/ui/components/modal.tsx`. The component:
- Has no `aria-labelledby` or `aria-describedby` attribute.
- Does not implement focus-trap (keyboard `Tab` escapes the modal into
  the page behind).
- Does not close on `Escape` key.

`accessibility-validator` runs as part of `validator_lg.py --auto`
validation set (mandatory for `ux_heavy ∈ {minor, true}` per
`validation-pipeline`). Screens for both light and dark themes are
captured in `engagement/screens/iter-1/{light,dark}/modal.png`.

## Expected behavior (before-edit baseline)

- `accessibility-validator` flags missing aria attributes with
  severity ≥ critical (WCAG 2.1 SC 4.1.2 Name/Role/Value).
- `accessibility-validator` flags missing focus-trap with
  severity ≥ critical (WCAG 2.1 SC 2.1.2 No Keyboard Trap inverted —
  user MUST be able to escape modal, AND focus MUST stay within when
  open).
- `accessibility-validator` flags missing Escape-to-close (WCAG 2.1
  SC 2.1.1 Keyboard).
- `canonical.verdict` resolves to `changes_required`.

## Failure mode it must catch

`rule_missing` — `accessibility-validator` agent body / `ui-ux-methodology`
checklist contains "aria-label" generic check but no explicit "modal
focus-trap" or "modal escape" check. Result: modal component ships
without keyboard accessibility; screen-reader users cannot identify the
dialog purpose; sighted keyboard users get trapped in the underlying
page. WCAG AA conformance silently broken on a critical interaction
surface.

## Pass criteria

- `accessibility-validator` JSON output has at least 2 findings, each
  with `severity ∈ {critical, high}`, covering ≥2 of these failure
  modes: missing aria-label/labelledby, missing focus-trap, missing
  Escape close.
- At least one finding's `category` includes "aria" OR "focus-trap" OR
  "keyboard" verbatim.
- The finding cites the artefact path (`engagement/ui/components/modal.tsx`)
  and the relevant WCAG SC identifier.
- `canonical.verdict` resolves to `changes_required` (not `approved`).
- Ledger emits `validator_completed` event with `verdict=REJECT` for
  `accessibility-validator`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for design
domain parity with dev)
