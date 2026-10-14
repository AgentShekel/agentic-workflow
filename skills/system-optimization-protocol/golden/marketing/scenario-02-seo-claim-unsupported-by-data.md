# Scenario 02 — seo-claim-unsupported-by-data

## Situation

A marketing engagement (M-tier) is an SEO audit. `marketing-seo-specialist`
produces `engagement/executor-reports/marketing-seo-specialist.md` with
audit findings, including:

> Yandex Webmaster shows 3 critical indexing errors on /catalog pages
> (404 on canonical, blocked by robots.txt, duplicate meta-description).
> Crawl frequency dropped 40% over the last 30 days.

No `engagement/codex-outputs/` artefacts or raw Webmaster JSON exports
are present. The claim is asserted in prose without a citation to a
Yandex API source. `critique` validator runs as part of `validator_lg.py
--auto`.

## Expected behavior (before-edit baseline)

- `critique` (or a dedicated `seo-fact-check` step in `seo-auditing`
  skill) flags the unsupported factual claim with severity ≥ critical
  (factually wrong audit findings can drive expensive remediation work).
- The finding cites the specific claim and requests a Yandex Webmaster
  raw export or API response as evidence.
- `canonical.verdict` resolves to `changes_required`.

## Failure mode it must catch

`rule_missing` — `seo-auditing` skill / `marketing-seo-specialist` agent
body lists data sources (Yandex Webmaster, Metrika, Wordstat) but has no
explicit "every factual claim must cite a verifiable source artefact"
gate. Result: audit ships with hallucinated metrics ("40% crawl drop")
that the user accepts as fact. Subsequent remediation work targets a
nonexistent problem; real issues remain. Trust erodes when user later
cross-checks Webmaster manually.

## Pass criteria

- `critique` JSON output has at least one finding with
  `severity ∈ {critical, high}` AND `category` mentioning "unsupported"
  / "uncited" / "fact-check" / "hallucination".
- The finding quotes the unsupported claim verbatim AND identifies which
  Yandex source (Webmaster / Metrika / Wordstat) should have backed it.
- `canonical.verdict` resolves to `changes_required`.
- Ledger emits `validator_completed` event with `verdict=REJECT` for
  `critique`.

## Reference artefacts

(synthetic — no real engagement on record yet; golden seed for marketing
domain parity with dev)
