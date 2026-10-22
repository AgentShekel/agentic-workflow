---
name: tech-spec-planning
domain: dev
description: |
  [METHODOLOGY] Tech-spec creation (architecture, decisions, testing
  strategy, implementation plan) from approved user-spec. SDD phase 2: the
  single task of the `{name}-spec` engagement, owned by dev-tech-architect.
  Preloaded by dev-tech-architect and dev-lead.
---

# Tech Spec Planning

Create the technical specification from an approved user-spec, inside the SDD `{name}-spec`
engagement (see `dev-methodology` §"Spec-Driven Development").

**Input:** `engagement/specs/user-spec.md` (status: approved) + `engagement/specs/code-research.md` + Project Knowledge
**Output:** `engagement/specs/tech-spec.md` (status: draft)
**Language:** Technical documentation in English

**Where this runs.** `engagement-workflow` dispatches `dev-tech-architect` as the owner of the
spec engagement's one task. You are a leaf (`engagement-contract`): no subagents, no user. That
shapes three things below:
- research you do yourself (Read/Grep/Glob + Context7), no `code-researcher` spawn;
- the six spec validators are run by the engine's validate phase (dev-lead lists them in
  `plan.validators`), not by you;
- approval is the spec engagement's acceptance (human directive + `dev-manager` ACCEPT). You
  never set `status: approved`; `agency-intake` does that when it opens the `{name}-impl`
  engagement.

## Phase 1: Load Context

1. Read `engagement/specs/user-spec.md`. If it is missing or its frontmatter is not
   `status: approved`, stop and return NEEDS_CONTEXT: a tech-spec over an unapproved user-spec is
   the exact failure SDD exists to prevent.
   Extract `size: S|M|L` from user-spec frontmatter — it determines testing strategy depth in tech-spec.

2. Read all files in `.claude/skills/project-knowledge/references/` (project.md, architecture.md, patterns.md, deployment.md, ux-guidelines.md, and any custom domain files). Missing files are fine — not all projects have all guides.

3. If `engagement/specs/research-verdict.md` exists, read it. Use complexity classification and risk assessment as starting point — carry forward and deepen in tech-spec.

4. user-spec.md is the single requirements source — all information from interview.yml and code research is already consolidated there.

**Checkpoint:**
- [ ] user-spec.md read, status approved, size extracted
- [ ] Project Knowledge read

## Phase 2: Code Research

Read `engagement/specs/code-research.md` (written by `code-researcher` during the user-spec phase) and
deepen it yourself to implementation level: the exact files, functions, call sites and tests the
change touches. Append your findings under `## Implementation-level analysis (tech-spec)` in the
same file. Every existing file path you later put into the tech-spec must be one you opened. A
file the feature creates is written with the marker `(new)` (`src/api/export.ts (new)`), and its
parent directory must exist or be created by an earlier task.

### Context7: Library Documentation

For each new external dependency identified in code research:
1. Use Context7 MCP (`resolve-library-id` → `query-docs`) to fetch current API documentation
2. Verify: API signatures match what code-research assumes, no deprecated methods planned
3. If library has breaking changes in latest version — note in Risks section
4. Use Context7 findings to inform Architecture and Decisions sections

This prevents mirages where tech-spec references APIs that don't exist in current library versions.

**Checkpoint:**
- [ ] code-research.md deepened with implementation-level analysis

## Phase 3: Gaps you cannot close

You cannot ask the user. Two kinds of gap, two different exits:

- **Technical gap** (an unknown about the code, a library, an environment): resolve it by
  reading. If reading cannot resolve it, pick the conservative option, record it as a Decision
  with the alternative you rejected, and list it in the tech-spec `## Open questions` section so
  the human sees it at the gate.
- **Requirements gap** (the user-spec does not say what should happen): do NOT edit the
  user-spec and do NOT invent the behaviour. Record it in `## Open questions` with the AC it
  touches, and return NEEDS_CONTEXT if the gap blocks a task. The approved user-spec changes only
  through the user.

**Checkpoint:**
- [ ] Every gap is either resolved by reading, recorded as a Decision, or listed in `## Open questions`

