---
name: project-planning
domain: dev
description: |
  [METHODOLOGY] New project bootstrap (interview, tech decisions, project-knowledge docs).
  Part A, the interview, runs in agency-intake's main loop and ends in an
  approved project brief; Part B, dev-product-analyst in the
  `{name}-bootstrap` engagement, fills the docs from that brief. Preloaded
  by dev-product-analyst.
---

# Project Planning

Adaptive interview → tech decisions → approved project brief → project-knowledge documentation.

**Who runs what.** The bootstrap is split by who can reach the user (see `dev-methodology`
§"Spec-Driven Development", phase 0):
- **Part A: Interview (Phases 1-2).** `agency-intake` runs it in the main loop, step 5c.0,
  because the interview needs the user and nobody inside `engagement-workflow` can reach the user.
  Output: `engagement/specs/project-brief.md` with `status: approved`, plus
  `engagement/specs/code-research.md` when the repo already has code.
- **Part B: Documentation (Phases 3-4).** `dev-product-analyst`, the PK task of the
  `{name}-bootstrap` engagement (`sdd: bootstrap`), dispatched by the engine. It works only from
  what is on disk: the approved brief, `code-research.md`, the repo. It never asks the user
  anything; the user's sign-off on the documentation is the engagement's acceptance gate.

Paths below are relative to the project root that holds `engagement/`.

## Output Files

**Part A:** `engagement/specs/project-brief.md` (shape in Phase 2.4).

**Part B, Project Knowledge** (`.claude/skills/project-knowledge/references/`):
- **project.md** — overview, audience, problem, key features, scope
- **architecture.md** — tech stack, project structure, dependencies, data model
- **patterns.md** — git workflow (code patterns, testing, business rules are filled later during development)
- **deployment.md** — platform, environment, CI/CD, monitoring
- **ux-guidelines.md** — only if project has significant UI

Plus the project's `CLAUDE.md` (pointer file) and the backlog file, if the brief names one.

---

# Part A: Interview (main loop, `agency-intake` step 5c.0)

## Interview Methodology

Conduct the interview in Russian, under `human-voice` (chat surface).

**One question at a time.** Ask one question, wait for the answer, then form the next question based on the response.

**Build on answers.** If user mentioned a domain — ask domain-relevant follow-ups. If they said something vague — clarify that specific point.

**Confirm understanding.** After 3-5 questions, briefly summarize what you understood. Catches misunderstandings early.

**Help when stuck.** When user says "not sure" or "don't know":
1. Say it's OK
2. Offer 2-3 common approaches for their type of project
3. Ask which is closer
4. If still uncertain and optional — mark TBD, move on
5. If still uncertain and required — break into simpler sub-questions

**Recount on scope changes.** If user suddenly adds many features or reveals unexpected complexity — stop and recount total scope. Show the updated list, confirm you understood correctly.

**If code exists.** Launch `code-researcher` (Task tool, opus) with `feature_path = engagement/specs` in parallel with the interview; read `engagement/specs/code-research.md` to pre-fill technical decisions and ask more targeted questions.

**Save as you go.** Create `engagement/specs/project-brief.md` (shape in 2.4, `status: draft`) after the first answers and update it after every answer batch. The draft is the resume point: `agency-intake` step 0 resumes an interrupted interview from it.

## Phase 1: Project Discovery

### 1.1 Interview

Check `.claude/skills/project-knowledge/references/`. If it already holds real content: `project.md` and `architecture.md` both exist and `project.md` no longer holds the template's `[Project Name]` placeholder,
this is not a bootstrap: stop and return to `agency-intake` step 5c, which
routes a feature to 5c.1. A missing PK folder or `CLAUDE.md` is expected here; Part B creates them.

Ask user to describe the project in free form. Let them say as much or as little as they want.

Then ask adaptive questions to cover three areas:

**Project Overview:**
- What the project does (one-line + context)
- Who uses it and why (target audience + use case)
- What problem it solves (core pain point)
- 3-5 key features (high-level only)
- Scope boundaries (explicit exclusions)

