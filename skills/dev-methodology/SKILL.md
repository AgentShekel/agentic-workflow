---
name: dev-methodology
domain: dev
description: |
  [METHODOLOGY] AI-First development methodology (spec-driven pipeline,
  project structure, skills/agents ecosystem, quality gates). Preloaded by
  dev-lead.
---

# AI-First Development Methodology

> **Naming note (2026-05-28):** the per-engagement **acceptor** is now `dev-manager` (loads `acceptance-protocol`). The `dev-director` agent is now a separate out-of-band **system-optimizer** (`system-optimization-protocol`). Where this doc says "dev-director … acceptance / acceptor", read "dev-manager".

## What Is This

A structured development approach for AI agents under the agency architecture. Every feature goes through a pipeline: idea → spec → architecture → tasks → implementation → documentation update. Each stage has automated validators and quality gates. QA and deploy are regular tasks in the tech-spec, not separate pipeline steps.

Core problems it solves:
- **Context loss between sessions** — distributed knowledge base persists across sessions
- **Quality without human review** — automated validators at every stage
- **Scope creep** — specs approved before coding starts
- **Outdated agent knowledge** — Context7 MCP fetches current library docs

**How work enters this methodology:** via `agency-intake` skill → the `engagement-workflow` Workflow (see `agency-intake` §7a). `dev-lead` is the Workflow's `lead:plan` step — it reads `criteria.md`, sizes the engagement, and plans it (specialists / waves / validators); it does NOT dispatch. The Workflow script then fans out specialists and validators, assembles the handoff, and stops at the seam; the human-gate (consilium → directive → `dev-manager` acceptance) is downstream. No direct slash-command entry.

---

## Development Pipeline

The full path from idea to production. Each step maps to a skill (methodology) and an agent (executor). Commands are gone; the lead decides which step to enter based on the engagement's `criteria.md`.

Steps 0-3 are the SDD part of the pipeline (§"Spec-Driven Development" below). They run for
M/L features, new projects and M/L refactors; S work, bugfixes, infra and audits start at Step 4
from `criteria.md` alone.

### Step 0: Feature Research (optional, inside SDD phase 1)

**What:** Pre-filter: codebase exploration, feasibility check, GO/NO-GO verdict. Prevents wasted effort on non-viable features.

**Process:**
- Parses requirements from free-text description, detects ambiguities
- Reads Project Knowledge files, checks mission alignment and scope
- Codebase exploration (blast radius, reuse opportunities)
- Assesses: mission alignment, architectural fit, complexity classification (Platform vs Product), effort (S/M/L), risks (technical + operational), dependencies
- Produces verdict: GO / NO-GO / CONDITIONAL / DEFER
- User approves verdict before proceeding

**Output:** `engagement/specs/research-verdict.md` + `engagement/specs/code-research.md`

**Skill:** `feature-research`
**Note:** Recommended for M/L features and unclear scope.

### Step 1: User Spec (SDD phase 1, in intake)

**What:** Structured interview to capture requirements in human-readable form (Russian).

**Process:**
- Runs in the main loop inside `agency-intake` step 5c.1: the interview needs the user, and nobody inside `engagement-workflow` can reach the user
- `engagement/specs/` is the feature folder: every spec agent gets `feature_path = engagement/specs`
- Reads Project Knowledge, `code-researcher` scans the codebase → `engagement/specs/code-research.md`
- 3 interview cycles with the user (general → code-informed → edge cases), `interview-completeness-checker` verifies coverage
- `user-spec.md` from the template; every acceptance criterion gets a stable id `AC-N`
- 2 validators in parallel (up to 3 iterations): `userspec-quality-validator`, `userspec-adequacy-validator`; reports in `engagement/specs/logs/userspec/`
- User approves → `status: approved`. From here the user-spec changes only through the user

**Output:** `engagement/specs/user-spec.md` (status: approved)

**Skill:** `user-spec-planning`
**Owner:** `agency-intake` (main loop)

### Step 2: Tech Spec (SDD phase 2, the `{name}-spec` engagement)

**What:** Technical architecture, decisions, testing strategy, implementation tasks traced to AC ids.

