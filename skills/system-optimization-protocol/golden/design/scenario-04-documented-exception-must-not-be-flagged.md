# Scenario 04 — documented-exception-must-not-be-flagged

## Situation

A design engagement ships a marketing hero section. The brand system defines a
`--brand-accent-inverse` token that is documented in `design-system/tokens.json` with an
explicit note: it is a **large-text-only** pair, approved at 3.4:1 against the accent
background, which is compliant under WCAG AA for text at 24px/700 and above. The delivered
hero uses it exactly once, on a 40px display heading, and every body-copy pair in the same
screen uses the standard 4.9:1 token.

Separately, one CTA button deliberately uses a 2px offset outline instead of the system's
default shadow focus ring, because the button sits on a photographic background where the
shadow is invisible. The exception is written into `design-system/README.md` under "focus
ring on imagery" with the reasoning and the contrast measurement.

Nothing here violates the design system. Both deviations are the system's own documented
escape hatches, used as documented.

## Expected behavior (before-edit baseline)

`accessibility-validator` returns `approved` (or `approved_with_suggestions` carrying `info`
findings at most). `design-ui-designer` review does not demand a token change. The engagement
reaches ACCEPT without a rework round spent re-litigating a documented decision.

## Failure mode it must catch

The design domain's three seed scenarios all reward flagging: token drift (01), missing ARIA
(02), dark-mode contrast (03). Each accepted edit tightens the checkers, and nothing in the
gate pushes back, so the predictable drift is a validator that reports **any** ratio under
4.5:1 and **any** deviation from the default component spec as a violation, without reading
the token's own documentation.

The concrete misfires:

1. **Threshold applied without the size rule** — 3.4:1 flagged as an AA failure on a 40px
   heading, where the applicable bar is 3:1.
2. **Deviation read as drift** — a documented exception treated as an undocumented one because
   the validator checked the component against the default spec and never opened the README.
3. **Escalating severity to force a change** — rating either finding `high` so the acceptor
   cannot ship without addressing it, converting a design decision the brand already made into
   a validator's decision.

A design system with documented exceptions that the validators cannot honour is a design
system whose exceptions will be deleted, which is the real cost of this drift.

## Pass criteria

- `accessibility-validator` `canonical.verdict` is `approved` or `approved_with_caveats`;
  never `changes_required` or `blocked` for either the token pair or the focus ring.
- Zero findings at `severity ∈ {critical, high}`. Any finding referencing the 3.4:1 pair must
  state the applicable large-text threshold and resolve as compliant.
- If a validator raises the focus-ring deviation at all, its finding cites
  `design-system/README.md` and closes as a documented exception, at `severity: info`.
- No finding demands replacing `--brand-accent-inverse` with a different token.
- The engagement reaches ACCEPT at iteration 1 on these two points; any rework round spent
  here counts as a FAIL for the scenario.

## Reference artefacts

Synthetic, by construction — non-rejection scenarios cannot be derived from a real REJECT.
The class is the design mirror of `golden/dev/scenario-06-clean-work-must-not-be-rejected.md`;
run them together when judging an edit that touches any validator's severity rules.
