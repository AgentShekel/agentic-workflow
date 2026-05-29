---
name: feature-research
domain: dev
description: |
  [METHODOLOGY] Feature pre-filter (codebase exploration, feasibility
  check, GO/NO-GO verdict) — runs before user-spec to prevent wasted effort.
  Preloaded by dev-product-analyst agent.
---

# Feature Research

Pre-filter step before `user-spec-planning`. Takes a rough feature idea, runs structured analysis, produces GO/NO-GO verdict. Prevents wasted effort on non-viable, misaligned, or duplicated features.

**Input:** Feature description (free text from user)
**Output:** `work/{feature}/research-verdict.md` + `work/{feature}/code-research.md`
**When to use:** Recommended for M/L features and unclear scope. Optional for obvious S features.

## Phase 1: Requirement Parsing

1. Accept feature description from user.
2. Extract structured requirements:
   - **What:** core functionality in 2-3 sentences
   - **Who for:** target users/roles
   - **Why:** business/user value
   - **Constraints:** known limitations, deadlines, dependencies
3. Detect ambiguities — list explicitly: "Unclear: [X]. Assuming [Y] — correct?"
4. Determine feature type: `new_feature` | `enhancement` | `bug_fix` | `refactoring` | `infrastructure`
5. Propose feature name (kebab-case), get user confirmation.
6. Run `~/.claude/shared/scripts/init-feature-folder.sh {name}` — creates folder structure.

**Checkpoint:** Feature folder exists, requirements parsed, ambiguities clarified.

## Phase 2: Project Context

1. Read all files from `.claude/skills/project-knowledge/references/`:
   - `project.md` — mission, scope, explicit exclusions
   - `architecture.md` — current architecture, components, patterns
   - `patterns.md` — code conventions, testing approach
   - `deployment.md` — deploy pipeline, infrastructure

   If directory missing or empty — warn user, note "no PK" in verdict.

2. Check for duplicates/overlaps:
   - Grep codebase for similar functionality keywords
   - Check `work/` and `work/completed/` for related features
   - If overlap found — report: "Found existing [X] in [path]. This feature overlaps/extends it."

3. Check mission alignment:
   - Is this feature within `project.md` scope?
   - Is it explicitly listed as out-of-scope or excluded?
   - If out-of-scope → immediate NO-GO candidate (still complete research, but flag it).

**Checkpoint:** PK read, duplicates checked, mission alignment assessed.

## Phase 3: Codebase Exploration

Launch `code-researcher` subagent (Task tool, opus) with feature path and feature description.

Subagent investigates:
- Existing implementations that can be reused
- Integration surface (which modules/files will be affected)
- Blast radius (how many files/components need changes)
- Technical constraints from code (undocumented limits, dependencies)

After subagent completes — read `{feature_path}/code-research.md`.

**Checkpoint:** code-research.md created, key findings noted.

## Phase 4: Feasibility Assessment

Based on PK files and code research, assess:

### 4.1 Mission Alignment
- Does this feature serve the project's stated purpose (from project.md)?
- Does it fit the target audience?
- Result: `aligned` | `partially_aligned` | `misaligned`

### 4.2 Architectural Fit
- Works with current architecture from architecture.md?
- Requires fundamental architectural changes?
- Result: `fits` | `needs_adaptation` | `needs_rearchitecture`

### 4.3 Complexity Classification

**Platform** — complex orchestration, event pipelines, multi-service coordination, new infrastructure. High complexity justified.

**Product** — user-facing features, standard CRUD/UI, straightforward integration. Simplicity enforced: adopt existing patterns > adapt > invent new.

**Mixed** — platform backend + product frontend. Specify per component.

Red flags:
- Applying platform complexity to a product feature
- Over-engineering simple requirements with unnecessary abstractions
- Confusing internal tooling needs with user-facing product needs

### 4.4 Effort Estimate
- **S** (1-3 files, 1-2 days): local fix, straightforward
- **M** (several components, 3-5 days): moderate integration
- **L** (new architecture, 5+ days): deep changes, multiple waves

Base estimate on code-research.md blast radius.

### 4.5 Risk Quick-Scan

**Top 3 technical risks:**
| Risk | Impact | Probability | Mitigation hint |
|------|--------|-------------|-----------------|

Categories to consider: scalability, performance, security, data integrity, integration, maintainability.

**Top 2 operational risks:**
| Risk | Impact | Probability | Mitigation hint |
|------|--------|-------------|-----------------|

Categories to consider: rollback difficulty, deployment risk, user adoption, external dependencies, operational complexity.

### 4.6 Dependencies
- External services/APIs needed
- New packages/libraries
- License considerations
- Other features that must be done first

**Checkpoint:** All assessment dimensions completed.

## Phase 5: Verdict

### 5.1 Produce verdict

Assemble findings into `work/{feature}/research-verdict.md`:

```markdown
---
created: YYYY-MM-DD
verdict: GO | NO-GO | CONDITIONAL | DEFER
feature: {feature-name}
type: {feature_type}
complexity: Platform | Product | Mixed
effort: S | M | L
---

# Feature Research: {Feature Name}

## Requirements
{Structured requirements from Phase 1}

## Verdict: {GO | NO-GO | CONDITIONAL | DEFER}
{1-3 sentence justification}

## Mission Alignment
{aligned | partially_aligned | misaligned} — {reasoning}

## Architectural Fit
{fits | needs_adaptation | needs_rearchitecture} — {reasoning}

## Complexity Classification
**Type:** {Platform | Product | Mixed}
{Justification}

## Effort Estimate
**Size:** {S | M | L}
- Files affected: ~{N}
- Components involved: {list}
- New dependencies: {list or "none"}

## Risks
### Technical
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|

### Operational
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|

## Dependencies
{List or "none"}

## Existing Code
{Key findings from code-research.md: reusable components, overlap, integration points}

## Recommendations
{Specific next steps based on verdict}
```

**Verdict rules:**
- **GO** — aligned, feasible, risks manageable. Proceed to `user-spec-planning`.
- **NO-GO** — misaligned with mission, fundamentally infeasible, or risks too high. Explain why, suggest alternatives if any.
- **CONDITIONAL** — viable but conditions must be met first. List conditions (e.g., "refactor module X first", "get API access", "wait for feature Y").
- **DEFER** — viable and aligned, but not now. Reason: dependency on another feature, timing, resource constraints.

### 5.2 Validate verdict

Launch `feasibility-assessor` subagent (sonnet) with `research-verdict.md` path and PK path. Single lightweight validator — checks:
- Verdict is justified by the evidence
- Risks identified and not overlooked
- Scope assessed against PK (not just gut feeling)
- No blind spots (common gaps: rollback plan, data migration, external service SLAs)

Report: `work/{feature}/logs/research/feasibility-review.json`

If findings → fix verdict, re-run validator (max 2 iterations).

### 5.3 Git commit
```
draft(research): feature research verdict for {feature}
```

### 5.4 User approval

Show verdict to user. Wait for explicit decision:
- **Approve GO** → hand off to `user-spec-planning` for {feature-name}
- **Approve NO-GO** → archive or delete feature folder
- **Override** → user can override verdict with reasoning (record in verdict file)
- **Request changes** → fix, re-validate

**Checkpoint:** Verdict produced, validated, approved by user.

## Self-Verification

- [ ] Requirements parsed and ambiguities clarified
- [ ] PK files read, mission alignment checked
- [ ] code-research.md produced by code-researcher
- [ ] All 6 assessment dimensions completed
- [ ] research-verdict.md created with all sections
- [ ] feasibility-assessor validated verdict
- [ ] User approved verdict
