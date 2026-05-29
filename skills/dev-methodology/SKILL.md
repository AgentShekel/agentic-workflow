---
name: dev-methodology
domain: dev
description: |
  [METHODOLOGY] AI-First development methodology (spec-driven pipeline,
  project structure, skills/agents ecosystem, quality gates). Preloaded by
  dev-lead and dev-* lead agents.
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

**How work enters this methodology:** via `agency-intake` skill → `dev-lead` agent. The lead classifies engagement (research / spec / decomposition / execution / ship / done), sizes it, dispatches specialists, and hands off to `dev-director` for acceptance. No direct slash-command entry.

---

## Development Pipeline

The full path from idea to production. Each step maps to a skill (methodology) and an agent (executor). Commands are gone; the lead decides which step to enter based on the engagement's `criteria.md`.

### Step 0: Feature Research (recommended)

**What:** Pre-filter: codebase exploration, feasibility check, GO/NO-GO verdict. Prevents wasted effort on non-viable features.

**Process:**
- Parses requirements from free-text description, detects ambiguities
- Reads Project Knowledge files, checks mission alignment and scope
- Launches `code-researcher` agent for codebase exploration (blast radius, reuse opportunities)
- Assesses: mission alignment, architectural fit, complexity classification (Platform vs Product), effort (S/M/L), risks (technical + operational), dependencies
- `feasibility-assessor` validates verdict (max 2 iterations)
- Produces verdict: GO / NO-GO / CONDITIONAL / DEFER
- User approves verdict before proceeding

**Output:** `work/{feature}/research-verdict.md` + `work/{feature}/code-research.md`

**Skill:** `feature-research`
**Dispatched by:** `dev-product-lead` → `dev-product-analyst`
**Note:** Recommended for M/L features and unclear scope. Optional for obvious S features (bug fixes, small enhancements).

### Step 1: User Spec

**What:** Structured interview to capture requirements in human-readable form (Russian).

**Process:**
- Agent reads Project Knowledge files to understand the project
- Scans codebase for relevant code, patterns, integration points
- Runs 3 interview cycles with the user (general → code-informed → edge cases)
- `interview-completeness-checker` agent verifies coverage
- Creates `user-spec.md` from interview data → git commit draft
- 2 validators run in parallel (up to 3 iterations):
  - `userspec-quality-validator` — document structure, acceptance criteria testability
  - `userspec-adequacy-validator` — solution feasibility, over/underengineering
- Git commit after each validation round
- User approves → git commit approval (status: approved)

**Output:** `work/{feature}/user-spec.md` (status: approved)

**Skill:** `user-spec-planning`
**Dispatched by:** `dev-product-lead` → `dev-product-analyst`

### Step 2: Tech Spec

**What:** Technical architecture, decisions, testing strategy, implementation plan.

**Process:**
- Reads approved user-spec
- Researches codebase, checks dependencies, uses Context7 for external libraries
- Asks technical clarification questions
- Copies tech-spec template, edits sections in place → `tech-spec.md` with architecture (including Shared Resources for heavy objects like ML models, DB pools), decisions, testing strategy, brief Implementation Tasks (scope only — AC and TDD are added during task-decomposition) → git commit draft
- Implementation Tasks include Verify-smoke (executable checks: curl, python -c, docker) and Verify-user (manual UI/UX checks) fields where applicable
- Last two waves are always Audit Wave (3 parallel auditors: code, security, test) and Final Wave (QA + deploy)
- 5 validators run in parallel (up to 3 iterations):
  - `skeptic` — detects non-existent files, functions, APIs (mirages)
  - `completeness-validator` — bidirectional requirements traceability, over/underengineering, solution depth
  - `security-auditor` — OWASP Top 10 review
  - `test-reviewer` — test plan adequacy
  - `tech-spec-validator` — template compliance, task quality, wave conflict detection
- Git commit after each validation round
- User approves → git commit approval (status: approved)

**Output:** `work/{feature}/tech-spec.md` (status: approved)

**Skill:** `tech-spec-planning`
**Dispatched by:** `dev-engineering-lead` → `dev-tech-architect`

### Step 3: Task Decomposition

**What:** Break tech-spec into atomic task files.

**Process:**
- For each Implementation Task in tech-spec, `task-creator` agent copies task template and fills it (parallel)
- Each task file expands brief tech-spec scope into: acceptance criteria, TDD anchor (from Testing Strategy), context files, skills, reviewers, wave, dependencies → git commit draft
- 2 validators run in parallel (up to 3 iterations):
  - `task-validator` — template compliance, content quality
  - `reality-checker` — validates against actual codebase (file existence, feasibility)