**Features & MVP:**
- Key features with descriptions
- What's included in MVP (launch scope)
- What comes later (post-launch ideas) — note these for the backlog
- Priority for each: Critical / Important / Nice-to-have

**Development Approach:**
- All at once or phased?
- If phased: how to group features, what's MVP
- If migration: current system, data migration, risks, rollback plan

### 1.2 Checkpoint

Move to Phase 2 when you can:
- Write a clear, non-vague Overview section of the brief
- List key features with priorities and MVP scope
- Describe the development approach

TBD is acceptable for optional aspects.

## Phase 2: Technical Decisions

### 2.1 New Project (no code)

1. **Propose tech stack** based on Phase 1: frontend, backend, database, key dependencies
2. **Verify choices** against current docs (Context7 if available). Update if you find deprecations or better alternatives.
3. **Propose deployment:** platform, CI/CD approach, environments
4. **Present proposal** to user with rationale for each choice. Iterate until user approves.

### 2.2 Existing Code

1. **Extract stack** from `code-research.md` and the package files, configs and directory structure it points to
2. **Verify** against current docs (Context7 if available)
3. **Confirm with user:** show what you found, ask about gaps (deployment, missing pieces)
4. Iterate until confirmed.

### 2.3 Questions Part B and infrastructure need answered here

Nobody downstream can ask these, so close them now (an unknown optional item is TBD):
- **Default branch** and any branching rule the user already follows. The rest of the git
  workflow is the analyst's default.
- **Docker:** not needed / local dev / production / both.
- **Pre-commit strictness:** gitleaks only, or gitleaks plus lint/format of staged files.
- **Significant UI?** Decides whether `ux-guidelines.md` is written.
- **Backlog:** if post-launch features came up, where the backlog file lives (a repo-relative
  path), or "none".

### 2.4 Write the brief

`engagement/specs/project-brief.md`. Headings exactly as below (Part B and `dev-lead` find
sections by them); content in Russian, because the user approves it:

```markdown
---
project: {name}
status: draft            # approved after 2.5
approved: null           # {YYYY-MM-DD} after 2.5
has_code: {true | false}
---

# Project brief — {name}

## Overview
What it does, who uses it and why, the core problem, explicit exclusions.

## Features & MVP
| Feature | Description | Priority | MVP |
|---|---|---|---|

## Post-launch
Ideas for later, one per line; "none" if none came up.

## Development approach
All at once or phased; feature grouping; migration details if any.

## Tech stack
One line per layer: the choice, why, and the date it was checked against current docs.

## Deployment
Platform, CI/CD approach, environments.

## Infrastructure
Docker: ... Pre-commit: ...

## Git workflow
Default branch; any branching rule the user stated.

## UI
Significant UI: yes / no.

## Backlog
Repo-relative path of the backlog file, or "none".

## TBD
Optional items left open, each with what it touches. Required items never land here.
```

### 2.5 Checkpoint and approval

Show the brief to the user. Move on only when:
- Tech stack (frontend, backend, database, key dependencies) approved by user
- Deployment platform and CI/CD approach agreed
- Every item in 2.3 has an answer or a TBD the user accepted
- No required item is open

On approval set `status: approved` and `approved: {YYYY-MM-DD}`, then return to `agency-intake`
step 5c.0, which writes the `{name}-bootstrap` engagement's `criteria.md`. After approval the
brief is frozen: only the user changes it, and a gap found later comes back to them as a question.

---

# Part B: Documentation (inside the `{name}-bootstrap` engagement)

You work only from what is on disk. You never ask the user: the engine has no way to reach them.
A required fact missing from the brief (no stack, no deployment platform) is a `blocked` return
with `NEEDS_CONTEXT:` notes per `engagement-contract`, not a guess. An optional item marked TBD in the brief becomes an explicit
"TBD: not decided at bootstrap" line in the doc it belongs to.

**Where things are.** The engine runs this task in code mode, in your own git worktree. Write the
PK files, `CLAUDE.md` and the backlog inside the worktree. Read the brief and `code-research.md`
from the canonical engagement directory your prompt names (`{ENG}/specs/`, an absolute path that
is not inside the worktree).

