# Skills Ecosystem — full catalog

Loaded by `dev-methodology` when an agent needs to pick a specific skill
to load for a sub-task. Hot-path summary lives in
`dev-methodology/SKILL.md §"Skills Ecosystem"` — it points here for the
full per-category catalog.

The dev domain currently exposes the following methodology / quality /
execution skills. Each row is a one-line purpose statement; for the
detailed contract, load the skill's `SKILL.md` directly.

## Planning Skills
| Skill | Purpose |
|-------|---------|
| `project-planning` | New project: interview → project knowledge docs (project.md, architecture.md, etc.) |
| `feature-research` | Pre-filter: feasibility check, GO/NO-GO verdict → research-verdict.md |
| `user-spec-planning` | Feature requirements: interview → user-spec.md |
| `tech-spec-planning` | Architecture: research → tech-spec.md |
| `task-decomposition` | Decompose tech-spec into atomic task files |

## Execution Skills
| Skill | Purpose |
|-------|---------|
| `code-writing` | TDD cycle: plan → tests → code → review |
| `prompt-engineering` | LLM prompt engineering: write, improve, verify prompts |
| `feature-execution` | Team lead dispatches agents by wave; teammates commit own code, lead commits statuses |
| `pre-deploy-qa` | Pre-deploy acceptance testing: tests + acceptance criteria |
| `post-deploy-qa` | Post-deploy verification on live environment via MCP tools |

## Quality & Review Skills
| Skill | Purpose |
|-------|---------|
| `code-reviewing` | 11-dimension code review methodology (incl. Resource Management) |
| `security-auditing` | OWASP Top 10 security analysis |
| `testing-methodology` | Testing strategy: when to use which tests |

## Meta Skills
| Skill | Purpose |
|-------|---------|
| `dev-methodology` | This skill — how the process works |
| `documentation-writing` | Manage Project Knowledge files |
| `skill-authoring` | Create and maintain quality skills |
| `infrastructure-setup` | Framework init, Docker, pre-commit hooks, testing setup |
| `deploy-pipeline` | CI/CD pipelines, deployment config, automated deploy |
| `skill-test-design` | Design test scenarios for skills |
| `skill-testing` | Execute skill test scenarios |

## Agency Cross-Cutting Skills
| Skill | Purpose |
|-------|---------|
| `agency-intake` | Single entry point: classify domain, capture criteria, hand off to lead |
| `engagement-protocol` | Canonical contract for engagement/ artefacts |
| `acceptance-protocol` | Acceptor-only verdict methodology for directors |
| `validation-pipeline` | Cross-cutting validator contracts |
| `docs-pipeline` | Documentation artefacts across engagements |