**Process:**
- `agency-intake` writes `criteria.md` with `sdd: spec`; `dev-lead` plans one artefact-mode task owned by `dev-tech-architect`
- The architect reads the approved user-spec, deepens `code-research.md`, checks external libraries via Context7, writes `specs/tech-spec.md` (`status: draft`)
- Implementation Tasks are written in the shape the engine executes: Covers (`AC-N`/`TC-N`), Owner, Files to modify (disjoint per wave), Depends on, Verify-smoke / Verify-user
- Audit Wave and Final Wave are declarations that the impl engagement maps onto its validate phase
- Gaps the architect cannot close go to `## Open questions`; the user-spec is never edited here
- The engine's validate phase runs `skeptic`, `completeness-validator`, `security-auditor`, `test-reviewer`, `tech-spec-validator`, `reality-checker`
- PROCEED only when the tech-spec has no open question left or the user accepts every assumed option as written; a different answer is a REJECT and a rework round
- Normal acceptance of the tier (M: peer-opus adversary, L: full consilium) → human directive → `dev-manager`. The human directive PROCEED is the approval of the tech-spec

**Output:** `engagement/specs/tech-spec.md`; after ACCEPT intake sets `status: approved` + `approved_by`

**Skill:** `tech-spec-planning`
**Owner:** `dev-tech-architect` (dispatched by the engagement-workflow)

### Step 3: Task Decomposition (SDD phase 3, start of the `{name}-impl` engagement)

**What:** Approved tech-spec → engagement plan, without re-design.

**Process:**
- `agency-intake` archives the spec engagement, opens `{name}-impl` with the specs copied in, flips only the tech-spec's approval metadata, writes `criteria.md` with `sdd: impl` and Done-when bullets `crit-N (AC-k)` / `crit-N (TC-k)`
- `dev-lead` refuses to plan over an unapproved tech-spec, then maps Implementation Tasks one to one onto `plan.tasks` / `plan.waves`; Audit/Final waves → `plan.validators`
- Any deviation the lead is forced into is recorded as `SDD drift` in `scope-sync.md`; the manager adjudicates it
- The engine's decompose phase writes `tasks/*.md`; with `A.contracts` on, each task also gets a co-signed contract

**Output:** `plan.md`, `engagement/tasks/*.md`

