# UX-heavy engagements — full rules

Loaded by `engagement-protocol` when `criteria.md` frontmatter has
`ux_heavy ∈ {minor, true}`. Hot-path summary lives in
`engagement-protocol/SKILL.md §"UX-heavy engagements"` — it points here
for the full rule set, trace schema, and lead-side gates.

`ux_heavy` is a 3-level gradient, not boolean — small UI tweaks should not pay full L-engagement overhead:

| Value | When | Mandatory artefacts |
|---|---|---|
| `false` | Backend, brand voice, SEO, copy without UI surface, infra | none |
| `minor` | CSS tweak, copy edit on existing surface, padding/color/font change, single-state visual fix | ONE screen per touched surface, single theme; NO traces required |
| `true` | New UI surface, new interactive flow, behaviour-changing UI, multi-screen design | Screens both themes + traces with structured `verdict` field per flow |

Set by secretary at intake based on signals (visual hierarchy / layout / typography / color / spacing / words of taste / mockup references). Lead can promote during execution (`false` → `minor` → `true`) with `scope-sync.md` entry; never demote.

## `ux_heavy: minor` — relaxed rules

For a small CSS-class adjustment or copy tweak, full screens-light+dark + traces is overkill and pushes leads toward corner-cutting. `minor` keeps the visible-state guarantee without overhead:

- ONE screenshot per touched surface in `engagement/screens/{iteration}/{theme}/{surface}.png`. Single theme acceptable (whichever was visually changed); both themes only if both were modified.
- `traces/` is **optional** — required only if the change has interactive behaviour (rare for CSS).
- `handoff.md` §6 Exercised is required but each bullet may reference just a screen, no trace.
- `ux-review` validator runs in lightweight mode (skips trace verification).

## `ux_heavy: true` — full rules

1. `engagement/screens/{iteration}/{theme}/` MUST contain Playwright captures of every touched UI surface, BOTH light and dark themes (if dark mode exists in the project).
2. `engagement/traces/{iteration}/{flow}.json` MUST contain structured exercised-flow records (schema below) for every exercised flow listed in handoff §6.
3. `handoff.md` §6 "Exercised" is mandatory and must reference real paths in `screens/` and `traces/`.
4. `ux-review` validator MUST be in lead's validation-log before handoff (mandatory per `acceptance-protocol`'s validator selection on `ux_heavy: true`). On L-tier, director MAY request a single re-run of `ux-review` on screens + traces if adversary findings identify a coverage gap (per `acceptance-protocol §"When you MAY request specific validator re-run"`).
5. Docker / Playwright unavailability is a blocker, never a deferral. Lead escalates to user once ("start Docker Desktop"), then proceeds. `screens/` cannot be left for the user to capture.

If `ux_heavy: true` and any of (1)–(3) absent on submission → handoff is INCOMPLETE (returned unread, doesn't burn iteration budget).

## Trace JSON schema (mandatory structured fields)

Free-form trace dumps let the lead write "result was correct" without comparing claim to reality. Forcing structure makes the lead compare numerically before submission:

```json
{
  "flow": "quarter-preset-click",
  "iteration": 2,
  "captured_at": "2026-04-24T14:32:11Z",
  "steps": [
    {
      "action": "click",
      "selector": "[data-test=preset-quarter]",
      "expected": "period.endDate - period.startDate >= 80 days (rolling 90-day window)",
      "observed": {
        "period.startDate": "2026-04-01",
        "period.endDate": "2026-04-24",
        "diff_days": 24
      },
      "verdict": "FAIL",
      "notes": "Math.floor(month/3) returns calendar quarter start, degrades to 1-3 days at month boundaries"
    }
  ],
  "network": [{"url": "...", "status": 200, "request_body": "...", "response_body": "..."}],
  "console": [{"level": "warn", "message": "..."}],
  "dom_snapshot": "engagement/traces/iter-2/quarter-preset.html"
}
```

Required fields per step:
- `action` — what user did (click / type / select / navigate).
- `selector` — DOM selector or trace anchor.
- `expected` — what SHOULD happen, written from criteria.md or user-spec language. Plain English allowed but must be falsifiable.
- `observed` — what actually happened, structured as object with concrete values.
- `verdict` — `"PASS"` or `"FAIL"`. Lead computes this themselves.

Lead-side gate: if any step has `"verdict": "FAIL"`, the lead does NOT submit handoff with this trace as evidence. Either fix the underlying behaviour, or surface as a known-issue deferral with explicit out-of-scope justification in §11. Submitting with FAIL verdicts attached = REJECT `submitted FAIL trace as evidence`.

Director-side gate: ux-review validator and director both look at `verdict` field. Missing `verdict` field → REJECT `unstructured trace cannot be verified`. Free-form prose traces that don't parse as JSON → REJECT.
