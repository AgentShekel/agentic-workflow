---
name: persistent-tasks-methodology
domain: dev
description: |
  [METHODOLOGY] Git-backed task management that survives context
  compaction (tasks as .md files in work/tasks/ with dependencies and statuses,
  auto-save context for post-compact recovery). Preloaded by
  dev-engineering-lead agent.
---

# Persistent Tasks

File-based task tracking that survives context resets. Alternative to TodoWrite for multi-session work.

## When to Use

- **TodoWrite** — single-session work, simple flat lists, will NOT survive compact
- **Persistent Tasks** — multi-session work, tasks with dependencies, must survive compact
- **task-decomposition skill** — when decomposing from tech-spec (creates task files in work/features/)

This skill is for ad-hoc task management outside the formal spec pipeline.

## Data Structure

```
work/tasks/
├── BACKLOG.md          — task index with statuses and dependencies
├── .claude-context.yml — auto-saved context for compact recovery
└── notes/              — optional notes/decisions per task group
```

## Task Format in BACKLOG.md

```markdown
# Tasks

## Active Sprint

- [x] TASK-1: Set up database schema
- [ ] TASK-2: Create API endpoints (blocked by: TASK-1)
  - [ ] TASK-2a: GET /users endpoint
  - [ ] TASK-2b: POST /users endpoint
- [ ] TASK-3: Frontend components (blocked by: TASK-2)
- [-] TASK-4: Write tests (in progress)

## Backlog

- [ ] TASK-5: Add caching layer
- [ ] TASK-6: Performance optimization

## Done

- [x] TASK-0: Project setup (completed 2026-03-28)
- [x] TASK-1: Set up database schema (completed 2026-03-29)
```

### Status markers
- `[ ]` — pending
- `[-]` — in progress
- `[x]` — completed
- `(blocked by: TASK-N)` — dependency declaration

## Workflow

### Phase 1: Initialize

Create `work/tasks/BACKLOG.md` if it doesn't exist.

```markdown
# Tasks

## Active Sprint

## Backlog

## Done
```

### Phase 2: Add Tasks

Add tasks to Active Sprint or Backlog. Rules:
- Each task gets an ID: TASK-{N} (sequential)
- Subtasks: indent with 2 spaces, ID = parent + letter (TASK-2a, TASK-2b)
- Dependencies: `(blocked by: TASK-N)` or `(blocked by: TASK-1, TASK-3)`
- Keep descriptions concise — one line per task

### Phase 3: Work on Tasks

1. Find next **ready** task — not blocked, not done
2. Mark as in-progress: `[-]`
3. Do the work
4. Mark as done: `[x]` + add completion date
5. Save context (Phase 5)

### Phase 4: Show Ready Tasks

Parse BACKLOG.md, resolve dependencies, show only unblocked tasks:

```
Ready tasks (not blocked):
  TASK-4: Write tests (in progress)
  TASK-5: Add caching layer
```

### Phase 5: Save Context (for compact recovery)

After each significant change, save context to `.claude-context.yml`:

```yaml
# Auto-saved by persistent-tasks-methodology skill
updated_at: "2026-04-01T14:30:00Z"
skill: persistent-tasks
backlog: work/tasks/BACKLOG.md
current_task: TASK-4
current_task_desc: Write tests for API endpoints
key_files:
  - backend/app/api/users.py
  - backend/tests/test_users.py
notes: |
  Working on unit tests for user CRUD.
  GET endpoint done, POST endpoint next.
```

The `post-compact-context.sh` hook will output this file after compaction, so Claude can resume.

## Integration

### With feature-execution

If working inside a feature (work/{feature}/), tasks go into the feature directory:
```
work/my-feature/
├── tasks/BACKLOG.md
├── tech-spec.md
└── ...
```

### With task-decomposition

Tasks from tech-spec decomposition create formal task files (tasks/*.md).
Persistent-tasks BACKLOG.md can reference them:
```
- [ ] TASK-3: Implement auth middleware → see tasks/003-auth-middleware.md
```

### Context save trigger

Save `.claude-context.yml` when:
- Completing a task
- Starting a new task
- Making significant progress on current task
- Before any operation that might trigger compact (large file reads, many tool calls)

## Self-Verification

- [ ] BACKLOG.md exists and has proper format
- [ ] No circular dependencies
- [ ] At most one task is `[-]` (in progress)
- [ ] Completed tasks have dates
- [ ] `.claude-context.yml` is up to date