- Cross-task integration check: both validators re-run on all tasks together — catches shared resource conflicts, duplicate heavy resource init, hidden dependencies (max 2 extra iterations)
- Git commit after each validation round
- User approves → git commit approval

**Output:** `work/{feature}/tasks/*.md` (validated)

**Skill:** `task-decomposition`
**Dispatched by:** `dev-engineering-lead` → `dev-tech-architect`

### Step 4: Implementation

Two modes, chosen by the lead based on engagement size:

**Single task** — manual control, debugging, iterating on one piece. Dispatches one engineer (`dev-backend-engineer`, `dev-frontend-engineer`, or `dev-fullstack-engineer`) against one task file.

**Full feature** — multiple tasks ready, parallel execution. Team lead orchestrates waves.

#### Mode A: Single Task

One task per session.

**Process:**
- Reads task file and all its Context Files
- Loads skills specified in task (e.g. `code-writing`, `pre-deploy-qa`, `infrastructure-setup`)
- Follows loaded skill workflow (TDD for code tasks, verification for QA tasks, etc.)
- Git commit implementation (code + tests pass)
- Runs reviewers specified in task (if any), up to 3 review iterations
- Git commit after each round of review fixes (tests pass)
- Writes entry to `decisions.md`, updates task status → done
- Git commit status + decisions

**Skill:** Loaded from task file (typically `code-writing` for code tasks)

#### Mode B: Full Feature

All tasks via agent teams. Team lead orchestrates waves of parallel work.

**Process:**
- Team lead reads tech-spec and all task files, builds execution plan
- Checks `checkpoint.yml` — if resuming after context compaction, skips completed waves (uses decisions.md as source of truth for what actually completed)
- Creates team via TeamCreate
- Executes tasks wave by wave:
  - Spawns one agent per task (parallel within wave)
  - Each teammate: follows loaded skill workflow, runs smoke verification if task has Verify-smoke (before reviews), commits code (tests pass), sends diff to reviewers, fixes findings with commits per round (max 3 rounds), commits review reports
  - Each teammate writes `decisions.md` entry
  - Lead commits status updates (task frontmatter + decisions.md) after wave completes, updates `checkpoint.yml`
- **Audit Wave** (always present): 3 auditors run in parallel (code-reviewer, security-auditor, test-reviewer) — review all feature code holistically. Issues found → lead spawns fixer agent, auditors become reviewers (max 3 fix rounds)
- **Ad-hoc agents**: when lead needs work outside planned tasks (fixing audit findings, escalations), assigns matching skill + reviewers based on work type
- **Final Wave**: QA (always), deploy + post-deploy (if applicable)
- **Escalation**: after 3 failed fix rounds — stop, report to user, write decisions.md entry, wait for decision
- User reviews results, team shuts down, `checkpoint.yml` deleted

Tasks can be code, user-action, deploy, config, or verification. Task nature is determined by its skill + description, not a separate type field.

**Skill:** `feature-execution`
**Dispatched by:** `dev-engineering-lead`

### Step 5: Done

**What:** Finalize feature, update project knowledge, archive.

**Process:**
- Reads user-spec, tech-spec, decisions.md
- Updates affected Project Knowledge files (architecture.md, patterns.md, deployment.md, etc.)
- Moves `work/{feature}/` → `work/completed/{feature}/`
- `documentation-reviewer` validates PK updates
- Commits changes

**Skill:** `documentation-writing` (for PK update rules)
**Dispatched by:** `dev-product-lead` → `dev-technical-writer`

### Step 6: Ship (when deploy applies)

**What:** Pre-deploy validation + deploy via CI/CD.

**Process:**
- `pre-deploy-qa` runs tests and acceptance criteria
- `code-reviewer` + `security-auditor` sweep on final branch state
- `deploy-reviewer` validates CI/CD config
- Push / merge triggers CI/CD; no direct server access
- `post-deploy-qa` verifies live environment via MCP tools (Playwright, Claude_Preview) against AVP

**Skills:** `pre-deploy-qa`, `deploy-pipeline`, `post-deploy-qa`
**Dispatched by:** `dev-quality-lead` + `dev-devops-engineer`

---

## Project Structure

### Project Knowledge — the Knowledge Base

All project documentation lives in `.claude/skills/project-knowledge/references/`. This is the single source of truth for everything about the project.

