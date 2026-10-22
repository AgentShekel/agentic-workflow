---
name: task-decomposition
domain: dev
description: |
  [METHODOLOGY] Approved tech-spec → atomic engagement tasks. SDD phase 3:
  dev-lead applies it in the `{name}-impl` engagement when it maps the
  tech-spec's Implementation Tasks onto the plan. Preloaded by dev-lead and
  dev-tech-architect.
---

# Task Decomposition

Turn the approved tech-spec's Implementation Tasks into the `{name}-impl` engagement's plan tasks
without losing intent.

**Input:** `engagement/specs/tech-spec.md` (status: approved) + `engagement/specs/user-spec.md`
**Output:** `plan.tasks` / `plan.waves` returned by `dev-lead`; the engine's decompose phase writes
`engagement/tasks/*.md` and `tasks/INDEX.md` from them.

**Where this runs.** Inside `engagement-workflow`, at the `lead:plan` step of the impl engagement.
Nobody here can reach the user, and nobody spawns subagents: the older multi-agent flow
(`task-creator` fan-out, `task-validator` + `reality-checker` batches, user approval of the task
set) belonged to the retired `work/{feature}/` pipeline and does not run inside an engagement.
The checks it performed now happen at three engine seams: your self-check below, the per-task
review (and the co-signed contract when `A.contracts` is on), and the validate phase.

## Integrity rules (read first)

Decomposition is a lossy migration of intent, not a summary. The rules that keep meaning intact
across the conversion live in one shared file:
[decomposition-integrity.md](references/decomposition-integrity.md).

Load it before mapping. Non-negotiable subset: every task names its **Source** and repeats
the **Common objective**; the source wins on any conflict with task wording; requirements that
exist because of a risk carry that risk into `## Non-goals / must not break`; small same-shape
edits batch into ONE task instead of one seat each; the coverage check in §6 runs before the set
is handed over.

## Step 1: Gate on approval

Read `engagement/specs/tech-spec.md`. Frontmatter must say `status: approved` with a non-null
`approved_by`. If it does not, return a plan with zero delivery tasks and put
`SDD gate: tech-spec not approved` in `notes`: the impl engagement does not start on a draft.

## Step 2: Map tasks one to one

For each Implementation Task in the code waves (everything before Audit Wave and Final Wave):

| tech-spec field | plan task field |
|---|---|
| `Task N: {Name}` | `id` = `T{N}`, `title` = `{Name} [tech-spec Task N]` |
| Owner | `owner` |
| Files to modify | `files` (repo-relative, unchanged) |
| Covers (`AC-N`, `TC-N`) | `crit_refs` = the `crit-N` ids of the impl `criteria.md` Done-when bullets that cite those AC/TC ids (bullets read `- crit-3 (AC-2): …`) |
| Depends on | `depends_on` |
| Wave | the task's position in `plan.waves` |
| Description, Verify-smoke, Verify-user, Files to read | not copied: the plan schema has no per-task field for them. The `[tech-spec Task N]` marker in the title and the impl `criteria.md` Scope line send the specialist and the reviewer to that task in `specs/tech-spec.md` |

Rules:
- **One to one, unless a recorded drift says otherwise.** Do not merge, split or drop tech-spec
  tasks on your own judgement. The only deviations are the cases below, and each one is written
  as `SDD drift` so the manager adjudicates it. A task that cannot run as written
  (overlapping files in one wave, a missing owner, a file that does not exist) is a spec defect:
  record it in `notes` and `scope-sync.md` as `SDD drift: {task} — {what}` and plan the nearest
  executable shape. The manager adjudicates drift at acceptance. A path marked `(new)` is
  expected not to exist yet; drop the marker in `files`.
- **Batching (drift).** §5 of the integrity reference still applies: if the tech-spec gave
  several same-shape one-line edits a seat each, batch them and record the batch as drift.
- **No new work (drift).** A task that covers no AC/TC and is not infrastructure another task
  depends on does not enter the plan; record the dropped task as drift.

## Step 3: Map Audit Wave and Final Wave onto the validate phase

| tech-spec declaration | engagement plan |
|---|---|
| Code Audit | `code-reviewer` in `plan.validators` |
| Security Audit | `security-auditor` in `plan.validators` |
| Test Audit | `test-reviewer` in `plan.validators` |
| QA (pre-deploy) | `pre-deploy-qa` in `plan.validators` |
| Deploy | a `dev-devops-engineer` task in the last delivery wave |
| Post-deploy verification | `post-deploy-qa` in `plan.validators` |

Always add `completeness-validator` (traceability user-spec ↔ tech-spec ↔ code) and
`anti-pattern-detector`.

## Step 4: Coverage and cross-task self-check

Before returning the plan:
1. **Coverage (§6 of the integrity reference).** Every `AC-N` and every `TC-N` reaches at least
   one plan task through `crit_refs`, or, for a TC the tech-spec assigns to an Audit/Final
   declaration, the matching validator in `plan.validators`. An uncovered id is a hole, not a
   judgement call.
2. **Disjoint files per wave.** No two same-wave tasks share a file.
3. **Shared resources.** Each heavy resource in tech-spec Architecture → Shared resources has one
   owning task; its consumers depend on that task.

## Per-task contract (S2 — when A.contracts is enabled)

On M/L engagements run with `A.contracts` on, each `tasks/{id}.md` ALSO carries a `## Contract (co-signed)` section (the per-task acceptance rubric). You do NOT author it — leave it for the engine's contract handshake (owner proposes assertions in-band → reviewer co-signs and writes the section). Schema: `engagement-protocol` §"`tasks/{id}.md` → `## Contract (co-signed)`". It binds the per-task review only and never waives `criteria.md`.

## Final Check

- [ ] tech-spec approved (`status: approved`, `approved_by` set) before any task was planned
- [ ] Every code task mapped one to one; every deviation recorded as `SDD drift`
- [ ] Audit/Final waves mapped onto `plan.validators` (+ deploy task if declared)
- [ ] Every `AC-N` / `TC-N` covered; same-wave files disjoint
