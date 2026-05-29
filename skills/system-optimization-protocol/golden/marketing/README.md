# golden/marketing/ — SkillOpt golden scenarios for the marketing domain

Tricky scenarios used by `system-optimization-protocol` Step 3 ("Gate") to
verify that a proposed bounded edit does NOT regress on previously-passing
behavior. Each scenario file is a self-contained markdown brief that the
director uses to ask itself: "given this concrete situation, does the
candidate skill/agent edit still produce the right outcome?"

Format mirrors `golden/dev/README.md`. See that file for the canonical
scenario template (Situation / Expected behavior / Failure mode / Pass
criteria / Reference artefacts).

## Initial set (2026-05-28, populated for parity with dev)

| # | Slug | Class | What it guards |
|---|---|---|---|
| 01 | keyword-count-underdelivery | rule_ignored | criteria-trace / completeness-validator still flag when keyword-researcher returns less than the criterion-specified count |
| 02 | seo-claim-unsupported-by-data | rule_missing | seo-auditing / critique still require Yandex-source citations for factual claims in audit reports |
| 03 | brand-voice-pronoun-violation | rule_wrong | critique / brand-voice validator still flag pronoun mismatch (formal вы vs casual ты) against brand-research.md |

These three are the seed set, mapped to the three SkillOpt failure classes
(rule_ignored / rule_missing / rule_wrong). Population synced with dev:
all three domains now have ≥3 golden scenarios covering all three classes.

## Adding new scenarios

1. Write a markdown file matching the format in `golden/dev/README.md`.
2. Pick a unique NN (sequential).
3. Edit this README's table.
4. The director picks up new scenarios on next cycle — no registration
   step needed.

## Anti-patterns

- Don't write scenarios that test only ONE skill/agent in isolation —
  cross-component scenarios catch more (e.g., marketing-seo-specialist +
  critique + completeness-validator interacting).
- Don't write scenarios that mirror a single past engagement verbatim —
  generalize to a class.
- Don't write scenarios where the pass criteria are "agent says the
  right thing in prose" — make them observable in artefacts (validator
  output verdict, ledger event payload type, etc.).