## Phase 4: Create tech-spec

1. Copy template:
   ```bash
   cp ~/.claude/shared/work-templates/tech-spec.md.template engagement/specs/tech-spec.md
   ```
   Then edit sections one by one using Edit tool. This keeps template structure and examples visible while you work.

2. Fill frontmatter:
   - `created`: today's date
   - `status`: draft
   - `size`: copy from user-spec (S|M|L)
   - `user_spec`: `specs/user-spec.md` + its `approved:` date
   - `branch`: `dev` (simple change, single component) or `feature/{name}` (multiple components, architectural changes)

3. Fill all template sections. The template defines section structure — follow it directly.
   Fill Complexity Classification: determine if feature is Platform/Product/Mixed. If research-verdict.md exists, use its classification as starting point. Product features must enforce simplicity.
   In Architecture → Shared Resources: list heavy resources (ML models, DB pools, browser instances, API clients) shared across components. Specify owner (who creates), consumers, instance count. If none — write "None".
   Fill Risks with concrete technical and operational risks for THIS feature. If research-verdict.md has risk assessment, carry forward and deepen. 2+ entries for M/L features.
   Fill Rollback Strategy for M/L features (required) or S features with DB changes (recommended): deployment rollback method, data rollback, feature flags if applicable, rollback verification steps.

4. Fill Implementation Tasks by waves. The `{name}-impl` engagement's dev-lead maps these tasks
   onto its plan one to one, so write them in the shape the engine executes:
   - **Covers:** the ids it delivers (`AC-2, AC-5, TC-1`). Every `AC-N` in the user-spec and every
     `TC-N` in this tech-spec is covered by at least one task. A TC no code task can own ("all
     tests pass", "no regressions") is covered by an Audit or Final Wave declaration: write it in
     that declaration's Covers. A task that covers nothing is either infrastructure another task
     needs (say which) or scope creep (delete it).
   - **Owner:** the specialist agentType (`dev-backend-engineer`, `dev-frontend-engineer`,
     `dev-fullstack-engineer`, `dev-devops-engineer`).
   - **Files to modify** (repo-relative; new files marked `(new)`) and **Files to read**. Tasks in the same wave have
     strictly disjoint Files to modify: parallel worktrees merge by octopus. Shared contracts
     (types, schema) go alone in an earlier wave.
   - **Depends on:** earlier task ids.
   - Description, Skill, Reviewers, Verify-smoke (optional), Verify-user (optional). Select skill
     and reviewers from [skills-and-reviewers.md](references/skills-and-reviewers.md).

   For each task, write `Verify-smoke:` when the task involves:
   - External API integration → curl/httpie command to real endpoint with expected response
   - Library/model initialization → `python -c` or import check that verifies setup
   - Docker/infrastructure → `docker compose build`, `docker run` commands
   - LLM/prompt work → spawn agent with prompt + test question, check response
   - External service API (OpenRouter, Stripe, etc.) → test API call with expected response
   - MCP-verifiable UI/frontend → use Playwright MCP or similar to check rendered page
   Write `Verify-user:` when user should check something: UI on localhost, behavior, UX.
   Omit both if task is purely internal logic covered by unit tests.

   **Task brevity rules:**
   - Tasks are brief scope descriptions (2-3 sentences). Detailed steps and AC come from the impl engagement's decomposition and per-task contract.
   - Task Description answers WHAT and WHY, not HOW. No step-by-step instructions, no line numbers, no implementation details.
   - All technical decisions belong in the Decisions section, not in task descriptions. If you're writing a decision rationale inside a task — move it to Decisions.

5. The last two waves are always **Audit Wave** and **Final Wave**, in that order. They declare
   the verification plan; the impl engagement maps them onto its validate phase (see `dev-lead`
   §"SDD impl engagement"), so they are written as declarations, not as code tasks:

   **Audit Wave** (always present):
   - **Code Audit** (`code-reviewer`) — holistic code quality review of all feature code
   - **Security Audit** (`security-auditor`) — OWASP Top 10 across all components
   - **Test Audit** (`test-reviewer`) — test quality and coverage across all components

   **Final Wave:**
   - **QA** (`pre-deploy-qa`) — always present. Acceptance testing: run all tests, verify every `AC-N` from user-spec and the tech-spec criteria.
   - **Deploy** (`dev-devops-engineer` task) — only if deploy is needed for this feature.
   - **Post-deploy verification** (`post-deploy-qa`) — only if live-environment checks are needed (MCP tools listed in Agent Verification Plan → Tools required).
   QA is mandatory. Deploy and post-deploy — if applicable.

6. Task Count Check: if >15 code tasks, split them into an MVP set and an Extension set inside
   Implementation Tasks and list the split in `## Open questions`. The human decides at the gate
   which set the impl engagement takes.

7. **AVP executability.** You cannot co-sign your own AVP. Make every AVP step and every
   `Verify-smoke` a concrete command or tool call with a concrete expected value, list every tool
   in `### Tools required` (the impl engagement's preflight checks each one is reachable before
   any code is written), and in `### Executability review` write exactly
   `Executability review: validate-phase — reality-checker + test-reviewer against the spec engagement's AVP criterion`.
   The spec engagement's `criteria.md` carries the AVP as a Done-when item, so those two validators judge it.

8. Write your executor report per `engagement-contract` and return.

**Checkpoint:**
- [ ] tech-spec.md created in `engagement/specs/` with all sections
- [ ] Every `AC-N` from user-spec and every `TC-N` covered by a task or an Audit/Final declaration; every code task names Covers, Owner, Files, Depends on
- [ ] Same-wave tasks have disjoint Files to modify
- [ ] No AC or TDD anchors in tasks (those come from the impl engagement)
- [ ] Technical decisions are in Decisions section, not in task descriptions
- [ ] Final Wave present with QA (mandatory) + Deploy/Post-deploy (if applicable)
- [ ] Task count ≤15, or the MVP/Extension split is listed in `## Open questions`

## Phase 5: Validation (run by the engine, not by you)

The spec engagement's validate phase runs these on your tech-spec (dev-lead puts them in
`plan.validators`), and the engine adversarially verifies each finding:

