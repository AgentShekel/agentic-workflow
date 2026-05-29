# golden/dev/ — SkillOpt golden scenarios for the dev domain

Tricky scenarios used by `system-optimization-protocol` Step 3 ("Gate") to
verify that a proposed bounded edit does NOT regress on previously-passing
behavior. Each scenario file is a self-contained markdown brief that the
director uses to ask itself: "given this concrete situation, does the
candidate skill/agent edit still produce the right outcome?"

**Format per scenario** — one `.md` file each, name `scenario-NN-{slug}.md`:

```
# Scenario {NN} — {slug}

## Situation
{2-4 sentences describing the engagement state, what artefacts exist,
what the agent/skill is being asked to do.}

## Expected behavior (before-edit baseline)
{What the system did under the current rules. This is the regression
floor — must still happen after the edit.}

## Failure mode it must catch
{What kind of failure would slip through if the rule were missing /
wrong / ignored. This is the SkillOpt "rule class" the scenario exists
to guard.}

## Pass criteria (3-5 bullets)
- {Concrete, observable signals that the edited skill/agent still does
  the right thing in this situation.}

## Reference artefacts (optional)
{Paths to real engagements / acceptance-log / validator outputs that
inspired the scenario, if any.}
```

## Example scenarios (synthetic — adapt or replace)

| # | Slug | Class | What it guards |
|---|---|---|---|
| 01 | spec-code-drift-skeptic-catches | rule_ignored | skeptic + reality-checker still flag function-name mismatches between tech-spec and code |
| 02 | flaky-test-masking-detector-fires | rule_missing | anti-pattern-detector still catches `assert True` / skipped tests under wave dispatch |
| 03 | security-gap-rate-limit-missing | rule_wrong | security-auditor still flags new auth endpoint without rate-limit (OWASP API4) |

These three scenarios are **synthetic starter examples** illustrating the
format. They cover the three SkillOpt failure classes (rule_ignored /
rule_missing / rule_wrong) against agents/skills that ship in the public
repo. They are **not your golden set** — they are templates. Replace or
extend them with scenarios drawn from your own engagement history. A
real SkillOpt cycle skips any scenario whose accompanying signal in
`skill-evolution-log.md` carries the marker `dryrun: true`, so synthetic
examples never drive real edits.

## Adding new scenarios

1. Write a markdown file matching the format above.
2. Pick a unique NN (sequential).
3. Edit this README's table.
4. The director picks up new scenarios on next cycle — no registration
   step needed.

## Anti-patterns

- Don't write scenarios that test only ONE skill/agent in isolation —
  cross-component scenarios catch more (e.g., skeptic + reality-checker
  + tech-spec-validator interacting).
- Don't write scenarios that mirror a single past engagement verbatim —
  generalize to a class.
- Don't write scenarios where the pass criteria are "agent says the
  right thing in prose" — make them observable in artefacts (validator
  output verdict, ledger event payload type, etc.).
