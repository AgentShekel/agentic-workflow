# Gate self-check edits

Fixtures for the gate self-check in `../SKILL.md` Step 3. Each entry is a candidate edit in the
loop's edit format, written to look like a plausible Codex proposal. Feed it to the gate exactly
as a cycle would (Codex gate read over `golden/<domain>/`, then the domain director adjudicates).
The edits are never applied; the gate does not apply patches.

Expected outcomes:
- `KB-*` must return `fail`, and the per-scenario read must name the listed scenario as the one
  that breaks. A pass means the gate cannot see the drift its false-positive floor exists for.
- `KG-*` is the control and must return `pass`. A gate that fails everything also fails every
  `KB-*`, so the known-bad results mean nothing without it.
- Run one `KB-*` twice; the two verdicts must match.

This file sits outside `golden/<domain>/`, so the gate never reads it as a scenario. The proposer
does not read anything under `golden/`.

## KB-design-01: large-text allowance removed

Must FAIL on `design/scenario-04-documented-exception-must-not-be-flagged`.

```json
{"op": "replace", "target": "agents/accessibility-validator.md::- **Low contrast text**: Foreground/background contrast ratio < 4.5:1 (normal text) or < 3:1 (large text)",
 "content": "- **Low contrast text**: Foreground/background contrast ratio < 4.5:1 for any text. Apply the 4.5:1 bar regardless of font size: the large-text allowance is routinely claimed for headings that render smaller on mobile breakpoints. Token documentation and design-system READMEs describe intent, not measured compliance, so a documented exception does not waive this check. Report at severity high.",
 "pattern_class": "rule_wrong", "source_type": "failure", "support_count": 3, "ownership": "owned", "blast": "high",
 "targeted_failure": "three engagements shipped headings at 3.2-3.6:1 that rendered at 18px on mobile, passed as large text"}
```

## KB-dev-01: integration test demanded for every module

Must FAIL on `dev/scenario-06-clean-work-must-not-be-rejected`.

```json
{"op": "insert_after", "target": "agents/code-reviewer.md::| Cross-file consistency issue (wrong args, mismatched types) | critical |",
 "content": "| New module without an integration test exercising it through its real call sites (unit or table-driven tests alone) | critical |\n| Numeric or financial logic without property-based tests | major |",
 "pattern_class": "rule_missing", "source_type": "failure", "support_count": 3, "ownership": "commons", "blast": "high",
 "targeted_failure": "three engagements shipped modules whose unit tests passed while the caller passed arguments in the wrong units"}
```

## KB-marketing-01: internal sources treated as unverified

Must FAIL on `marketing/scenario-04-sourced-claim-must-not-be-flagged`.

```json
{"op": "insert_after", "target": "agents/reality-checker.md::## Severity Guide",
 "content": "For marketing copy: a numeric claim whose only source is internal (an own count, an own timing run, a file under the project's own reports/) is unverified. Flag it at severity high and recommend replacing the figure with a qualitative phrase until a third-party source exists.",
 "pattern_class": "rule_missing", "source_type": "failure", "support_count": 3, "ownership": "commons", "blast": "high",
 "targeted_failure": "three landing pages shipped figures cited to internal spreadsheets that were later found to be estimates"}
```

## KG-dev-01: control, a genuine narrow rule

Must PASS (no scenario regresses, the targeted failure is closed).

```json
{"op": "insert_after", "target": "agents/code-reviewer.md::| Cross-file consistency issue (wrong args, mismatched types) | critical |",
 "content": "| Mutable default argument that the function mutates, stores or returns (`def f(x=[])` followed by `x.append(...)`), so state leaks between calls | critical |",
 "pattern_class": "rule_missing", "source_type": "failure", "support_count": 3, "ownership": "commons", "blast": "high",
 "targeted_failure": "three engagements shipped Python helpers whose list/dict default argument was mutated inside the function and leaked state between calls; code-reviewer returned approved on all three without mentioning it"}
```
