# Scenario 03 — brand-voice-pronoun-violation

## Situation

A marketing engagement (M-tier) writes landing-page copy for a B2B
financial product. `engagement/brand-research.md` (produced by
`brand-context-researcher`) explicitly states:

> Voice axis: formal. Pronouns: «вы» (capitalized in addresses).
> Never use casual «ты». Tone: confident, expert, no exclamation marks.

`marketing-copywriter` produces
`engagement/executor-reports/marketing-copywriter.md` with landing copy
that includes:

> Узнай, как сэкономить на комиссиях! Открой счёт за 5 минут!

(casual «ты» imperative + exclamation marks — direct contradiction)

`critique` validator (or a brand-voice-validator if present) runs as
part of `validator_lg.py --auto`.

## Expected behavior (before-edit baseline)

- `critique` flags the voice violation with severity ≥ high, citing both
  the brand-research.md rule AND the verbatim violating phrase from the
  copy.
- Multiple finding instances if multiple violations (each violating
  sentence flagged separately).
- `canonical.verdict` resolves to `changes_required`.

## Failure mode it must catch

`rule_wrong` — `marketing-copywriter` agent body has anti-patterns list
covering generic issues (overpromising, jargon, weak CTAs) but no
explicit rule binding to `brand-research.md` voice axis enforcement.
`critique` validator likewise checks copy quality in isolation, not
against the brand-research source-of-truth. Result: copy ships
contradicting brand voice; user receives complaints from internal brand
guardian; engagement re-opens 2 weeks post-ACCEPT for a "voice pass"
that should have been caught at validation.

## Pass criteria

- `critique` JSON output has at least one finding with
  `severity ∈ {critical, high}` AND `category` mentioning "brand-voice"
  / "pronoun" / "voice-violation" / "tone-mismatch".
- The finding cites BOTH the rule from `brand-research.md` (verbatim or
  by quoted phrase) AND the violating phrase from the copy (verbatim).
- `canonical.verdict` resolves to `changes_required`.
- Ledger emits `validator_completed` event with `verdict=REJECT` AND
  `canonical_verdict="changes_required"` for `critique`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for marketing
domain parity with dev)
