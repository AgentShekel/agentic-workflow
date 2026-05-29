# Dev Agents — full catalog

Loaded by `dev-methodology` when an agent needs to identify which
sibling agent to dispatch for a sub-task. Hot-path summary lives in
`dev-methodology/SKILL.md §"Agents"` — it points here for the full
per-role catalog.

Agents are isolated subprocesses with fresh context. They receive
input, do one job, return structured output.

## Dev Track Leadership
- `dev-director` — system-optimizer (out-of-band); does NOT accept engagements
- `dev-manager` — acceptor for dev-lead handoffs; writes accept/reject verdict (does not plan or execute)
- `dev-lead` — plans + dispatches; owns the engagement
- `dev-product-lead` — discovery track (planning, research, user-spec)
- `dev-engineering-lead` — delivery track (tech-spec, tasks, execution)
- `dev-quality-lead` — QA and review track (reviewers, security, pre/post-deploy)
- `dev-tech-architect` — tech-spec author + task decomposition

## Validators (run during spec/task creation)
- `userspec-quality-validator` — document quality and completeness
- `userspec-adequacy-validator` — solution feasibility
- `interview-completeness-checker` — interview coverage gaps
- `tech-spec-validator` — template compliance
- `skeptic` — detects mirages (non-existent files/functions/APIs)
- `completeness-validator` — bidirectional requirements traceability, over/underengineering, solution depth
- `task-validator` — task template compliance
- `task-creator` — generates task files from tech-spec
- `reality-checker` — validates tasks against codebase
- `feasibility-assessor` — validates feature research verdict (scope, risks, justification)

## Reviewers (run during/after code writing)
- `code-reviewer` — code quality across 10 dimensions
- `test-reviewer` — test quality analysis with concrete fixes
- `security-auditor` — OWASP Top 10, auth, input validation
- `performance-validator` — N+1 queries, memory leaks, O(n²), async anti-patterns
- `migration-validator` — DB migration safety: atomicity, rollback, data preservation
- `accessibility-validator` — WCAG AA: ARIA, contrast, keyboard nav, screen readers
- `prompt-reviewer` — prompt quality against prompt-engineering principles
- `documentation-reviewer` — project-knowledge quality (haiku model — template check)
- `deploy-reviewer` — CI/CD pipeline and deployment configuration (haiku model)
- `infrastructure-reviewer` — folder structure, Docker, pre-commit hooks, .gitignore (haiku model)

## Engineers (implementation)
- `dev-backend-engineer` — server-side (APIs, services, DB, background jobs)
- `dev-frontend-engineer` — client-side (UI components, state, routing)
- `dev-fullstack-engineer` — end-to-end features when split adds no value
- `dev-devops-engineer` — infrastructure + CI/CD
- `dev-technical-writer` — project-knowledge maintenance
- `dev-qa-engineer` — test strategy + plans

## Research
- `code-researcher` — codebase research for features (files, patterns, tests, integrations, risks)

## QA
- `pre-deploy-qa` — pre-deploy acceptance testing (tests + acceptance criteria)
- `post-deploy-qa` — post-deploy verification on live environment (MCP tools, AVP)

## Meta
- `skill-checker` — validates skills against skill-authoring standards
