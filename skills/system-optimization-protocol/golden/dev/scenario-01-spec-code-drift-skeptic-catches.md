# Scenario 01 — spec-code-drift-skeptic-catches

## Situation

A dev engagement (M-tier) submits `engagement/specs/tech-spec.md` claiming
function `parseCommand(raw: str) -> dict` exists in `src/cli/parser.py`.
The actual code has `parse_cli_command(raw_text: str)` — names differ but
the function exists for the same intent. The engineer wrote tasks that
reference the spec's name. `reality-checker` runs as part of `validator_lg.py
--auto` validation; `skeptic` also runs because the tech-spec touches an
implementation contract.

## Expected behavior (before-edit baseline)

- `skeptic` flags spec↔code name mismatch with severity ≥ high in its JSON
  output `findings` array. `canonical.verdict` resolves to `changes_required`.
- `reality-checker` flags the same drift independently — its §A "Reality"
  finding cites the missing `parseCommand` symbol in `src/cli/parser.py`.
- Both findings reach `validation-outputs/` and feed into
  `consilium-summary.md` synthesis.

## Failure mode it must catch

`rule_ignored` — either validator agent silently accepts the spec because
the function "looks close enough" / contains a substring match. Result:
the engineer implements against the spec's name, code review passes
("tests green"), but the integration call site in another wave is broken
since it expects `parseCommand`. Drift is discovered post-deploy.

## Pass criteria

- `skeptic` validator output has at least one finding with
  `severity ∈ {critical, high}` AND `category` mentioning "drift" / "spec"
  / "mismatch".
- `reality-checker` validator output has at least one finding with
  `severity ∈ {critical, high, medium}` AND issue text referencing the
  missing symbol name verbatim.
- `canonical.verdict` from BOTH validators resolves to one of
  `changes_required` / `suspicious` (not `approved` / `approved_with_caveats`).
- Ledger emits `validator_completed` events with `verdict=REJECT` for at
  least one of {skeptic, reality-checker}.

## Reference artefacts

(synthetic example — adapt or replace with a scenario drawn from your own engagement history)