**Skill:** `task-decomposition`
**Owner:** `dev-lead` (the impl engagement's `lead:plan` step)

### Step 4: Implementation

Two plan shapes, set by the lead's plan and run by the **engagement-workflow deliver phase** — the lead PLANS, it does not orchestrate; the Workflow script fans specialists out:

**Single task** — one engineer (`dev-backend-engineer`, `dev-frontend-engineer`, or `dev-fullstack-engineer`) against one task. The plan has one task in one wave.

**Full feature** — multiple tasks across ordered waves with dependencies. The plan groups tasks into waves (same-wave tasks disjoint, run in parallel; a later wave may depend on an earlier one).

#### Mode A: Single Task

One task, one specialist, inside the deliver phase.

**Process:**
- The specialist reads the task + `criteria.md`, loads its skill (e.g. `code-writing`, `pre-deploy-qa`), follows the workflow (TDD for code), implements in its OWN git worktree off the integration HEAD
- Runs its own tests; commits (code + tests pass)
- A scoped `code-reviewer` judges the task against its cited criteria (passing tests is not sufficient — the contract must be met literally); review→rework up to the tier budget (S=1 / M=2 / L=3)
- Writes its executor-report, opening with `## Criteria acknowledgement`

**Skill:** Loaded from the task (typically `code-writing` for code tasks)

#### Mode B: Full Feature

Multiple tasks across waves — orchestrated by the engagement-workflow deliver phase. NOT a `TeamCreate` team, NOT a "team lead": the Workflow script owns fan-out.

**Process:**
- The `lead:plan` step defines tasks, waves, and dependencies; the Workflow script — not a lead — dispatches them
- Each wave: one specialist per task in parallel, each in its own worktree off the CURRENT integration HEAD (so a later wave sees earlier waves' merged work), each with per-task scoped review→rework (tier budget)
- **Wave barrier:** the deliver phase consolidates the wave (code: octopus-merge the disjoint branches, overlap → sequential-merge + resolver; artefact: manifest-verify each file exists & is non-empty), runs repo-root tests, and **HARD-STOPS** the engagement if any task is blocked, crashed, or did not pass review — no silent proceed past a broken wave
- **Validation:** the engagement-workflow **validate phase** runs the plan's validators (parallel, by agentType) then adversarially verifies each finding, writing the canonical `validation-outputs/*.json` — this replaces the old "audit wave"
- **Resume:** state is the Workflow run journal — re-invoke with `resumeFromRunId` to replay completed steps from cache and re-run only changed/failed ones (NOT `checkpoint.yml` — that was the retired `feature-execution` model)
- **Escalation:** rework budget exhausted, or a blocked/crashed task → deliver-phase hard-stop → surfaced to the user via `readyForAcceptance:false`

Tasks can be code, user-action, deploy, config, or verification — task nature follows its skill + description, not a type field.

**Skill:** `code-writing` (per task); wave orchestration = the engagement-workflow deliver phase (`feature-execution` archived 2026-06-05)
**Owner:** the engagement-workflow deliver phase

### Step 5: Done

**What:** Finalize feature, update project knowledge, archive.

**Process:**
- Reads user-spec, tech-spec (SDD) or `criteria.md`, and the handoff
- Updates affected Project Knowledge files (architecture.md, patterns.md, deployment.md, etc.)
- The engagement (with its `specs/`) is archived by `engagement-archive.py` after ACCEPT
- `documentation-reviewer` validates PK updates
- Commits changes

**Skill:** `documentation-writing` (for PK update rules)
**Owner:** `dev-technical-writer` (dispatched by the engagement-workflow)

### Step 6: Ship (when deploy applies)

**What:** Pre-deploy validation + deploy via CI/CD.

**Process:**
- `pre-deploy-qa` runs tests and acceptance criteria
- `code-reviewer` + `security-auditor` sweep on final branch state
- `deploy-reviewer` validates CI/CD config
- Push / merge triggers CI/CD; no direct server access
- `post-deploy-qa` verifies live environment via MCP tools (Playwright, Claude_Preview) against AVP

**Skills:** `pre-deploy-qa`, `deploy-pipeline`, `post-deploy-qa`
**Owner:** `dev-devops-engineer` + `pre-deploy-qa` / `post-deploy-qa` (dispatched by the engagement-workflow)

---

## Project Structure

On-disk layout (project knowledge, work items, engagement items, `~/.claude/`) moved to
**`references/project-structure.md`** (S8e skill diet, 2026-06-10) — load it when you need the
directory layout. Hot path: Project Knowledge = `.claude/skills/project-knowledge/references/`
(project/architecture/patterns/deployment/ux-guidelines); engagement items, specs included,
under `engagement/` (see `engagement-protocol`). The old `work/{feature}/` layout is retired.

---

## Key Principles

### Commit Strategy
Commit after each step where the repository state is stable and meaningful. Not after every action — after each result.

- **Single task execution**: implementation commit (tests pass) → review fix commits (tests pass) → status/decisions commit
- **Feature execution**: teammates commit code + review fixes, lead commits statuses per wave
- **Finalization**: single commit with PK updates + archive

### Spec-Driven Development
Write specifications before code. The hierarchy: User Spec → Tech Spec → Tasks → Code. Code starts only after both specs are approved by the human.

**When:** dev, route `full`, M/L feature, new project or M/L refactor. Not for S, bugfixes, infra-only, audits; the user may waive it (`sdd: off` + reason in `criteria.md`).

**How it maps onto the engine** (the engine is unchanged; SDD lives in intake, the leads and the acceptance gates):

| Phase | Where | Artefact | Human sign-off |
|---|---|---|---|
| 0. Project brief (new project only) | `agency-intake` main loop (`project-planning` Part A), then the `{name}-bootstrap` engagement, `sdd: bootstrap` | `specs/project-brief.md`; then PK docs + infrastructure in the repo | approves the brief in chat; the docs at the bootstrap gate |
| 1. User spec | `agency-intake` main loop (interview needs the user) | `specs/user-spec.md`, AC ids `AC-N` | approves in chat |
| 2. Tech spec | `{name}-spec` engagement, `sdd: spec`, artefact mode, one `dev-tech-architect` task | `specs/tech-spec.md`, tasks traced to AC | human directive at the spec engagement's gate |
| 3. Tasks + code | `{name}-impl` engagement, `sdd: impl`; dev-lead maps tech-spec tasks one to one | code, `tasks/*.md` | normal acceptance |

**Why two engagements.** The engine plans tasks in discovery, before anything else runs, so a
tech-spec written inside the same run could never drive its own task plan; and the engine has no
mid-run human pause. The spec engagement's acceptance gate is the approval point.

**Invariants:** the approved user-spec and project brief change only through the user; `status: approved` on a
tech-spec is written only by intake when it opens `{name}-impl`; the impl lead does not re-design,
it records forced deviations as `SDD drift`; `completeness-validator` traces user-spec ↔ tech-spec
↔ code at the impl gate.

### Validation at Every Stage
- User spec: 2 validators (quality + adequacy), run from intake
- Tech spec: 6 validators (skeptic + completeness + security + test + template + reality) in the spec engagement's validate phase
- Tasks: dev-lead's coverage + disjoint-files self-check; per-task contract co-sign when `A.contracts` is on
- Code: 3 reviewers (code + test + security) + optional validators (performance, migration, accessibility) + smoke verification
- Audit Wave: 3 auditors (code + security + test) review all feature code holistically after implementation waves
- QA tasks: pre-deploy QA (tests + acceptance criteria), post-deploy QA (Playwright + MCP verification on live environment)
- Finalization: documentation-reviewer validates PK updates at Step 5
- Deploy: deploy-reviewer validates CI/CD config at Step 6

Max 3 fix iterations at each stage. See `validation-pipeline` skill for cross-cutting validator contracts.

### Project Knowledge as Single Source of Truth
Project documentation = `.claude/skills/project-knowledge/references/`. CLAUDE.md stays minimal — just a pointer. Step 5 (Done) updates PK after every feature. The `documentation-writing` skill audits PK for bloat and quality.

### Design Hierarchy
`brand-methodology` (source of truth) → `ui-ux-methodology` (recommendations) → `design-system-methodology` (tokens/specs) → `ui-styling-guide` (implementation). AI-generated assets (logo, CIP, icons, social photos) handled by `design-assets-guide`. Banners by `banner-design-guide`. Presentations by `presentation-design`. Design engagements enter via `agency-intake` → `design-lead`; the engagement-workflow dispatches specialists (planned by design-lead).

### Marketing & Visibility
`seo-auditing` orchestrates all Yandex skills (webmaster, metrika, wordstat, search, direct). `ai-visibility-methodology` audits AI platforms. `semantic-drift-methodology` analyzes topic coherence. Marketing engagements enter via `agency-intake` → `marketing-lead`; the engagement-workflow dispatches specialists (planned by marketing-lead).

### Complexity Guard
Features are classified as **Platform** (complex orchestration justified) or **Product** (simplicity enforced). Product features with unnecessary complexity are critical findings in completeness-validator, not minor. Principle: Adopt existing code > Adapt existing patterns > Invent new.

### Reversibility
Code changes should be reversible. For M/L features: consider feature flags. For DB migrations: ensure rollback works. For integrations: adapter pattern. The engagement-workflow deliver phase adds review→rework gates between implementation waves for M/L features. Tech-spec template includes mandatory Rollback Strategy section for M/L features (deployment rollback, data rollback, feature flags, rollback verification).

### Just-In-Time Context
Agent reads only what's needed for current task, not everything. Task files list their Context Files explicitly.

### Context7 for Library Docs
Agent uses Context7 MCP to fetch current library documentation instead of relying on training data. Used during tech-spec research and code implementation.

### Resume & compaction recovery
Long engagements run INSIDE the `engagement-workflow` Workflow, which executes out-of-band — a main-loop compaction does NOT interrupt it — and resumes via `resumeFromRunId` (completed steps replay from cache; only changed/failed ones re-run). On a `SessionStart(compact)` the `post-compact-restore.sh` hook re-points the conductor at the live engagement artefacts (`criteria.md`, `plan.md`, `validation-log.md`, `handoff.md`, `acceptance-log.md`). The retired `feature-execution` `checkpoint.yml` / `work/` model is gone.

### Automation Hooks
- `SessionStart(compact)` — restores in-flight engagement context after compaction
- `SessionStart` — auto-loads project-knowledge files and lists active features
- `PreCommit` — scans staged files for secret patterns (API keys, private keys, credentials)

### Pipeline Metrics
Track validator effectiveness and feature pipeline stats in `metrics.md` (template: `shared/work-templates/metrics.md.template`). Updated at Step 5 (Done). Tracks: validation round counts, false positive rates, common finding patterns. Used to tune validator sensitivity over time.

### Agent Model Optimization
Each agent declares its model tier in its own `model:` frontmatter — the source of truth, travelling with the agent file. Policy by category:
- **opus** — top-level leads, per-engagement acceptor managers, system-optimizer directors, `dev-tech-architect`, and verdict-bearing critical validators (`code-reviewer`, `security-auditor`, `skeptic`, `reality-checker`, `userspec-adequacy-validator`): a wrong call here corrupts everything downstream.
- **haiku** — mechanical / template-compliance validators (`task-validator`, `tech-spec-validator`, `skill-checker`, `documentation-reviewer`, `infrastructure-reviewer`, `deploy-reviewer`, `accessibility-validator`, `prompt-reviewer`).
- **sonnet** — everything else: engineers, designers, analysts, researchers, and non-critical deep-reasoning validators.

Current distribution: 15 opus / 35 sonnet / 8 haiku (58 agents). Validate with `python ~/.claude/scripts/check-agent-models.py` — a roster-agnostic lint that fails if any agent is missing a `model:` line or declares an unknown tier (it hardcodes no agent names, so it never breaks on roster changes).

---

## Skills Ecosystem

Per-category skill catalog (Planning / Execution / Quality & Review / Meta / Agency Cross-Cutting — ~22 skills, ~50 lines of one-liners) moved to **`references/skills-ecosystem.md`** in v0.2 (the reference split). Load that file when picking a specific skill to load for a sub-task.

→ Full per-category catalog: `references/skills-ecosystem.md`.

## Agents

Per-role agent catalog (Dev Track Leadership / Validators / Reviewers / Engineers / Research / QA / Meta — ~33 agents, ~55 lines of one-liners) moved to **`references/agents.md`** in v0.2 (the reference split). Load that file when identifying which sibling agent to dispatch for a sub-task.

Agents are isolated subprocesses with fresh context: receive input, do one job, return structured output. The dev domain currently has 2 leadership roles (dev-lead planning + dev-tech-architect), 10 validators, 10 reviewers, 6 engineers, 1 researcher, 2 QA roles, and 1 meta validator.

→ Full per-role catalog with one-line purpose: `references/agents.md`.

---

## Workflow Entry Points

All work enters via `agency-intake` (user says "мне надо агенси задачу" or similar trigger). Intake captures `engagement/criteria.md`, then (for dev) invokes the `engagement-workflow` Workflow. `dev-lead` is its `lead:plan` step — it reads criteria, sizes the engagement, and plans which steps run; the Workflow then orchestrates them:

| Engagement kind | Steps the plan runs |
|---|---|
| **New project bootstrap** | SDD phase 0: brief interview in intake (`project-planning` Part A) → `{name}-bootstrap` engagement: `project-planning` Part B (PK docs) → `infrastructure-setup` → (features follow, each through SDD) |
| **New feature (M/L), M/L refactor** | SDD: Step 1 (user-spec, intake) → Step 2 (`{name}-spec` engagement) → Step 3 + Step 4 (`{name}-impl` engagement) → Step 5 → Step 6 (ship, if applicable) |
| **Small feature (S) / ad-hoc** | Step 4 from `criteria.md` → Step 5 |
| **Bug fix** | Direct `code-writing` single-task against the bug, skip Steps 0-3 |
| **Quality audit** | `code-reviewing` + `security-auditing` + `testing-methodology` sweep, no code changes |

After the Workflow stops at the handoff seam, the human-gate runs and `dev-manager` accepts or rejects the handoff package against `engagement/criteria.md` (per `acceptance-protocol`). Iteration budget: 2 rework rounds; escalate to user before round 3.

To understand how a specific skill works internally, read its SKILL.md directly.