**4 core + optional files:**

| File | Content |
|------|---------|
| `project.md` | Purpose, audience, core features, scope |
| `architecture.md` | Tech stack, structure, dependencies, data model |
| `patterns.md` | Code conventions, git workflow, testing, business rules |
| `deployment.md` | Platform, env vars, CI/CD, monitoring |
| `ux-guidelines.md` | UI language, tone, domain glossary (optional) |

Features and roadmap live in the project backlog (external to PK).

**CLAUDE.md is minimal.** It contains only the project name, a reference to project-knowledge skill, methodology overview, and default branch. All real information lives in Project Knowledge files.

**`project-planning` skill** creates PK from scratch in new projects (invoked by `dev-product-analyst` at project bootstrap).

**`documentation-writing` skill** manages existing PK: audits, updates, checks consistency. Used by `dev-technical-writer` at Step 5 (Done).

### Work Items

```
work/{feature}/
├── user-spec.md          # Requirements (Russian, for human)
├── tech-spec.md          # Architecture (English, for agent)
├── decisions.md          # Decisions made during implementation
├── tasks/
│   ├── 1.md              # Atomic task files
│   ├── 2.md
│   └── 3.md
└── logs/                 # Working logs (interview, research, reviews)
```

Completed features are archived to `work/completed/{feature}/`.

### Agency Engagement Items

```
engagement/
├── criteria.md           # Captured by agency-intake (non-mutable after lock)
├── plan.md               # Written by dev-lead
├── acceptance-log.md     # Written by dev-director (acceptor)
└── handoff.md            # Package dev-lead hands to dev-director
```

See `engagement-protocol` skill for the canonical contract.

### Global Structure `~/.claude/`

```
~/.claude/
├── skills/               # Skills (methodology, workflow, quality — reference only)
├── agents/               # Agents (validators, reviewers, creators, leads, directors)
├── shared/               # Templates, scripts, interview plans
├── hooks/                # Automation hooks
└── CLAUDE.md             # Global instructions
```

---

## Key Principles

### Commit Strategy
Commit after each step where the repository state is stable and meaningful. Not after every action — after each result.

- **Planning stages** (user-spec, tech-spec, tasks): draft commit → validation round commits → approval commit
- **Single task execution**: implementation commit (tests pass) → review fix commits (tests pass) → status/decisions commit
- **Feature execution**: teammates commit code + review fixes, lead commits statuses per wave
- **Finalization**: single commit with PK updates + archive

### Spec-Driven Development
Write specifications before code. The hierarchy: User Spec → Tech Spec → Tasks → Code. Code starts only after specs are approved.

### Validation at Every Stage
- User spec: 2 validators (quality + adequacy)
- Tech spec: 5 validators (skeptic + completeness + security + test + template/task-quality)
- Tasks: 2 validators (template + reality)
- Code: 3 reviewers (code + test + security) + optional validators (performance, migration, accessibility) + smoke verification
- Audit Wave: 3 auditors (code + security + test) review all feature code holistically after implementation waves
- QA tasks: pre-deploy QA (tests + acceptance criteria), post-deploy QA (Playwright + MCP verification on live environment)
- Finalization: documentation-reviewer validates PK updates at Step 5
- Deploy: deploy-reviewer validates CI/CD config at Step 6

Max 3 fix iterations at each stage. See `validation-pipeline` skill for cross-cutting validator contracts.

### Project Knowledge as Single Source of Truth
Project documentation = `.claude/skills/project-knowledge/references/`. CLAUDE.md stays minimal — just a pointer. Step 5 (Done) updates PK after every feature. The `documentation-writing` skill audits PK for bloat and quality.

### Design Hierarchy
`brand-methodology` (source of truth) → `ui-ux-methodology` (recommendations) → `design-system-methodology` (tokens/specs) → `ui-styling-guide` (implementation). AI-generated assets (logo, CIP, icons, social photos) handled by `design-assets-guide`. Banners by `banner-design-guide`. Presentations by `presentation-design`. Design engagements enter via `agency-intake` → `design-lead`; `design-brand-lead` and `design-product-design-lead` dispatch specialists.

### Marketing & Visibility
`seo-auditing` orchestrates all Yandex skills (webmaster, metrika, wordstat, search, direct). `ai-visibility-methodology` audits AI platforms. `semantic-drift-methodology` analyzes topic coherence. Marketing engagements enter via `agency-intake` → `marketing-lead`; `marketing-traffic-lead`, `marketing-analytics-lead`, `marketing-content-lead` dispatch specialists.

