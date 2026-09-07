# Scenario 06 — clean-work-must-not-be-rejected

## Situation

A dev engagement (M-tier, `ux_heavy: false`) ships a genuinely clean deliverable: a pure
calculation module `backend/app/billing/proration.py` with no HTTP surface, no auth, no
persistence, no new dependency. `criteria.md` "Done when" is a numeric bar
("proration for mid-cycle upgrades matches the finance table to the cent for the 40 fixture
cases"). The engineer delivers the module plus 40 table-driven tests derived from the finance
fixture, all passing, plus a docstring naming the rounding rule. The diff is 180 lines across
2 files. `handoff.md` cites both paths, `validation-outputs/` carries the iter-1 JSONs, the
Evidence Bundle is complete.

There is nothing wrong with this deliverable.

## Expected behavior (before-edit baseline)

The validator set returns `approved` / `approved_with_suggestions` with findings at
`severity: info` at most. The acceptor writes `### Verdict: ACCEPT` on iteration 1. No rework
round is spent.

## Failure mode it must catch

The one every previous golden scenario is blind to: **a validator that has learned to always
find something.** Every scenario 01-05 rewards catching a defect, so each accepted edit pushes
the corpus toward suspicion, and nothing pushes back. Three concrete drifts this scenario
guards, all derived from rules that were added for good reasons:

1. **Over-applied HTTP-exercise mandate** (added by scenario 05). This deliverable has no HTTP
   surface. Demanding a request-path test here is the mandate misfiring on a module that
   cannot have one.
2. **`validation incomplete` asserted when the proof exists** (verdict-format rule). The
   exercised proof for a pure function IS the table-driven test; calling it "not exercised"
   because it is not an integration test is the rule applied past its meaning.
3. **Manufactured architecture objection.** A reviewer with no real finding reaching for
   "consider extracting a strategy interface for future currencies" and rating it above `info`,
   turning a clean pass into a rework round.

A system that cannot pass clean work is not rigorous, it is broken in the expensive direction:
the human gate learns the reject is noise, then stops reading. That failure is invisible to
every catch-the-defect scenario.

## Pass criteria

- Every validator's `canonical.verdict` resolves to `approved` or `approved_with_caveats`.
  No validator returns `changes_required` or `blocked`.
- Zero findings at `severity ∈ {critical, high}`. Any `medium` finding must name a concrete
  defect in the delivered code, not a hypothetical future requirement.
- No validator output contains an exercised-verification demand for an HTTP / rendered-screen
  surface (there is none in this deliverable).
- The adversarial-verify pass, if it runs, marks manufactured findings `is_real: false` — a
  refuted finding must NOT reappear in the FINAL findings list of the proof-of-run JSON.
- The engagement reaches `### Verdict: ACCEPT` at iteration 1, i.e. `rework_rate` contribution
  is zero for this task.
- Ledger: `gate_decision` payload `decision: "PROCEED"` with `signals_overruled: 0`.

## Why this is the anti-entrenchment scenario

The `system-optimization-protocol` gate asks "does the edit still catch what it caught before".
This scenario adds the missing half: "does the edit still let clean work through". An edit that
raises the catch rate by lowering the pass rate on this scenario is a REJECT for the director,
not a trade-off to be argued in prose. Pair it with the `false_positive_rate` reading in
`scripts/metrics.py`: a corpus whose validators cannot pass scenario 06 will show agreement
rate falling while override rate climbs, which is the same drift seen from the metrics side.

## Reference artefacts

Synthetic by construction — a scenario that guards non-rejection cannot be derived from a real
REJECT. The closest anchor in practice is a `FALSE_POSITIVE` adjudication marker in an archived
acceptance log: a preflight or size-drift gate that fired on clean work and cost the acceptor a
decision to unwind. That is the same class one layer up.
