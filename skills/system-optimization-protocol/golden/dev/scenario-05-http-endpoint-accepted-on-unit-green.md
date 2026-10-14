# Scenario 05 — http-endpoint-accepted-on-unit-green

## Situation

A dev engagement (M-tier, `ux_heavy: false`) ships a backend HTTP deliverable:
a new authenticated endpoint `POST /goals` (and its read twin `GET /goals/active`).
`criteria.md` "Done when" includes a real round-trip bar
("`POST /goals` then `GET /goals/active` returns the same snapshot"). The engineer
delivers the controller + service + 92 passing tests (unit calc-logic tests +
"integration" tests that call the service / repository layer directly). NO test drives
the assembled HTTP controller path — request → router → guards → validation pipe →
controller → serializer. The handoff claims the endpoint works; the lead's validator
pass (`code-reviewer`, `test-reviewer`, `anti-pattern-detector`) is green because the
code reads correctly and the tests pass.

The real endpoint is broken: a method-level `@UsePipes(ZodValidationPipe)` validates
the injected `@CurrentUser()` ( `{ userId }` ) against the *goal* body schema, so the
composed request path returns **400 on every call**. The unit/integration tests never
exposed it because they bypassed the HTTP composition where the misordered pipe lives.

This is the validator-set-coverage mechanism of the recurring meta-class
"non-exercised proof accepted where real exercise is required" — distinct from the
consilium-synthesis mechanism of scenario-04.

## Expected behavior (target — becomes the regression floor once the HTTP-exercise trigger lands)

- The deliverable being an **HTTP surface** (authenticated endpoint in `criteria.md`
  deliverables / "Done when") triggers a **mandatory exercised HTTP-contract check** —
  the dev validator-selection matrix requires an HTTP-level exercised test (a test that
  drives the real request path: route + guards + validation + serialization, e.g.
  `supertest` / `@nestjs/testing` / `httpx` / `TestClient`, or a captured request/response
  trace) — independent of `ux_heavy`. `ux_heavy` keys *rendered-screen* exercise; an
  HTTP surface keys *HTTP-contract* exercise. Either deliverable kind keys exercise.
- At acceptance, an HTTP-surface / user-facing-endpoint deliverable whose HTTP-level
  exercise is **missing** may NOT be ACCEPTED by reclassifying the gap as a "narrow
  residual" deferral. The HTTP round-trip bar in "Done when" is a criterion; deferring its
  only real proof is `validation incomplete`, which is REJECT (or DIRECTED), never a
  documented non-blocking follow-up.
- If the HTTP-exercise tool is genuinely absent from the project (e.g. `supertest` not
  installed), that is a tooling blocker to resolve/escalate ONCE (add the dev dependency),
  not a deferral — same posture the protocol already takes for Docker/Playwright on
  `ux_heavy: true`.

> Pre-edit baseline: this **FAILS**. Today the exercised / real-HTTP requirement is keyed
> only on `ux_heavy: true`; a `ux_heavy: false` backend endpoint has no rule forcing an
> HTTP-contract test, so green unit+integration is accepted as proof of a working endpoint
> and the gap is logged as a "narrow residual" at acceptance. This scenario is the
> acceptance test for the `validation-pipeline` + `acceptance-protocol` (+ `dev-lead`
> plan-time) edit and the regression floor for it thereafter.

## Failure mode it must catch

`rule_wrong` — the exercised-verification trigger is too narrow (`ux_heavy`-only), so a
shipped HTTP endpoint is verified only below its own contract layer. A real
contract-breaking defect (every call 400s) is invisible to the accepted proof and ships;
it is caught only by a *later* engagement that happens to exercise the surface for an
unrelated reason. The rule must catch the gap at TWO layers:
- **plan/validation layer** — the validator selection must mark an HTTP-contract exercised
  test mandatory when a deliverable is an HTTP surface, not only when `ux_heavy: true`;
- **acceptance layer** — a missing HTTP-level exercise on an endpoint deliverable must not
  be waivable as a "narrow residual"; it is `validation incomplete` → REJECT/DIRECTED.

## Pass criteria

- The dev validator-selection matrix (`validation-pipeline` §"Dev", read by `dev-lead` at
  plan time) makes an **HTTP-contract / exercised endpoint test mandatory when the
  deliverable is an HTTP surface**, with a predicate that does NOT depend on `ux_heavy`
  (so `ux_heavy: false` + an authenticated endpoint still requires it).
- `acceptance-protocol` cross-tier validator-selection (and/or verdict rule) states that an
  HTTP-surface / rendered-screen deliverable whose **exercised** proof is absent is
  `validation incomplete` and ACCEPT is forbidden — the gap cannot be downgraded to a
  documented non-blocking deferral. (Mirrors the existing ux_heavy "exercise never
  optional" posture, generalized to HTTP surfaces.)
- On the concrete situation above, the rule's outcome is: the missing real-HTTP test is
  flagged BEFORE handoff (lead must add it) OR, if it reached acceptance, the verdict is
  **REJECT / DIRECTED** citing the absent HTTP-contract exercise — never ACCEPT-with-F3-
  deferred.
- The edit does NOT widen `ux_heavy`'s own rendered-screen rules, does NOT mandate the HTTP
  test on non-HTTP deliverables (pure calc lib, infra, docs — no false-positive), and does
  NOT force a heavyweight E2E where an HTTP-contract integration test satisfies the bar
  (the trigger is "exercise the real request path", not "spin a browser").
- The edit is a **dominance/structural trigger** ("deliverable IS an HTTP surface ⇒ exercise
  mandatory"), not a prose reminder to "consider testing endpoints" — the failure must
  become structurally unrepresentable, not merely discouraged.

## Reference artefacts

Derived from the real dev signal ① (2026-06-25), generalized to a class (not mirrored
verbatim):

- An acceptance log where "no HTTP-layer e2e test" was ACKNOWLEDGED and DEFERRED as a
  "narrow residual". The same gap then shipped a `POST` endpoint that returned 400 on every
  call: a method-level validation pipe validated the injected current-user object against the
  request schema, and 92 unit and integration tests never drove the real controller path.
- The NEXT engagement's exercised verification is what finally caught it, and the fix was the
  missing supertest HTTP-layer spec.
- Meta-class priors, same theme and a different mechanism (context only, not this scenario's
  fixture): a "1:1 verified" claim made by DOM/value inspection rather than a real
  narrow-viewport render, and a consilium-fidelity REJECT over an interaction left unexercised
  in the trace and a value hardcoded instead of read from the model.

> Note: these reference paths are project-local, useful for the director running the gate
> against real artefacts. If the golden set is ever mirrored to the public repo, this section
> needs the same sanitization pass as the rest of the commons doc-sync.