### Complexity Guard
Features are classified as **Platform** (complex orchestration justified) or **Product** (simplicity enforced). Product features with unnecessary complexity are critical findings in completeness-validator, not minor. Principle: Adopt existing code > Adapt existing patterns > Invent new.

### Reversibility
Code changes should be reversible. For M/L features: consider feature flags. For DB migrations: ensure rollback works. For integrations: adapter pattern. Feature-execution adds human validation gates between implementation waves for M/L features. Tech-spec template includes mandatory Rollback Strategy section for M/L features (deployment rollback, data rollback, feature flags, rollback verification).

### Just-In-Time Context
Agent reads only what's needed for current task, not everything. Task files list their Context Files explicitly.

### Context7 for Library Docs
Agent uses Context7 MCP to fetch current library documentation instead of relying on training data. Used during tech-spec research and code implementation.

### Checkpoint Recovery
Feature execution persists state to `checkpoint.yml` after each wave. A `SessionStart(compact)` hook detects context compaction during long feature executions and injects recovery context — the lead resumes from the next pending wave using checkpoint + decisions.md as source of truth.

### Automation Hooks
- `SessionStart(compact)` — restores feature-execution context after compaction
- `SessionStart` — auto-loads project-knowledge files and lists active features
- `PreCommit` — scans staged files for secret patterns (API keys, private keys, credentials)

### Pipeline Metrics
Track validator effectiveness and feature pipeline stats in `metrics.md` (template: `shared/work-templates/metrics.md.template`). Updated at Step 5 (Done). Tracks: validation round counts, false positive rates, common finding patterns. Used to tune validator sensitivity over time.

### Agent Model Optimization
Template-compliance validators (task-validator, tech-spec-validator, skill-checker, documentation-reviewer, infrastructure-reviewer, deploy-reviewer) use `haiku` model — fast, cheap, sufficient for structural checks. Deep-reasoning validators (skeptic, completeness-validator, code-reviewer, security-auditor, performance-validator) use `sonnet`. Critical-path agents (dev-lead, dev-director, dev-tech-architect, pre-deploy-qa, post-deploy-qa, userspec-adequacy-validator, task-creator, reality-checker) use `opus`. Policy enforced by `~/.claude/scripts/assign-agent-models.py`.

---

## Skills Ecosystem

Per-category skill catalog (Planning / Execution / Quality & Review / Meta / Agency Cross-Cutting — ~22 skills, ~50 lines of one-liners) moved to **`references/skills-ecosystem.md`** (now in `references/`). Load that file when picking a specific skill to load for a sub-task.

→ Full per-category catalog: `references/skills-ecosystem.md`.

## Agents

Per-role agent catalog (Dev Track Leadership / Validators / Reviewers / Engineers / Research / QA / Meta — ~33 agents, ~55 lines of one-liners) moved to **`references/agents.md`** (now in `references/`). Load that file when identifying which sibling agent to dispatch for a sub-task.

Agents are isolated subprocesses with fresh context: receive input, do one job, return structured output. The dev domain currently has 3 leadership roles (top-lead + mid-leads + tech architect), 10 validators, 10 reviewers, 6 engineers, 1 researcher, 2 QA roles, and 1 meta validator.

→ Full per-role catalog with one-line purpose: `references/agents.md`.

---

## Workflow Entry Points

All work enters via `agency-intake` (user says "мне надо агенси задачу" or similar trigger). Intake captures `engagement/criteria.md`, then routes to `dev-lead`. The lead reads criteria, sizes the engagement, and picks which steps to run:

| Engagement kind | Steps the lead runs |
|---|---|
| **New project bootstrap** | infrastructure-setup → project-planning → (features follow) |
| **New feature (M/L)** | Step 0 (research) → Step 1 (user-spec) → Step 2 (tech-spec) → Step 3 (tasks) → Step 4 (execute) → Step 5 (done) → Step 6 (ship, if applicable) |
| **Small feature / ad-hoc** | Step 2 (tech-spec) → Step 3 → Step 4 → Step 5 |
| **Bug fix** | Direct `code-writing` single-task against the bug, skip Steps 0-3 |
| **Quality audit** | `code-reviewing` + `security-auditing` + `testing-methodology` sweep, no code changes |

`dev-director` accepts or rejects the handoff package against `engagement/criteria.md`. Iteration budget: 2 rework rounds; escalate to user before round 3.

To understand how a specific skill works internally, read its SKILL.md directly.
