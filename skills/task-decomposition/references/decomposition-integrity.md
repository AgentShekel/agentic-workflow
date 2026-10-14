# decomposition-integrity

Shared rules for turning an approved document (tech-spec, plan, `criteria.md`) into a set of
atomic task files. Loaded by `task-decomposition`, `design-task-decomposition`,
`marketing-task-decomposition`. Domain-neutral on purpose: the three decomposition skills own
the task shapes and wave rules, this file owns what must survive the conversion.

## 1. Decomposition is a lossy migration, not a summary

Every transformation of a document loses meaning. Treat the task set as a risky migration of
intent, not as a compression of the spec.

Tasks are execution handles that keep pointing back at the source. They are not a second source
of truth. When a task's wording and the source document disagree, **the source wins**, unless the
task explicitly records an approved change to the source.

- Do not replace spec wording with a tidier task summary when exact contract names, field names,
  numbers or thresholds matter. Copy them verbatim.
- Do not turn a spec into a coverage matrix and then treat the matrix as more authoritative than
  the spec.
- If a conversion step needs interpretation beyond the source, create a discovery task or record
  an open question. Do not invent the missing scope silently.

## 2. Every task carries its source and the common objective

Two fields are mandatory in every task file (they are in the template):

- **Source** — path plus section of the document the task is derived from.
- **Common objective** — one or two sentences naming the goal of the whole work.

The reason is the wave model: a specialist dispatched into wave 2 sees its own task and nothing
else. Without the objective repeated in the task, it cannot tell whether its slice is a means or
an end, and it optimises the slice against the wrong target. Repetition across tasks is the
intended cost.

## 3. Preserve the failure mode, not just the instruction

When a requirement exists because of a risk, the risk goes into the task. Say what must not
happen, not only what to build.

- Prefer: "replace the relation so the stored document never loses its old link even if session
  creation fails".
- Avoid: "replace the relation".

Per task type: migration tasks carry the no-regression invariant; reliability tasks carry the
failure being prevented; test tasks carry the regression the test must catch; review and QA tasks
carry the drift or contract mismatch being hunted. This is what the `## Non-goals / must not
break` section is for, and it is why leaving it empty without writing "нет" is a defect.

## 4. Constrain the outcome, leave the route free

A task should fix the source to follow, the final invariant, the hard requirements and non-goals,
and the proof required to close it. It should leave the implementation details, local structure
and test shape to the owner, unless the source itself demands exact steps.

Good wording says: make this outcome true and prove it. A brittle step-by-step checklist is only
correct when the source prescribes those steps.

## 5. Atomicity, and the one exception

Default: one task = one owner = one deliverable that can be verified without bundling unrelated
runtime paths, surfaces, migrations or test families.

The exception is **same-shape batching**. When the plan produces several small independent edits
of the same kind (the same one-line change, the same constant, the same field added across
files), do not create one task per file and burn one specialist seat each. Compose ONE task that
lists every file and its change, give it one owner, and let it be reviewed as one diff. Reserve
one-task-per-item for work that needs its own judgement, its own tests, or its own review
surface.

Batching is about identical shape, not about adjacency. Two edits in the same file that need
different reasoning are two tasks.

## 6. Coverage check before declaring the set complete

Every unique requirement in the source must appear in at least one of: task scope, acceptance
criteria, non-goals, or an explicit blocker/follow-up task. If a requirement maps to none of
these, the set is incomplete regardless of how many tasks it has.

Check before handing the set over:

- Every phase or section of the source has at least one task.
- Every "must" and "must not" appears in acceptance criteria or in non-goals.
- Every edge case appears in implementation, test, or review work.
- Every artefact and doc update has a task.
- Every out-of-scope item is named explicitly rather than dropped.
- Every known blocker is represented.
- Every task names its source and repeats the common objective.
- No task asks for push or deploy unless the user asked for it.
- Sampled tasks are actually atomic; if a sample is an umbrella, split that whole class.
- The task count matches the real size of the source. A large spec compressed into a handful of
  tasks is a defect, not brevity.

Last check: has the set become more bureaucratic than useful? A task that exists only to satisfy
process, and protects neither meaning, sequencing, proof nor execution clarity, gets merged or
deleted.

## 7. Anti-patterns

- One vague "QA" task, or one vague "write tests" task.
- Umbrella wording: "доделать остальной бэкенд", "покрыть тестами всё", "финальный QA по всему
  объёму", "остальное".
- Dropping non-goals because they are not implementation work.
- Replacing exact contract names from the source with a paraphrase.
- Leaving typecheck, build or lint to an unnamed future step.
- A task set that can be fully closed while a known blocker is still open.
- Turning "100% покрытие" into a line-coverage claim nobody measured.
- Recording a large scope in the plan while creating a medium-sized task set.
- Over-constraining implementation when the source only requires an outcome and its proof.