| Validator | Agent | Checks |
|-----------|-------|--------|
| Mirage detector | `skeptic` | Non-existent files, APIs, functions, dependencies |
| Completeness + adequacy | `completeness-validator` | Bidirectional traceability user-spec ↔ tech-spec, scope creep, overengineering, underengineering, solution depth |
| Security | `security-auditor` | OWASP, input validation, auth, sensitive data |
| Testing strategy | `test-reviewer` | Test plan adequacy for feature size S/M/L, AVP executability |
| Template + wave conflicts | `tech-spec-validator` | All sections filled, frontmatter, format, skills/reviewers, wave conflict detection |
| Reality + AVP review | `reality-checker` | Task claims against the codebase; Verify-smoke and AVP concrete, tools listed (static) |

Before you return, walk the tech-spec through these five lenses yourself so the validators find
little. Self-review is not validation; it only saves a rework round.

**Rework.** Three ways a round comes back to you:
- a per-task `rework` verdict inside the run: fix what the reviewer names;
- a fresh run at the same iteration after a gate failure: `specs/tech-spec.md` already exists.
  Read the newest `validation-outputs/*-iter-{N}-*.json` files (highest timestamp per validator)
  and fix every finding of severity medium or above; record each in your executor report with
  what you changed, or why it needs no change;
- a new iteration (`iteration` ≥ 2) after a REJECT or DIRECTED: before touching the spec,
  read the previous iteration's `validation-outputs/*-iter-{N-1}-*.json`, the latest
  `acceptance-log.md` entry and `human-directive.md`. Every finding and every answer the human gave
  to an open question is addressed in the spec. Your executor report gets a `## Iteration N`
  section (`engagement-protocol` §"4-iter") listing each one with what you changed, or why it
  needs no change.
Either way: fix `engagement/specs/tech-spec.md` in place, keep `status: draft`.

## Final Check

- [ ] tech-spec.md created with all sections (Implementation Tasks are brief scope descriptions)
- [ ] Every AC traced, every gap visible in `## Open questions`
- [ ] status = draft (approval belongs to the spec engagement's acceptance)
