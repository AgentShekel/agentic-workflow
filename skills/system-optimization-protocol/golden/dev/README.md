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

## Initial set (initial dry-run seed)

| # | Slug | Class | What it guards |
|---|---|---|---|
| 01 | spec-code-drift-skeptic-catches | rule_ignored | skeptic + reality-checker still flag function-name mismatches between tech-spec and code |
| 02 | flaky-test-masking-detector-fires | rule_missing | anti-pattern-detector still catches `assert True` / skipped tests under wave dispatch |
| 03 | security-gap-rate-limit-missing | rule_wrong | security-auditor still flags new auth endpoint without rate-limit (OWASP API4) |

These three are the dry-run set — synthetic, exercised once on the cycle to
characterize failure modes before a real cycle runs against real signals.
Marker `dryrun: true` is set in their accompanying signals (in
`skill-evolution-log.md`) so the director's reflect step skips them when a
real cycle runs.

## Real-signal scenarios

| # | Slug | Class | What it guards |
|---|---|---|---|
| 04 | manager-catches-mis-rendered-consilium | rule_missing | acceptance-protocol manager diffs `consilium-summary.md` against raw `{role}-iter-N` JSON + ledger verdicts before adjudicating; a softened or unbacked adversary REJECT cannot become a false ACCEPT premise at the human gate |
| 05 | http-endpoint-accepted-on-unit-green | rule_wrong | exercised-verification trigger covers HTTP surfaces, not only `ux_heavy: true`; a `POST /…` endpoint deliverable cannot be ACCEPTED on green unit+integration alone with its real-HTTP test deferred as a "narrow residual" — caught at the validation-pipeline matrix + acceptance verdict layers |

Scenario 04 derived from the live dev `acceptance-protocol / rule_missing × 3`
cluster (×2 provenance gate + cross-repo paths; ×1 fidelity-diff).
NOT `dryrun` — guards a real cluster
that is DUE for a cycle; this scenario is its acceptance test + post-edit
regression floor.

Scenario 05 derived from the live dev verification-coverage cluster — the 3rd hit
of the "non-exercised proof accepted where real exercise is required" meta-class
inside ~48h. NOT `dryrun` — guards the HTTP-surface mechanism of that
meta-class; it is the acceptance test for the `validation-pipeline` +
`acceptance-protocol` (+ `dev-lead` plan-time) edit and the regression floor.

## False-positive floor (2026-08-20)

| # | Slug | Class | What it guards |
|---|---|---|---|
| 06 | clean-work-must-not-be-rejected | rule_wrong (inverted) | a genuinely clean deliverable still PASSES: no over-applied HTTP-exercise mandate on a non-HTTP module, no `validation incomplete` where the proof exists, no manufactured architecture objection rated above `info` |
| 07 | escalation-quality-both-directions | rule_missing | an unresolvable ambiguity IS escalated and a repo-resolvable one is NOT — graded as one pair; a partial pass is a fail |

Scenarios 01-05 all reward CATCHING a defect, so every accepted edit pushes the corpus
toward suspicion and nothing pushes back. 06 is the missing half: an edit that raises the
catch rate by failing 06 is a REJECT for the director, not a trade-off to argue in prose.
Run it with the domain mirrors `design/scenario-04` and `marketing/scenario-04` whenever an
edit touches validator severity or evidence rules.

07 adds the fourth eval class (capability / regression / session-length / **escalation**).
It grades both directions at once because a one-sided test rewards a degenerate agent: a
never-escalate agent passes the second half, an always-escalate agent passes the first.

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
