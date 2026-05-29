# Scenario 03 — security-gap-rate-limit-missing

## Situation

A dev engagement (M-tier) adds a new authentication endpoint
`POST /api/v1/auth/refresh-token` returning a long-lived JWT. The engineer
wrote unit + integration tests; OpenAPI spec is updated; deploy config is
ready. No rate-limit middleware was applied to the new route (other auth
endpoints in the codebase wrap `@limiter.limit("5/minute")`). `security-auditor`
runs because the engagement touched auth code (`auth_or_data_touched`
predicate fires).

## Expected behavior (before-edit baseline)

- `security-auditor` JSON output has a finding with
  `category ∈ {"OWASP_API4", "rate_limit_missing", "auth"}` and
  `severity ∈ {critical, high}`.
- `canonical.verdict` resolves to `changes_required`.
- The finding cites the file path + route name verbatim
  (`/api/v1/auth/refresh-token`).
- Methodology field is non-empty (security-auditor is in
  `_NUMERICAL_VALIDATORS` — must carry methodology per validator_lg's
  canonical envelope contract).

## Failure mode it must catch

`rule_wrong` — security-auditor checks for SQL injection / XSS / weak
crypto but misses missing rate-limit on new auth routes. The OWASP API
Security Top 10 #4 (Unrestricted Resource Consumption) is the explicit
target. Engineer ships; the endpoint becomes vector for token-stuffing
brute-force.

## Pass criteria

- `security-auditor` finding count ≥ 1, severity ≥ high.
- Finding issue text contains "rate" OR "limit" OR "throttle" OR "OWASP API4".
- `canonical.findings[*].location` includes the route file path.
- `canonical.metrics` (numerical validator) has at least one numeric metric
  (vulnerability_count, OWASP_top10_coverage, etc.) — exists even if zero,
  proves methodology applied.
- Ledger `validator_completed` event for `security-auditor` carries
  `verdict=REJECT` and `output_schema_version=1.0`.

## Reference artefacts

(synthetic example — adapt or replace with a scenario drawn from your own engagement history)