Precondition: `{ENG}/specs/project-brief.md` has `status: approved`. If it does not, write
nothing and return `blocked` with that reason in `notes`.

## Phase 3: Fill Documentation

Documentation goal: someone opens these files and understands the project without reading code. Describe what exists, what it does, and why. Record decisions, operational details (server addresses, deploy procedures, log locations), high-level component overview. Write in prose, link to source files for code details. Each fact lives in one file only.

Use Edit tool to replace template placeholders with real content. Content language: English.

### 3.0 Scaffold

- If `.claude/skills/project-knowledge/` is missing, copy from
  `~/.claude/shared/templates/new-project/.claude/skills/project-knowledge/` into the repo at the
  same path: `SKILL.md` and `references/{project,architecture,patterns,deployment}.md`, plus
  `references/ux-guidelines.md` only when the brief says significant UI: yes. Copy file by file,
  not the directory: the engine commits every change in the worktree, but its reviewer reads only
  the task's declared files, so an untouched template would be committed unreviewed.
- If `CLAUDE.md` is missing, copy `~/.claude/shared/templates/new-project/CLAUDE.md` and fill the
  project name, the one-line description from the brief's Overview, the default branch from
  its Git workflow section, and the backlog path from its Backlog section ("none" if it names none).
- Copy nothing else from that template: `work/` is the retired layout, and `.gitignore` /
  `.env.example` belong to `infrastructure-setup`.

### 3.1 Project Knowledge Files

**project.md** — from the brief's Overview, Features & MVP, Post-launch and Development approach:
- Project overview, target audience, core problem
- Key features with priorities and MVP scope
- Post-launch ideas (if any)
- Out of scope

**architecture.md** — from the brief's Tech stack + `code-research.md` when the repo has code:
- Tech stack with "why" for each choice
- Project structure (directory tree)
- Key dependencies (only critical ones, not everything)
- External integrations
- Data flow
- Data model (fill if known, leave template sections if TBD)

**patterns.md** — fill git workflow section:
- Branch structure and default branch from the brief; branch decision criteria
- Testing requirements per branch
- Security gates (pre-commit, pre-push), matching the brief's Infrastructure section
- Anything the brief does not settle is your default, written as a decision with its reason
- Leave code patterns, testing methods, and business rules sections minimal — filled during development as patterns emerge

**deployment.md** — from the brief's Deployment section:
- Platform, type, rationale
- Deployment triggers (what deploys where)
- Environments and URLs
- Environment variables (reference .env.example)
- Monitoring: fill if configured, note "not yet configured" if not

**ux-guidelines.md** — only if the brief says significant UI: yes. Skip entirely for CLIs, APIs, bots without custom UI.

### 3.2 Backlog

If the brief's Backlog section names a path, write the Post-launch items there. "none" → skip.

### 3.3 Checkpoint

All output files from "Output Files" section created. No template placeholders remain.

## Phase 4: Verify & Report

### 4.1 Self-Verify

Before reporting, verify:
- project.md contains every feature in the brief's Features & MVP, with its priority and MVP flag
- architecture.md and deployment.md match the brief's Tech stack and Deployment sections
- every TBD in a doc traces to the brief's TBD section
- No template placeholders remain

Fix any issues before proceeding.

### 4.2 Documentation Review

Run `documentation-reviewer` agent (Task tool, sonnet) on your worktree, not the canonical repo: pass the absolute worktree root and the exact list of files you wrote (the canonical checkout does not have them until the wave merges). Fix critical and major findings. Minor findings — fix or leave at your discretion. This dispatch is a step of the method (`engagement-contract` §"spec-authoring methodologies"), so the lead does not schedule it again.

### 4.3 Report

Executor report per `engagement-contract`: the files created, the brief sections each one came
from, every default you chose where the brief was silent, and the `documentation-reviewer`
findings with what you did about each. Committing is the engine's job, and the user approves the
documentation at the engagement's acceptance gate, not in a chat with you.
