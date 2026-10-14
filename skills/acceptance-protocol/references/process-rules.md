# Process rules (iteration, scope sync, auto-promote, observability)

> Loaded from `acceptance-protocol` SKILL.md. Apply across tiers per each rule's stated scope.

**Contents:** Iteration loop · Scope sync (M/L only) · Auto-promote handling · Observability

## Iteration loop

The counter is informational. **Slot language is banned** — no "slot 1/2 used", "last attempt", "final round". That language pressures premature accepts.

### Triggers for escalation (root-cause based, not counter-based)

- **Repeating-critique trigger (highest priority):** if a blocking item from iteration N appears in iteration N+1 with the same root cause, escalate IMMEDIATELY. Loop detected — more rework will not fix it.
- **Pre-final-iteration trigger:** before starting the last allowed iteration (S=1, M=2, L=3), escalate to user with current blockers and ask whether to continue or revise scope.
- **Hard limits:**
  - S: 1 iteration. REJECT → human directive.
  - M: 2 iterations. After round 2, escalate.
  - L: 3 iterations. After round 3, escalate.
  - Auto-promoted engagements: budget +1 (so promoted-S becomes M with 3 max, etc.)

### Escalation message template (Russian, per global CLAUDE.md)

```
После {N} раундов правок не могу принять работу. Текущие блокеры:
- {blocking 1} — {root cause from adversary findings}
- {blocking 2} — {root cause}

Adversary findings location: engagement/consilium-summary.md
Validator outputs: engagement/validation-outputs/

Варианты: продолжить ещё круг / пересмотреть criteria / закрыть как unresolvable.
```

When loop signals "criteria are wrong, not the work" — route back to `agency-intake` for new/updated `criteria.md`, do not throw rework at lead.

## Scope sync (the only pre-execution interaction, M/L only)

On M and L tiers, once per engagement before lead starts Phase 2 planning, director MAY:
- Read `criteria.md`
- Ask lead ONE clarifying question about criterion interpretation
- Lock criteria by writing `engagement/scope-sync.md` with Q/A and director signature

### When scope sync is MANDATORY (not optional)

1. `criteria.md` has `ux_heavy: true` — director double-checks classification. If domain=dev and criteria mention only API/data, push back: "ux_heavy looks wrong, propose `false`?".
2. `criteria.md` has `ux_heavy: false` AND scope text mentions `screen|page|dashboard|landing|UI|интерфейс|экран|страница` — flag potential under-classification.
3. `criteria.md` "Done when" has fewer than 2 measurable bullets, OR any bullet is taste-vague ("clean", "professional") without objective bar — demand sharpening.
4. `tools_required` is empty for dev/design engagement (almost certainly missed) — ask lead to enumerate.

After scope sync, director does NOT interact with lead until handoff. No mid-execution consultation. **S-tier has no scope sync** — secretary intake is sufficient.

If criteria change mid-engagement (user request): new scope sync required, iteration counter resets.

## Auto-promote handling (tier shifts mid-engagement)

`size-detect.py --mode runtime` detects scope drift and may auto-promote S→M or M→L. **Promotion is one-way; demotion is forbidden.**

### Behaviour on promotion

1. `criteria.md` frontmatter rewritten (`size: S` → `size: M`)
2. `scope-sync.md` appended:
   ```markdown
   ## Auto-promote S → M @ {timestamp}
   Trigger metrics: {specialists, diff_files, ui_surfaces, deploy_involvement}
   New acceptance: M-tier (Opus adversary required)
   Iteration budget revised: +1 round expected for adversary findings
   ```
3. **Iteration budget bumped +1** on this engagement (M default 2 → 3; L default 3 → 4)
4. **Acceptance protocol switches to NEW tier retroactively** at handoff.

### Why retroactive (not next-iter)

Acceptance is the gate. Shipping work that's M-shaped through S-acceptance ships gaps. Adversary review on auto-promoted engagement may find more gaps than fresh M-tier work — that's correct behaviour, the work was produced under lighter mode.

### Detection points

- After every Phase heartbeat, lead invokes `size-detect.py --mode runtime`
- Pre-handoff, `handoff-precheck.py` includes `size-drift` check (M and L tier sets) → if observed > current, FAIL handoff with directive to auto-promote
- Lead must address gaps **before** handoff once promoted — don't accumulate to acceptance-time surprise

### Consequences

- S → M promotion: producer must run methodology validators (didn't on S), pass M's 11-check pre-check, expect adversary pass at acceptance
- M → L promotion: must produce `tasks/INDEX.md` (L requires task decomposition), expect full consilium at acceptance

## Observability

After each iteration, append one line to `~/.claude/projects/{project}/metrics.jsonl`:

```json
{"ts":"2026-05-09T15:30:00Z","engagement":"acme-landing","domain":"design","director":"design-director","tier":"M","iter":2,"verdict":"reject","blocking_count":3,"adversary_roles":["peer-opus"],"adversary_verdict":"rework_required","duration_s":180,"tokens_used":68421}
```

New required fields (tiered acceptance):
- `tier` — S | M | L (the tier at acceptance time, after any auto-promote)
- `adversary_roles` — list of roles that ran (empty on S)
- `adversary_verdict` — aggregate from consilium-summary.md (or "n/a" on S)

Read `metrics.jsonl` directly (one JSON per line) for retrospectives or to compute reject rate / iter distribution / adversary-overrule ratio by tier. A dedicated summarizer / dashboard is deferred until LangSmith integration lands (no live summarizer script today).
