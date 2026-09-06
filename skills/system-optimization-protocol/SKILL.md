---
name: system-optimization-protocol
domain: meta
triggers:
  - "loaded by every *-director agent via skills frontmatter"
  - "≥3 same-class signals accumulated in skill-evolution-log.md"
  - "monthly reflection sweep over engagement-reflections.md (Layer 3)"
  - "user explicitly invokes skill-evolution cycle"
  - "drafting / judging bounded edits to skills or agents"
description: |
  [PROTOCOL] Generic system-optimization (skill-evolution) methodology shared by the
  three domain director-optimizers (dev / design / marketing). The SkillOpt loop adapted
  to a creative/dev agency: event-driven reflect → bounded edit → gate → slow-update over
  the agent/skill corpus, with a cross-family proposer and judge-only directors. Reference-
  only — loaded by `*-director` agents via skills frontmatter, not triggered by keywords.
---

# System-optimization protocol (skill-evolution loop)

This is the optimizer side of the agency. It does NOT accept engagements (managers do that).
It improves the **skill/agent corpus itself**, treating it as a trainable artefact —
the adaptation of Microsoft SkillOpt's "train the procedure, not the weights" to a
low-volume, subjective-output agency with no automatic scorer.

## Mental model (SkillOpt mapping)

| SkillOpt | Here |
|---|---|
| Skill document = trainable state | The domain's `~/.claude/agents/*.md` + `~/.claude/skills/*/SKILL.md` |
| `current_skill` vs `best_skill.md` | `~/.claude/` (working) vs `C:\releases\agentic-workflow\` (blessed mirror) |
| Rollout (forward) | A real engagement in this domain |
| Loss / evaluator | Validator JSON + adversary consilium + **manager** acceptance verdict |
| Failure-trajectory analysis | Channels A/B — log signals + gap reflections (corrective) |
| Success-trajectory analysis | **Channel C** — `- worked:` reflections (reinforcement). Never a trigger |
| Reflect (backward) | This loop, step 1 — attribute failures to a skill/agent |
| Edit patch (gradient) | `append` / `insert_after` / `replace` / `delete` op on a skill/agent file |
| Learning rate / clipping | `edit_budget` — max edits accepted per cycle, after a stated ranking |
| Validation gate | Golden-scenario **rubric judgment** (Codex reads pass/fail, director adjudicates; `skill-testing` harness only for executable high-blast checks) |
| `round<r>__before.md` snapshot | Pre-edit file copies under `skillopt-snapshots/<ts>/` — the restore point |
| Momentum (anti-forgetting) | Slow-update: golden-set before/after, 4-bucket categorisation, **rollback on regressed>0** |
| Meta-learning | Two-level meta (shared process + domain content), written each cycle and read by the next |
| Optimizer ≠ target | **Codex proposes edits (cross-family); director judges. Never the same brain.** |

## Role boundary (judge-only — non-negotiable)

The director-optimizer is a **pure judge**, exactly like the manager is for engagements.
It authored neither the skills nor the proposed edits, so it carries zero defend-bias.

| Action | Who |
|---|---|
| Run engagements / accept deliverables | manager (NOT here) |
| Detect a recurring failure pattern | director-optimizer |
| **Author** edit patches to skills/agents | **Codex** (via `codex-bridge`) — never the director |
| Judge a proposed patch (accept/reject) | director-optimizer |
| Run the gate (golden-set) | director-optimizer (dispatches `skill-testing`) |
| Promote `~/.claude` → releases mirror | director stages a **draft MR** (branch + reasoning + gate evidence); **human merges** = ship (owned = audit-merge; commons = human decides content) |
| Decide a commons-protocol edit | **human** (commons maintainer) — director only proposes |

If the director ever writes an edit itself, defend-bias returns and the gate loses its
independence. Codex authors; the director judges Codex's proposal against gate evidence
and the rejection buffer.

## Trigger (event-driven, pattern-batched — NOT per-engagement)

This loop is expensive and out-of-band. It does NOT run after every engagement.
Fire only when ONE of:

- A manager wrote **REJECT** and tagged the cause as systemic (a skill gap, not a one-off
  producer slip) → it appends a signal to `skill-evolution-log.md`.
- An engagement needed **>1 rework round** in this domain.
- `anti-pattern-detector` fired on a wave in this domain.
- **≥3 engagements** in this domain show the *same* failure class accumulated in the log.
- **Reflection sweep pathway:** the `engagement/engagement-reflections.md` files
  (last 30–60 days, this domain) are clustered by **`target × class`**; a cycle fires
  on **cluster size ≥3** OR (once event ledger lands) Langfuse trend Δ thresholds:
  reject-rate ↑ ≥20%, validator FP-rate ↑ ≥30%, P95 latency ≥2× baseline. This
  pathway catches slow-burn patterns sub-threshold per-engagement but supra-threshold
  pooled — Reflexion-style per-engagement signal feeding the SkillOpt event-driven gate.
  **`skillopt-ready.py` now harvests this channel automatically** (Channel B): it scans
  the reflection files, drops any reflection with a log twin (same engagement+taxonomy —
  the log is authoritative and carries resolution) and any `resolved:`/`dryrun:` ones,
  clusters the remaining *orphans* by `(domain, target, class)`, and surfaces a due
  cluster through the same SessionStart reminder as Channel A. The director's manual
  pass is now the deeper review over what the checker surfaces, not the only harvest.

Optimise on a **common pattern across the batch**, never a single trajectory (single
failures are noise; patching them overfits). This is SkillOpt's
"identify COMMON failure patterns — not individual edge cases".

**Channel C (success) is fuel, not a trigger.** `- worked:` bullets in
`engagement-reflections.md` record a behaviour that CARRIED an engagement; two on one
`(target, class)` make it available as reinforcement. They never open a cycle. A cycle
authors a bounded edit against a defect, so firing one because things went well leaves the
proposer with nothing to close — and `skillopt-ready.py` keeps `ready` computed from A/B
alone for that reason. What the channel changes is what a cycle that some failure already
earned is allowed to do: without it, every edit this loop has ever authored made the corpus
more suspicious and nothing ratcheted back. The gate's false-positive floor is the brake on
that drift; this is the counterweight at the source.

## The loop

### 1. Reflect (Codex authors, taxonomy-classified)

**Dry-run signals are skipped.** Before reading signals, filter
`skill-evolution-log.md` entries with the line `dryrun: true` — those are
synthetic exercises (seed) and must not drive real edits. A real
cycle reflect step considers only signals without that marker.

**Resolved signals are skipped.** Signals closed by a direct fix outside a
cycle carry a `resolved: <date> — <how>` line. Exclude them from cluster
counting (the ≥3-same-class trigger) and from edit authoring — the gap is
already closed. Like `dryrun:`, the marker is load-bearing: a fixed signal
left unmarked would inflate a future cluster and trigger a redundant cycle.

Director dispatches **Codex via `codex-bridge`** with: the accumulated signals,
`acceptance-log.md`, `consilium-summary.md`, `validation-outputs/`. Codex classifies each
recurring finding and attributes it to a specific `agents/X.md` or `skills/Y/SKILL.md`:

- **`rule_missing`** — the skill was silent on this → propose `append` / `insert_after`.
- **`rule_wrong`** — an existing rule misled → propose `replace`.
- **`rule_ignored`** — the rule was correct but the agent didn't follow it → do NOT add text;
  propose a **structural** fix (raise it, make it a gate, tighten emphasis). Adding more
  text to an ignored rule just grows the file without changing behaviour.
- Plus the domain's own failure types (see the per-domain director file).

**Cross-check the target before authoring (finding F2).** A signal's `Traced to` (and a
reflection's `target`) names a best-guess file; it is load-bearing but fallible — a wrong trace
yields a right-pattern / wrong-file edit that the gate then rejects (pure waste, the most common
dry-run failure). Codex MUST verify the target points at the agent/skill whose CONTENT enforces
the catch — the validator/rule that would PRODUCE the catching artefact — not the producer of the
buggy output, by cross-reading the relevant golden scenario's pass-criteria before emitting a patch.

Codex output = a JSON patch list (see edit format). Director reads the shared process-meta
+ its domain content-meta BEFORE judging, and the rejection buffer (step 2).

**The reinforcement channel runs beside this one**, on the same call shape and the same
proposer, when Channel C carried fuel. It is deliberately the conservative half: propose only
patterns the target file does not already state, prefer tightening an existing section over a
new heading, and return an empty list when the corpus already says it. A reinforcement edit
that adds length without changing behaviour is this channel's characteristic failure.

**Both channels pass the optimizer meta-memory to Codex.** `skill-evolution-meta.md` is what
the last cycle learned about EDITING in this domain; a cycle that does not read it repeats a
mistake already paid for.

### 2. Select (merge failure-first, rank, then cut = learning rate)

- **Read `skill-rejected-edits.md` first.** If Codex re-proposes a previously-reverted
  edit, drop it (or demand it explain what changed). The buffer is negative memory — it
  exists so cycles don't re-litigate settled rejections.
- **Merge the two channels failure-first.** Where a corrective and a reinforcement edit
  touch the same region or make the same point, the corrective one wins; the reinforcement
  one survives only on ground no corrective edit covers. Two edits must never target the
  same text region.
- **Rank before cutting**, on stated criteria, in this order: systematic impact (how much of
  the batch backs it — `support_count`), complementarity (fills a gap rather than duplicating),
  generality (a principle beats a case), actionability (concrete and checkable). A budget cut
  with no stated criteria is a cut nobody can audit later.
- Cap accepted patches at `edit_budget` per cycle (start **L = 4–6**). Bigger early in a
  large overhaul, smaller as it converges (the cosine instinct).

### 3. Gate (golden-set, blast-radius tiered)

Before any edit reaches the blessed mirror it must pass the **golden-scenario gate** — a
rubric judgment over the relevant scenarios (Codex proposes a pass/fail read, the director
adjudicates; the `skill-testing` harness is optional, reserved for high-blast edits whose
scenarios are executable). The gate runs as a judgment with NO patch applied:
the director reasons whether the edit satisfies each scenario's pass-criteria without
regressing. Tier the gate by **blast radius** (anti-overhead):

| Blast radius | Examples | Pre-check (before promote) | Post-check (after promote) |
|---|---|---|---|
| High | a lead, a manager, a director, a shared protocol, a widely-loaded skill | **Mandatory** golden-set gate | slow-update |
| Low | one specialist, a typo, a narrow methodology skill | Optional (skipped unless `forceGate`) | slow-update |

**The tier scales rigour, never coverage.** Skipping the low-blast pre-check is the intended
anti-overhead trade. Skipping its post-check as well was not: an edit could then be applied to
the corpus and staged for the mirror without a single scenario ever being read against it, which
is the cheap way a specialist acquires an always-flag-X rule and the corpus ratchets toward
suspicion. Slow-update therefore covers **every** owned promotion, and flags the ungated ones so
they get read against the false-positive floor at least once. It costs one agent call over the
whole golden set per cycle, not one per edit, so the cheap tier stays cheap. This is only safe
because a post-hoc failure can now be undone: the step-4 snapshot is what makes it a check rather
than a note.

Pass = no regression on the golden set AND the channel's second test. No auto-scorer
exists, so the gate verdict is rubric-judged: **Codex proposes a pass/fail read, the
director adjudicates** (mirror of adversary → supreme-judge). FAIL → the edit goes to
`skill-rejected-edits.md` with what broke.

- **Corrective edit** (`source_type: failure`): the targeted failure is closed.
- **Reinforcement edit** (`source_type: success`): there is no failure to close, so the
  second test is *neutral-or-better on every scenario* AND *it says something the target
  file does not already say*. Judging a success edit by "did it close the failure" would
  fail every one of them for a reason that does not apply.

**False-positive floor (mandatory).** Every gate run also judges the domain's
non-rejection scenario — `dev/scenario-06`, `design/scenario-04`, `marketing/scenario-04` —
plus `dev/scenario-07` when the edit touches escalation, dispatch or task-contract rules.

Rationale: scenarios 01-05 all reward CATCHING a defect, so every accepted edit ratchets the
corpus toward suspicion and nothing ratchets back. A validator that has learned to always find
something is not rigorous, it is broken in the expensive direction: the human gate learns that
rejects are noise and stops reading them. No catch-the-defect scenario can detect that.

Adjudication rule: **an edit that closes the targeted failure but fails the false-positive
floor is a REJECT, not a trade-off to argue in prose.** Record it in `skill-rejected-edits.md`
naming the floor scenario it broke.

### 4. Promote (snapshot → apply → diff guard → draft-MR seam)

**Snapshot first.** Before any edit is applied, copy every target file to
`skillopt-snapshots/<ts>/`. This is the restore point step 5 rolls back to. File copies, not
a `git reset`: `~/.claude` is a git repo but is routinely dirty, so a hard reset would take
unrelated in-flight work with it. The same step records which files were ALREADY modified,
which is what makes the diff guard below precise.

**Diff guard after applying.** Every step in this loop declares its targets, and every step
is an LLM that could touch a neighbouring file while it is in there. The gate judges the edit
that was *proposed*; the guard checks what actually *landed*: newly-touched files (post-apply
dirty minus the pre-apply baseline) must all be declared targets or known side-effect paths
(the log, the buffer, the meta file, the snapshot and promotion dirs). A violation means the
cycle wrote outside the premise the gate judged under, so it rolls back and stages no MR.

A gate-passed edit is applied to the live `~/.claude` working corpus, then the mirror side is
staged as a **draft MR** for the human to review and merge — never a silent copy onto the
mirror's `main`:

- **Domain-owned files** (gate-passed): the director opens a promotion branch on the blessed
  mirror (`C:\releases\agentic-workflow\`, `skillopt/<domain>-<ts>`), applies the SAME change
  there as a surgical delta (preserve the file's line-endings; edit in place rather than
  copying the whole file over), and writes an **MR body** (reasoning + the batch pattern closed
  + per-edit gate evidence + slow-update buckets + a Codex-authored/director-judged line) as the
  review artefact. It does NOT merge and does NOT `git push`. The human reviews `git diff main..<branch>`
  + the MR body and merges = the publish/ship decision; owned MRs are gate-blessed, so the merge
  is an audit + ship gate.
- **Commons files** (see governance): the director cannot self-promote — it escalates the SAME
  reviewable artefact as a **proposal** (the exact edit + gate verdict + a one-line ask); the
  human decides the content, optionally pulling the other directors for cross-impact.

This is the SkillOpt equivalent of "the loop opens a draft PR with its reasoning attached; the
human owns the merge" — it fits the no-auto-push / review-before-merge rule and turns a silent
working-tree copy into a reviewable diff.

### 5. Slow-update (anti-forgetting; every owned promotion)

Re-run the golden set on the **pre-cycle** and **post-cycle** state. Categorise each
scenario (SkillOpt buckets):

- **regressed** (was-good → now-bad) — HIGHEST PRIORITY; blocks the cycle.
- **persistent_fail** (bad → bad) — escalate; the edit didn't help.
- **improved** (bad → good) — the win; record it.
- **stable_success** (good → good) — ignore; spend no attention here.

This is exactly what `anti-pattern-detector` did manually after the big refactor — now
systematic, on the golden set.

**`regressed > 0` rolls the cycle back for real.** Restore the offending targets from the
step-4 snapshot, append a `Status: RETRACTED` entry to `skill-rejected-edits.md` naming the
scenario that regressed, and stage no MR. A block that leaves the regressing edit on disk is
worse than no block at all: the buckets read as though something was enforced.

### 6. Record (close what the cycle actually closed)

A cycle that writes nothing back to `skill-evolution-log.md` cannot learn between runs — the
cluster it just closed stays live and the readiness checker re-fires it next session.

- **Promoted edits** → append `resolved: <date> — skillopt cycle <ts>. <which edit, what gate
  evidence>` under each signal a promoted edit genuinely addresses. Close ONLY those: a signal
  in the same cluster that no edit touched stays open. Silently closing a live gap is the more
  expensive mistake.
- **Mixed traces** (a skill half plus a script/engine half) → `resolved (SKILL half):`, never a
  bare `resolved:`. The two checkers read half-markers in opposite directions on purpose:
  `skillopt-ready` closes on `resolved:` and on `resolved (SKILL half):` only; `harness-ready`
  closes on `resolved:` and on its own `resolved (SCRIPT half):` / `resolved (ENGINE …):`, and
  explicitly not on the SKILL one. Whichever loop fixed its half is the only one that stops
  counting. Get the marker wrong and it inverts silently: the other loop drops a still-open
  half out of its cluster while this one re-fires a closed signal every session.
- **Null cycle** (Codex proposed nothing, or select dropped everything) → append
  `adjudicated: <date> | skillopt cycle <ts> | no-edit. <why> <what would reopen it>`.
  Deliberately not `resolved:` — nothing was fixed, the signal stays live and keeps counting,
  so one new occurrence re-fires the cluster immediately. Without this line a null cycle is
  byte-identical on disk to never having run, and a trigger that is always on stops being read.
- **Rolled back** → write nothing. The signals stay open.

### 7. Meta (two-level — see Zazor-2 split)

Written at the end of every cycle and read by the reflect and select steps of the next one.
It records how to EDIT better, never target-facing rules — those belong in the corpus and go
through the gate.

- **Shared process lessons** (`skill-evolution-meta.md`, all 3 directors read+write):
  lessons about *how to optimise* that hold across domains, e.g. "after demoting a
  validator to a cheaper model, recheck reasoning-heavy ones". Apply when ambiguous; do
  NOT force a past lesson if the current evidence clearly contradicts it (anti-overfit).
- **Domain content lessons** (the domain section of the same file): edit heuristics
  specific to this domain's skills.
- Judge the previous lessons against what this cycle did before adding new ones, and delete
  what misled. The file is not append-only, and the ~150-line cap is load-bearing: an
  unbounded meta file stops being read, which costs more than any lesson in it.

## Edit format (patches, like SkillOpt)

```json
{
  "reasoning": "why these edits close the batch's common pattern",
  "edits": [
    {"op": "append",       "target": "skills/X/SKILL.md", "content": "..."},
    {"op": "insert_after", "target": "skills/X/SKILL.md::<exact heading>", "content": "..."},
    {"op": "replace",      "target": "agents/Y.md::<exact text>", "content": "..."},
    {"op": "delete",       "target": "agents/Y.md::<exact text>"}
  ]
}
```

At most `edit_budget` edits. Empty list is a valid output (nothing warranted).

## Rejection buffer (`skill-evolution-meta.md` is meta; this is separate)

`<your-memory>/skill-rejected-edits.md`, append-only.
MUST be read before proposing edits. Schema:

```markdown
## <edit summary> | target: <file> | domain: <dev|design|marketing|commons> | YYYY-MM-DD
Tried: <what was proposed>
Reverted because: <what broke / which gate failed / which scenario regressed>
Status: WITHDRAWN | RETRACTED | GATE-FAIL
```

## Commons governance (the cross-cutting layer)

~80% of a domain's files are domain-owned (full authority here). ~20% are **commons**:
`engagement-protocol`, `validation-pipeline`, `acceptance-protocol`,
`system-optimization-protocol`, `docs-pipeline`, `agency-intake`, `codex-bridge`,
cross-domain validators (`product-context-validator`, `anti-pattern-detector`), and the
manager/director agent definitions.

- A director may **propose** a commons edit (when its domain's failure traces to a shared
  file) but **cannot self-promote** it. It escalates to the **human commons-maintainer**.
- The human serialises commons edits (no concurrent self-promote → no race), with
  cross-domain awareness, optionally pulling the other directors for cross-impact review.
- **Cross-domain meta-rollup is the human's job** (Zazor 2): periodically read the shared
  process-meta + sub-threshold anomalies logged by all 3 directors, and catch patterns
  that are sub-threshold per-domain but supra-threshold pooled (e.g. one model-demotion
  regression in each of dev/design/marketing = a methodology bug none alone would fire on).

## State files

- `skill-evolution-log.md` — append-only signal log + cycle records (domain-tagged).
  Channel A. Read by `skillopt-ready.py` (the SessionStart readiness hook).
- `engagement/engagement-reflections.md` (per engagement) — Channel B (`- target:` bullets)
  AND Channel C (`- worked:` bullets). Read by `skillopt-ready.py`, which harvests orphan
  reflections (no log twin) and clusters them by `(domain, target, class)`; a `resolved:`
  line under a reflection drops it from the count. Channel C clusters at 2 and is reported
  as `success_due` / `success_signals`, never as readiness.
- `skill-rejected-edits.md` — negative memory (above).
- `skill-evolution-meta.md` — two-level meta (shared process + per-domain content). Written
  by step 7, read by steps 1 and 2 of the next cycle.
- `skillopt-snapshots/<ts>/` — pre-edit file copies; the rollback source for step 5.
- Golden sets — `~/.claude/skills/system-optimization-protocol/golden/<domain>/` (scenarios
  + rubric; grow incrementally, start with 3 known-tricky cases per domain).
- Blessed mirror — `C:\releases\agentic-workflow\` (the promoted `best_skill`).

## Anti-patterns

- **Don't author edits as the director.** Codex authors; you judge. (Kills defend-bias.)
- **Don't fire on a single failure.** Wait for a ≥3 common pattern. Single = noise.
- **Don't run a full auto epoch×batch loop.** No auto-scorer, low volume, expensive. Event-driven only.
- **Don't pre-gate trivial edits.** Tier by blast radius. But every promotion is post-checked by slow-update — cheaper rigour, not zero coverage.
- **Don't self-promote a commons edit.** Escalate the reviewable proposal to the human.
- **Don't copy onto the mirror's `main` in place.** Promotion is a draft MR (branch + reasoning + gate evidence); the human merges = ship. The loop never merges or `git push`es.
- **Don't grow `skill-evolution-meta.md` unbounded.** Cap ~150 lines (like MEMORY.md); prune.
- **Don't touch per-engagement acceptance.** That's the manager's job — different role, different cadence.
- **Don't pool domain CONTENT errors across domains.** Only process-meta is shared.
- **Don't skip the rejection-buffer read.** Re-litigating settled rejections is the cost this whole loop exists to remove.
- **Don't fire a cycle on success.** Channel C is fuel for a cycle a failure earned; on its own it has nothing to close.
- **Don't let a reinforcement edit grow the corpus.** If the target file already says it, the correct output is no edit.
- **Don't end a cycle silently.** A promotion writes `resolved:`, a null cycle writes `adjudicated:`, a rollback writes neither and leaves the signals open. A cycle that writes nothing is indistinguishable from a cycle that never ran.
- **Don't leave a regressed edit on disk.** `regressed > 0` restores the snapshot and buffers the edit. Reporting a block without acting on it is worse than not checking.

## Where this skill ends and the per-domain director starts

This skill is the generic loop. Each `*-director` agent file holds only:
- The domain's **failure taxonomy** (on top of generic `rule_missing/wrong/ignored`).
- The pointer to the domain **golden set**.
- Domain-specific **edit heuristics** (its section of the meta file).
- The domain's **owned vs commons** file boundary.
