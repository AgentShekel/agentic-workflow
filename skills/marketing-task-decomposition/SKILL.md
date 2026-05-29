---
name: marketing-task-decomposition
domain: marketing
description: |
  [METHODOLOGY] Decompose a marketing engagement plan into atomic
  task files (engagement/tasks/*.md). Each task = one specialist + one
  deliverable + measurable done-when. Enables targeted re-dispatch on iter-2
  REJECT instead of re-running the whole phase.

  Pure reference — invoked by marketing-lead at Phase 2.5 (after plan.md,
  before dispatch). Mandatory for size: L. Recommended for size: M with ≥2
  specialists. Skipped on size: S (single specialist, single deliverable).
---

# Marketing task decomposition

Marketing engagements without atomic task files force the entire phase to
restart on REJECT. With atomic tasks, the lead re-dispatches only the broken
unit. This skill defines the contract.

## When to decompose

| size | Required? | Rationale |
|---|---|---|
| **S** | NO | One specialist, one deliverable — `plan.md` is enough. |
| **M** | RECOMMENDED if ≥2 specialists OR ≥3 distinct deliverables | iter-2 cost saving outweighs decomposition overhead. |
| **L** | YES | Multi-specialist coordination requires explicit dependency graph; full-engagement re-runs cost too much. |

If lead skips decomposition on a size: L engagement, director will REJECT
on `## Tasks` missing — same gate as missing `## Validation log`.

## Inputs

- `engagement/criteria.md` (locked)
- `engagement/plan.md` (lead, Phase 2 output)

## Output

- `engagement/tasks/{NN}-{slug}.md` — one file per atomic task
- `engagement/tasks/INDEX.md` — manifest with wave grouping (optional but recommended for L)

## Atomic task = one of these shapes

A task is "atomic" when it can be re-run in isolation without re-running
adjacent work. Marketing atoms by domain:

| Domain track | Atom shape | Example |
|---|---|---|
| **SEO** | one keyword cluster, OR one technical-audit slice (robots.txt, sitemap, schema, meta), OR one URL group's on-page recommendations | "task-03-cluster-pricing-keywords.md" |
| **PPC** | one ad group (1 audience + 1 message + 1 landing), OR one campaign-level config (bid strategy, exclusions, geo) | "task-05-adgroup-retargeting-cart-abandoners.md" |
| **Analytics** | one metric pull (date-bounded, source-bounded), OR one drift-analysis slice (one section/topic), OR one AI-visibility prompt batch | "task-02-metrika-traffic-mar-apr.md" |
| **Content** | one landing block (hero, features, FAQ, etc.), OR one ad creative variant, OR one email in a sequence, OR one banner format | "task-08-landing-block-trust-section.md" |
| **Banner design** | one art direction × one format (1500×500 social hero, 728×90 ad, etc.) | "task-12-banner-instagram-stories-direction-A.md" |

**Anti-atom (don't do this):**
- "task-01-do-seo-audit.md" — too coarse, can't be re-run partially.
- "task-02-write-copy.md" — what copy, for what surface?
- "task-03-pull-data.md" — what data, what dates, what source?

If you can't write a measurable acceptance bullet for the task, it's not atomic — split further.

## Task file template

```markdown
---
task: {NN}-{slug}                     # NN = 2-digit zero-padded order
engagement: {engagement-name}
domain: marketing
owner: {specialist-agent-name}        # marketing-seo-specialist, marketing-ppc-specialist, etc.
deliverable_type: {keyword-cluster | ad-group | landing-block | seo-audit-slice | metric-pull | drift-slice | ai-visibility-batch | banner-variant | email-step | content-piece}
depends_on: [{task-NN}, ...]          # empty list if no deps
wave: {N}                             # tasks with same wave can run in parallel
status: pending | in_progress | done | blocked
estimated_effort: XS | S | M          # XS = <30 min, S = ≤2h, M = ≤half day; L per task = split further
validators: [{validator-name}, ...]   # which validators run on this task's output (subset of plan.md)
crit_refs: [crit-{N}, ...]            # criteria.md bullets this task addresses
---

# Task {NN}: {one-line title}

## Goal
One sentence: what observable artefact will exist after this task is done.

## Inputs
- criteria.md crit-N: "{verbatim criterion text}"
- plan.md phase: {phase name}
- prerequisite outputs (if depends_on non-empty): {paths}

## Steps
1. {action}
2. {action}
3. {action}

Keep ≤ 5 steps. If you need more, the task is too big — split.

## Deliverable
- {artefact path or section} — e.g. `executor-reports/marketing-seo-specialist.md` § "Cluster: pricing", or `engagement/banners/instagram-stories/direction-A.png`

## Done when
- [ ] {testable bullet 1}
- [ ] {testable bullet 2}
- [ ] specialist signed off in their executor-report
- [ ] validator(s) listed above passed (if applicable)
```

## Workflow

### Phase 1: Draft tasks (lead)

1. Read `criteria.md` and `plan.md`.
2. For each phase in plan.md, list candidate atoms using the shape table above.
3. Group atoms by **dependency order** → assign wave numbers.
   - Wave 1: no deps (data pulls, audits)
   - Wave 2: depends on wave 1 (recommendations from audits, semantic core from data)
   - Wave 3: depends on wave 2 (creative based on recs, campaigns based on core)
4. Write one `tasks/{NN}-{slug}.md` per atom from the template above.
5. Write `tasks/INDEX.md` with the wave grouping if engagement is L (or if M with ≥5 tasks).

### Phase 2: Validate (lead, single pass)

Marketing tasks don't need the dev-style 3-iteration validation cycle (no
TDD anchors, no code paths). One pass is enough:

For each task file, lead self-checks:
- [ ] `crit_refs` actually cites a `criteria.md` bullet (not a phantom).
- [ ] `owner` is a real agent name (matches a `marketing-*` agent in `~/.claude/agents/`).
- [ ] `depends_on` cites real `tasks/NN-*.md` files.
- [ ] `## Done when` has at least one bullet testable without the lead's word ("CSV at path X exists with header Y", not "data looks complete").
- [ ] No two tasks have the same `(owner, deliverable_type)` in the same wave (would compete).

If any check fails — fix the file, don't dispatch.

### Phase 3: Dispatch (lead → mid-leads → specialists)

Pass tasks to mid-leads grouped by track:

- `marketing-traffic-lead` ← all tasks where `owner` is `marketing-seo-specialist | marketing-ppc-specialist | marketing-keyword-researcher`.
- `marketing-analytics-lead` ← `marketing-web-analyst | marketing-ai-visibility-specialist`.
- `marketing-content-lead` ← `marketing-copywriter | marketing-banner-designer`.

Each mid-lead receives the list of task file paths (not contents — paths only) and
dispatches specialists wave-by-wave.

Specialists open their assigned task file, do the work, and append their result to
`executor-reports/{specialist-agent-name}.md` § "Task {NN}: {title}".

When done, specialist updates the task file's `status: done` and is finished.
Mid-lead aggregates, top-lead consumes.

### Phase 4: Iter-2 retargeting (on REJECT)

When director rejects, read which `crit-N` bullets failed. Find tasks where
`crit_refs` includes those crit-N values. Re-dispatch ONLY those tasks (with
specialist appending `## Iteration 2` to their executor-report per protocol).

This is the payoff: instead of re-running the whole content phase to fix
one ad creative, you re-run one task.

## Anti-patterns

- **Don't decompose retroactively** ("we already did the work, let me write the tasks now"). Either decompose at Phase 2.5 or skip it entirely (size: S/M-without-multispecialist). Retroactive task files are paperwork, not coordination.
- **Don't write `tasks/*.md` content longer than 40 lines.** If the task needs more spec, the brief belongs in `executor-reports/{specialist}.md` after the specialist runs, not in the task file.
- **Don't put the same crit-N in `crit_refs` of >3 tasks.** If one criterion needs that many tasks, the criterion is a deliverable list — sharpen criteria.md (lead-authority, no user touch) and respread.
- **Don't make a task's `owner` a mid-lead.** Mid-leads coordinate; they don't deliver. Owner must be a specialist agent.
- **Don't skip `crit_refs` "because the task is implementation detail".** Every atom must trace to a criterion. If it doesn't trace — it's scope creep, drop it or escalate via scope-sync.

## What this is NOT

- Not a tech-spec (no `tech-spec.md` for marketing).
- Not a `task-creator` invocation (dev-only — has TDD anchors, code-touching). Lead writes these directly with Write tool.
- Not validated by `task-validator` or `reality-checker` agents (those are dev-only). Lead's Phase 2 self-check above is sufficient.

## Cost estimate

For an M engagement with 8 atomic tasks: ≈10-15 min of lead time to draft + self-validate. Saves an entire phase re-run on iter-2 (≈30-60 min). Net positive at iter ≥ 1.4 reject rate; current baseline is 0.5 (1 reject in 2 engagements average), so still net positive across 4+ engagements.
