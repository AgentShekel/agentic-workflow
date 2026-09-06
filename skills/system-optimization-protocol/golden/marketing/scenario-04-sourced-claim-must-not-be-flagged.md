# Scenario 04 — sourced-claim-must-not-be-flagged

## Situation

A marketing engagement delivers a landing page for an analytics product. Three numeric claims
appear above the fold, each carried with its evidence:

1. "Индексация страниц ускорилась в 2.3 раза" — the copy deck cites
   `reports/webmaster-indexing-2026-07.csv` with the before/after crawl dates and the sample
   size (1 840 URLs), pulled from Yandex Webmaster, not from a customer anecdote.
2. "Более 400 проектов" — cited to an internal count with the query and the cut-off date in
   the same row of the claims table.
3. "Отчёты собираются за 15 минут вместо трёх часов" — cited to a timed run recorded in
   `reports/pipeline-timing-2026-07.md`, with both the manual and automated measurements.

The claims table in the deliverable maps every claim to its artefact path, the measurement
window, and the person who ran it. No claim is rounded up beyond its source, and no source is
older than the stated window.

## Expected behavior (before-edit baseline)

The validator pass returns `approved` / `approved_with_suggestions`. Any finding about the
claims is `info` at most (e.g. suggesting the sample size be shown inline for readers). The
engagement ships without a rework round spent re-sourcing already-sourced numbers.

## Failure mode it must catch

The marketing seed set rewards catching under-delivery (01), unsupported SEO claims (02) and
brand-voice violations (03). The drift that follows is a validator that treats **every**
number as unsupported until it personally re-derives it, and a critique agent that reads
confident phrasing as overclaiming.

The concrete misfires:

1. **Citation not read** — "2.3 раза" flagged as unsupported while the CSV path sits in the
   claims table one line below it.
2. **Standard-of-proof inflation** — demanding a third-party audit for an internal project
   count that is honestly labelled as an internal count.
3. **Tone read as claim** — "более 400" flagged as vague when the exact number and cut-off are
   in the table, i.e. the copy is rounded down for readability and the precision is one click
   away.
4. **Severity escalation** — rating any of the above `high` so the acceptor cannot ship, which
   converts a copy decision into a validator's decision.

The cost here is specific to the domain: a marketing corpus that cannot pass sourced claims
teaches the writer to strip numbers out of copy, and vague copy is the actual business loss.

## Pass criteria

- Every validator's `canonical.verdict` is `approved` or `approved_with_caveats`.
- Zero findings at `severity ∈ {critical, high}` against claims 1-3.
- Any finding raised against a claim must quote the cited artefact path and explain what is
  wrong WITH THAT ARTEFACT (stale window, wrong sample, arithmetic error) — a finding that does
  not reference the citation is a FAIL for this scenario.
- No finding demands removing a number that is correctly sourced, or replacing it with a
  hedge ("значительно", "существенно").
- The engagement reaches ACCEPT at iteration 1 on the claims axis.

## Reference artefacts

Synthetic, by construction. Domain mirror of
`golden/dev/scenario-06-clean-work-must-not-be-rejected.md` and
`golden/design/scenario-04-documented-exception-must-not-be-flagged.md`; the three form the
false-positive floor of the golden set and should be judged together whenever an edit touches
validator severity or evidence rules.
