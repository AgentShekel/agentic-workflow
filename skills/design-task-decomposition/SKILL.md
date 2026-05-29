---
name: design-task-decomposition
domain: design
description: |
  [METHODOLOGY] Decompose a design engagement plan into atomic
  task files (engagement/tasks/*.md). Each task = one specialist + one
  deliverable + measurable done-when. Enables targeted re-dispatch on iter-2
  REJECT instead of re-running the whole brand/UI phase.

  Pure reference — invoked by design-lead at Phase 2.5 (after plan.md,
  before dispatch). Mandatory for size: L. Recommended for size: M with ≥2
  specialists. Skipped on size: S (single deliverable).
---

# Design task decomposition

Design engagements without atomic task files force the entire brand or UI
phase to restart on REJECT. With atomic tasks, the lead re-dispatches only
the broken unit (one logo direction, one component spec, one screen variant).

## When to decompose

| size | Required? | Rationale |
|---|---|---|
| **S** | NO | Single artefact (one logo refresh, one icon set tweak) — `plan.md` is enough. |
| **M** | RECOMMENDED if ≥2 specialists OR brand+UI mixed | iter-2 cost saving outweighs decomposition overhead. |
| **L** | YES | Full rebrand + product UI + design system requires explicit dependency graph and token-propagation tracking. |

If lead skips decomposition on a size: L engagement, director will REJECT
on `## Tasks` missing — same gate as missing `## Validation log`.

## Inputs

- `engagement/criteria.md` (locked)
- `engagement/plan.md` (lead, Phase 2 output)

## Output

- `engagement/tasks/{NN}-{slug}.md` — one file per atomic task
- `engagement/tasks/INDEX.md` — manifest with wave grouping (mandatory for L)

## Atomic task = one of these shapes

A design task is "atomic" when its rework wouldn't cascade into adjacent tasks
in the same wave. Design atoms by track:

| Track | Atom shape | Example |
|---|---|---|
| **Brand voice** | one voice axis (formal/playful, terse/expansive) with example copy in 3 contexts | "task-01-voice-axis-formality.md" |
| **Logo** | one direction (mark + wordmark + clearspace), produced as alt 1/2/3 | "task-02-logo-direction-A.md" |
| **CIP / corporate identity** | one surface (business card, letterhead, email signature, social avatar, presentation cover) | "task-04-cip-business-card.md" |
| **Color palette** | one role (primary/secondary/accent/semantic) with full ramp + WCAG contrast pairs | "task-06-palette-primary-ramp.md" |
| **Typography** | one pairing (display + body + mono) with full size scale | "task-07-type-pair-A.md" |
| **Design tokens** | one group (color OR spacing OR radius OR elevation OR motion) | "task-08-tokens-spacing.md" |
| **Component spec** | one component (button, input, card, modal, nav, etc.) — all states + responsive | "task-10-component-button.md" |
| **Screen / page** | one screen variant (theme × breakpoint) | "task-12-screen-dashboard-dark-desktop.md" |
| **UX flow** | one flow (signup, checkout, onboarding step, settings change) | "task-14-flow-signup.md" |
| **Asset pack** | one asset family (icons set, illustrations set, social photos batch) | "task-16-icons-32px-stroke.md" |
| **Presentation slide** | one slide (title, problem, solution, etc.) | "task-18-slide-pricing.md" |

**Anti-atom (don't do this):**
- "task-01-design-the-landing.md" — span; can't re-run partially.
- "task-02-create-design-system.md" — too big; tokens vs components vs screens are different atoms.
- "task-03-make-it-look-good.md" — vibes; not measurable.

If you can't write a measurable acceptance bullet for the task, it's not atomic — split further.

## Sequence dependency (CRITICAL for design)

Design has hard sequence rules from `design-lead` skill:

1. Brand (voice, palette, type) → design tokens → components → screens → flows → assets.
2. Token tasks MUST land before component tasks (component depends on token).
3. Component tasks MUST land before screen tasks (screen consumes component).
4. Brand identity tasks (logo, CIP) are independent of token/component chain — separate dependency tree.

Encode this in `depends_on`. Director enforces order: a screen task with
`depends_on: []` is REJECTed because tokens must precede.

## Task file template

```markdown
---
task: {NN}-{slug}                     # NN = 2-digit zero-padded order
engagement: {engagement-name}
domain: design
owner: {specialist-agent-name}        # design-brand-strategist, design-visual-designer, design-ui-designer, design-ux-designer, design-presentation-designer
deliverable_type: {voice-axis | logo-direction | cip-surface | palette-role | type-pairing | token-group | component-spec | screen-variant | ux-flow | asset-pack | slide}
depends_on: [{task-NN}, ...]          # honour brand→tokens→components→screens chain
wave: {N}                             # tasks with same wave can run in parallel
status: pending | in_progress | done | blocked
estimated_effort: XS | S | M          # XS = <30 min, S = ≤2h, M = ≤half day; L per task = split further
validators: [{validator-name}, ...]   # critique, accessibility-validator, design-review, ux-review
crit_refs: [crit-{N}, ...]            # criteria.md bullets this task addresses
theme: light | dark | both            # for screen / component tasks
breakpoint: mobile | tablet | desktop | all  # for screen / component tasks
---

# Task {NN}: {one-line title}

## Goal
One sentence: what observable artefact will exist after this task is done.

## Inputs
- criteria.md crit-N: "{verbatim criterion text}"
- plan.md phase: {phase name}
- prerequisite outputs (if depends_on non-empty): {paths to brand/, design-system/, ui/}

## Steps
1. {action}
2. {action}
3. {action}

Keep ≤ 5 steps. If you need more, the task is too big — split.

## Deliverable
- {artefact path} — e.g. `engagement/design-system/tokens/spacing.json`, `engagement/ui/dashboard-dark-desktop.png`, `engagement/brand/logo/direction-A.svg`

## Done when
- [ ] {testable bullet — e.g. "all 8 spacing values in tokens/spacing.json non-empty"}
- [ ] {validator-specific — e.g. "accessibility-validator passes contrast on each colour pair"}
- [ ] specialist signed off in their executor-report
- [ ] (if ux_heavy) screen captured to `screens/{iter}/{theme}/{surface}.png`
```

## Workflow

### Phase 1: Draft tasks (lead)

1. Read `criteria.md` and `plan.md`.
2. Map each plan.md phase to atom families using the shape table.
3. Apply sequence rules: brand → tokens → components → screens → flows → assets.
4. Assign wave numbers respecting `depends_on`:
   - Wave 1: brand atoms (voice, palette, type) + independent assets (logo direction A/B/C in parallel)
   - Wave 2: design-token atoms (consume palette + type from wave 1)
   - Wave 3: component atoms (consume tokens)
   - Wave 4: screen atoms (consume components)
   - Wave 5: flow atoms (consume screens)
5. Write one `tasks/{NN}-{slug}.md` per atom from the template above.
6. Write `tasks/INDEX.md` with the wave grouping (mandatory for L, recommended for M with ≥6 tasks).

### Phase 2: Validate (lead, single pass)

Design tasks don't need a 3-iteration validation cycle. One self-check pass:

For each task file:
- [ ] `crit_refs` actually cites a `criteria.md` bullet.
- [ ] `owner` is a real agent name (matches `design-*` agent in `~/.claude/agents/`).
- [ ] `depends_on` honours sequence rule (component task depends on a token task; screen depends on component).
- [ ] `## Done when` has at least one bullet measurable WITHOUT the lead's eye ("token JSON has 8 spacing values", "WCAG contrast ≥ 4.5:1 on every text/bg pair", not "feels right").
- [ ] For UI tasks: `theme` field present (light / dark / both).
- [ ] No two tasks deliver to the same path (would overwrite).

If any check fails — fix the file, don't dispatch.

### Phase 3: Dispatch (lead → mid-leads → specialists)

Pass tasks grouped by track:

- `design-brand-lead` ← `design-brand-strategist`, `design-visual-designer` tasks (voice, logo, CIP, assets).
- `design-product-design-lead` ← `design-ux-designer`, `design-ui-designer`, `design-presentation-designer` tasks (tokens, components, screens, flows, slides).

Each mid-lead receives the list of task file paths and dispatches specialists wave-by-wave.

Specialists open their assigned task file, do the work, append result to
`executor-reports/{specialist-agent-name}.md` § "Task {NN}: {title}", and update
the task file's `status: done`.

### Phase 4: Iter-2 retargeting (on REJECT)

When director rejects, read blocking items. Find tasks where:
- `crit_refs` includes the failing crit-N, OR
- `deliverable_type` matches the rejected artefact (e.g. director says "screen X has wrong button radius" → re-run the screen task AND the button component task if token drifted).

Re-dispatch only those tasks. Specialist appends `## Iteration 2` to their executor-report (per `engagement-protocol` §4-iter).

## Token propagation safety

Design's biggest iter-2 trap: a token changes (wave 2), but components (wave 3) and screens (wave 4) don't get re-rendered. Lead's Phase 4 must check:

- If a wave-2 token task is re-run on iter-2, every wave-3 component task that consumed that token MUST also re-run, and every wave-4 screen using those components MUST re-render.
- This is automatic IF `depends_on` is wired correctly. Manual audit: trace the dependency graph from the changed token and queue everything downstream.

`tasks/INDEX.md` should make this graph explicit so it's not lost on iter-2.

## Anti-patterns

- **Don't decompose retroactively.** Either at Phase 2.5 or skip (size: S).
- **Don't write `tasks/*.md` content longer than 50 lines.** Spec details belong in `executor-reports/{specialist}.md`.
- **Don't violate sequence.** A screen task with no token dependency = REJECT.
- **Don't put the same `crit-N` in `crit_refs` of >5 tasks.** If a criterion needs that many tasks, sharpen criteria.md (lead-authority, no user touch).
- **Don't make a task's `owner` a mid-lead.** Owners are specialists.
- **Don't skip `theme` field on UI tasks.** Light-only and both-themes have different acceptance bars; ambiguity here causes iter-2 "we forgot dark mode".
- **Don't number tasks before verifying dependencies.** A non-monotonic `depends_on` (task 05 depends on task 12) hides bugs — re-number after dependency lock.

## What this is NOT

- Not a `task-creator` invocation (dev-only).
- Not validated by dev validators (`task-validator`, `reality-checker`). Lead's Phase 2 self-check is sufficient. Critique/accessibility/ux-review run on the *delivered artefacts*, not on the task files.
- Not a Figma file index — task files describe what to produce, not where the live source is. Live source paths go in the executor report after delivery.

## Cost estimate

For an L engagement with 18 atomic tasks (rebrand + product UI): ≈30-45 min of lead time to draft + self-validate + INDEX.md. Saves ≥2 hours on a single iter-2 reject of token drift (which would otherwise re-run components + screens + accessibility audit). Net positive at any reject rate above ~0.2 — current design baseline is 0.6.
