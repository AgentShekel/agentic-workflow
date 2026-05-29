# golden/design/ — SkillOpt golden scenarios for the design domain

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
| 01 | design-token-drift-ui-validator | rule_ignored | design-ui-designer / critique still flag hardcoded hex colors when design-system-researcher reported existing tokens |
| 02 | accessibility-aria-missing-modal | rule_missing | accessibility-validator still flags missing focus-trap / aria-label on modal dialogs |
| 03 | dark-mode-contrast-fail | rule_wrong | accessibility-validator color-contrast check still triggers on dark-mode pairs (not light-mode only) |

These three are the seed set, mapped to the three SkillOpt failure classes
(rule_ignored / rule_missing / rule_wrong). Population synced with dev:
both domains now have ≥3 golden scenarios covering all three classes.

## Adding new scenarios

1. Write a markdown file matching the format in `golden/dev/README.md`.
2. Pick a unique NN (sequential).
3. Edit this README's table.
4. The director picks up new scenarios on next cycle — no registration
   step needed.

## Anti-patterns

- Don't write scenarios that test only ONE skill/agent in isolation —
  cross-component scenarios catch more (e.g., design-ui-designer +
  accessibility-validator + critique interacting).
- Don't write scenarios that mirror a single past engagement verbatim —
  generalize to a class.
- Don't write scenarios where the pass criteria are "agent says the
  right thing in prose" — make them observable in artefacts (validator
  output verdict, ledger event payload type, etc.).
