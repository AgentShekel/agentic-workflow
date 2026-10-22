---
name: deploy-pipeline
domain: dev
description: |
  [METHODOLOGY] CI/CD pipeline setup, deployment configuration,
  automated deploy workflows (GitHub Actions, Vercel, Railway, Fly.io, AWS,
  VPS), secrets management in CI. Preloaded by dev-devops-engineer agent.
---

# Deploy Pipeline

## Gathering Deployment Context

Read project-knowledge to understand the deployment target:
- `.claude/skills/project-knowledge/references/deployment.md`
- `.claude/skills/project-knowledge/references/architecture.md`
- `.claude/skills/project-knowledge/references/patterns.md`

Inside an engagement also read `engagement/criteria.md` and, when they exist, the specs in the
canonical engagement directory your prompt names (`{ENG}/specs/project-brief.md` §Deployment,
`{ENG}/specs/tech-spec.md`), not copies in your worktree. If the PK files lack it, search the
other project-knowledge references too: the fact may live under another name.

The facts this skill needs come in three kinds:
- Target platform (Vercel, Railway, Fly.io, AWS ECS, VPS, NPM, Chrome Web Store)
- Environment details (URLs, project/service IDs, server access)
- Required secrets and where to obtain them

**Inside an engagement you cannot reach the user.** Job layout, triggers, skip logic, caching and
the deploy job's shape are yours: decide and record the ruling (`engagement-contract` §"Rule, do
not stall"). The three facts above are not: when no source on disk names one, never put a guessed
platform, URL, ID or address into a workflow or a doc.
- If the task's done-when does not need the missing fact (it asks for CI, not deploy), deliver the
  rest, leave the deploy job out per §Decision Framework, and list the missing fact in your report.
- If the done-when needs it, write nothing for that part and return `blocked` with `notes`
  starting `NEEDS_CONTEXT:`, naming the fact and the files you checked.

Outside an engagement (the user invoked you directly), ask the user for the missing facts.

Whatever you learn, write it into `deployment.md` with its source before proceeding with setup.

**Writing the pipeline is the task; running it is not.** Inside an engagement commit only as your
task prompt says (the engine merges locally) and never push to any remote, run a deploy, trigger
a workflow run or touch a server. Anything that leaves the machine is the human's step after
acceptance: list those steps in your report. Outside an engagement, push to main or production
only after the user says yes; deploys go through CI/CD either way.

## CI/CD Convention

Create `.github/workflows/ci.yml` following this structure:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check-skip:
    runs-on: ubuntu-latest
    outputs:
      should_skip: ${{ steps.check.outputs.should_skip }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - id: check
        run: |
          FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD)
          if echo "$FILES" | grep -vqE '\.(md|txt)$|^\.claude/|^\.spec/|^docs/'; then
            echo "should_skip=false" >> $GITHUB_OUTPUT
          else
            echo "should_skip=true" >> $GITHUB_OUTPUT
          fi

  test:
    needs: check-skip
    if: needs.check-skip.outputs.should_skip != 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # setup, install, lint, type-check, test, build

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # platform-specific deploy action
```

Adapt: add language setup, install steps, platform-specific deploy action.

## Platform Selection

| Platform | Choose when |
|----------|------------|
| Vercel | Next.js, React, static sites, serverless |
| Railway | Full-stack apps needing managed DB |
| Fly.io | Docker containers, global edge |
| AWS ECS | Enterprise, full infrastructure control |
| Custom VPS | Persistent sessions, multi-device |
| NPM | Node.js packages or CLI tools |
| Chrome Web Store | Browser extensions |

For VPS deployments: server-specific details (IPs, SSH keys, paths) go to `deployment.md`.

## Secrets Convention

Document all required secrets in `.claude/skills/project-knowledge/references/deployment.md`. For each secret:
- Name (GitHub Actions key)
- Where to obtain value (dashboard URL or CLI command)
- Which workflow uses it

Adding secret values in the repository settings is the user's step, never yours: name each
secret and where it goes in `deployment.md` and, inside an engagement, in your report, which
reaches the user through the handoff. Never ask for a value or write one anywhere. Create
`.env.example` with application-level variable names.

## Documentation Updates

After configuring, update project-knowledge references. Append to existing content.

**deployment.md:** deploy target, pipeline overview, required secrets table, manual deploy command, rollback steps.

**patterns.md (Git Workflow section):** CI triggers, pipeline jobs, skip logic pattern, PR workflow.

## Decision Framework

**Add deploy job?**
YES if: deployment target defined, `criteria.md` or the user asks for it, stable default branch (per the brief or `patterns.md`).
NO if: early development, manual deploys preferred, manual review step needed (Chrome Web Store).

**Use matrix strategy?**
YES if: NPM package, cross-platform library.
NO if: single-environment app, internal tool.

**Add staging?**
YES if: dev branch exists, multi-developer team.
NO if: solo + main-only, Vercel preview deploys sufficient.
