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
| Reflect (backward) | This loop, step 1 — attribute failures to a skill/agent |
| Edit patch (gradient) | `append` / `insert_after` / `replace` / `delete` op on a skill/agent file |
| Learning rate / clipping | `edit_budget` — max edits accepted per cycle |
| Validation gate | Golden-scenario run via `skill-testing` |
| Momentum (anti-forgetting) | Slow-update: golden-set before/after, 4-bucket categorisation |
| Meta-learning | Two-level meta (shared process + domain content) |
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
| Promote `~/.claude` → releases mirror | director-optimizer (domain files) / human (commons) |
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
- **Reflection sweep pathway (monthly):** director runs a clustering pass over
  `engagement/engagement-reflections.md` files (last 30–60 days, this domain).
  Triggers a cycle when **cluster size ≥3 same `target × class`** OR (once event
  ledger lands) Langfuse trend Δ thresholds: reject-rate ↑ ≥20%, validator
  FP-rate ↑ ≥30%, P95 latency ≥2× baseline. This pathway catches slow-burn
  patterns sub-threshold per-engagement but supra-threshold pooled —
  Reflexion-style per-engagement signal feeding the SkillOpt event-driven gate.

Optimise on a **common pattern across the batch**, never a single trajectory (single
failures are noise; patching them overfits). This is SkillOpt's
"identify COMMON failure patterns — not individual edge cases".

## The loop

### 1. Reflect (Codex authors, taxonomy-classified)

**Dry-run signals are skipped.** Before reading signals, filter
`skill-evolution-log.md` entries with the line `dryrun: true` — those are
synthetic exercises (dry-run seed) and must not drive real edits. A real
cycle reflect step considers only signals without that marker.

Director dispatches **Codex via `codex-bridge`** with: the accumulated signals,
`acceptance-log.md`, `consilium-summary.md`, `validation-outputs/`. Codex classifies each
recurring finding and attributes it to a specific `agents/X.md` or `skills/Y/SKILL.md`:

- **`rule_missing`** — the skill was silent on this → propose `append` / `insert_after`.
- **`rule_wrong`** — an existing rule misled → propose `replace`.
- **`rule_ignored`** — the rule was correct but the agent didn't follow it → do NOT add text;
  propose a **structural** fix (raise it, make it a gate, tighten emphasis). Adding more
  text to an ignored rule just grows the file without changing behaviour.
- Plus the domain's own failure types (see the per-domain director file).

Codex output = a JSON patch list (see edit format). Director reads the shared process-meta
+ its domain content-meta BEFORE judging, and the rejection buffer (step 2).

### 2. Select (bounded edits = learning rate)

- Cap accepted patches at `edit_budget` per cycle (start **L = 4–6**). Bigger early in a
  large overhaul, smaller as it converges (the cosine instinct). Forces highest-impact first.
- **Read `skill-rejected-edits.md` first.** If Codex re-proposes a previously-reverted
  edit, drop it (or demand it explain what changed). The buffer is negative memory — it
  exists so cycles don't re-litigate settled rejections.

### 3. Gate (golden-set, blast-radius tiered)

Before any edit reaches the blessed mirror it must pass `skill-testing` on the relevant
golden scenarios. Tier the gate by **blast radius** (anti-overhead):

| Blast radius | Examples | Gate |
|---|---|---|
| High | a lead, a manager, a director, a shared protocol, a widely-loaded skill | **Mandatory** golden-set + slow-update before promote |
| Low | one specialist, a typo, a narrow methodology skill | Gate optional |

Pass = no regression on the golden set AND the targeted failure is closed. No auto-scorer
exists, so the gate verdict is rubric-judged: **Codex proposes a pass/fail read, the
director adjudicates** (mirror of adversary → supreme-judge). FAIL → the edit goes to
`skill-rejected-edits.md` with what broke.

### 4. Promote

- **Domain-owned files** that pass the gate: director promotes `~/.claude/X` →
  `C:\releases\agentic-workflow\` (the blessed `best_skill`).
- **Commons files** (see governance): director cannot self-promote — escalates to human.

### 5. Slow-update (anti-forgetting, high-blast cycles only)

Re-run the golden set on the **pre-cycle** and **post-cycle** state. Categorise each
scenario (SkillOpt buckets):

- **regressed** (was-good → now-bad) — HIGHEST PRIORITY; blocks the cycle.
- **persistent_fail** (bad → bad) — escalate; the edit didn't help.
- **improved** (bad → good) — the win; record it.
- **stable_success** (good → good) — ignore; spend no attention here.

This is exactly what `anti-pattern-detector` did manually after the big refactor — now
systematic, on the golden set.

### 6. Meta (two-level — see Zazor-2 split)

- **Shared process lessons** (`skill-evolution-meta.md`, all 3 directors read+write):
  lessons about *how to optimise* that hold across domains, e.g. "after demoting a
  validator to a cheaper model, recheck reasoning-heavy ones". Apply when ambiguous; do
  NOT force a past lesson if the current evidence clearly contradicts it (anti-overfit).
- **Domain content lessons** (the domain section of the same file): edit heuristics
  specific to this domain's skills.

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

`<your-memory>/skill-rejected-edits.md` (path resolved by Claude Code workspace memory; see your CLAUDE.md), append-only.
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
- `skill-rejected-edits.md` — negative memory (above).
- `skill-evolution-meta.md` — two-level meta (shared process + per-domain content).
- Golden sets — `~/.claude/skills/system-optimization-protocol/golden/<domain>/` (scenarios
  + rubric; grow incrementally, start with 3 known-tricky cases per domain).
- Blessed mirror — `C:\releases\agentic-workflow\` (the promoted `best_skill`).

## Anti-patterns

- **Don't author edits as the director.** Codex authors; you judge. (Kills defend-bias.)
- **Don't fire on a single failure.** Wait for a ≥3 common pattern. Single = noise.
- **Don't run a full auto epoch×batch loop.** No auto-scorer, low volume, expensive. Event-driven only.
- **Don't gate trivial edits.** Tier by blast radius.
- **Don't self-promote a commons edit.** Escalate to human.
- **Don't grow `skill-evolution-meta.md` unbounded.** Cap ~150 lines (like MEMORY.md); prune.
- **Don't touch per-engagement acceptance.** That's the manager's job — different role, different cadence.
- **Don't pool domain CONTENT errors across domains.** Only process-meta is shared.
- **Don't skip the rejection-buffer read.** Re-litigating settled rejections is the cost this whole loop exists to remove.

## Where this skill ends and the per-domain director starts

This skill is the generic loop. Each `*-director` agent file holds only:
- The domain's **failure taxonomy** (on top of generic `rule_missing/wrong/ignored`).
- The pointer to the domain **golden set**.
- Domain-specific **edit heuristics** (its section of the meta file).
- The domain's **owned vs commons** file boundary.
