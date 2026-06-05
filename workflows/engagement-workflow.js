export const meta = {
  name: 'engagement-workflow',
  description: 'General agency production cascade (data-driven, multi-wave with deps, per-task rework, per-wave consolidation w/ overlap-fallback, adversarial-verify). Stops at the handoff seam; LangGraph acceptance consumes engagement/ unchanged.',
  phases: [
    { title: 'discovery' }, { title: 'decompose' }, { title: 'deliver' },
    { title: 'validate' }, { title: 'handoff' }, { title: 'gate' },
  ],
}

// ---- params via args (defensive); tier/domain/ux come from the PLAN, not args ----
const A = (typeof args === 'string') ? JSON.parse(args) : (args || {})
// Production contract — the caller (agency lead / gate-runner) MUST supply these.
const REPO = A.repoDir        // absolute path to the project git repo
const SCRIPTS = A.scriptsDir  // absolute path to the agency scripts dir (handoff-precheck.py etc.)
const TS = A.ts               // UTC timestamp string "YYYYMMDDTHHMMSSZ" (Date.now is banned in-script)
if (!REPO || !SCRIPTS || !TS) {
  return { error: 'engagement-workflow requires args.repoDir, args.scriptsDir, args.ts', readyForAcceptance: false }
}
const ENG = A.engDir || (REPO + '/engagement')
const ITER = A.iterN || 1
// Optional planner-selector hint. When supplied, the lead:plan step runs as the
// domain's lead agent (agentType:'<domain>-lead') so that lead's planning doctrine
// applies. Absent -> the generic default planner runs (domain-agnostic; the safe
// path for any domain whose lead is not yet migrated to a planning agent). This
// ONLY selects WHO plans; the authoritative plan.domain is still derived by the
// planner from criteria.md.
const DOMAIN = A.domain
const SIBLING = REPO.replace(/\/[^/]+$/, '') // parent dir for sibling worktrees
const TIER_ITER_MAX = { S: 1, M: 2, L: 3 }
const NUMERICAL = ['accessibility-validator', 'performance-validator', 'security-auditor', 'ux-review', 'anti-pattern-detector']
const HANDOFF_SECTIONS = {
  S: ['## 1. Diff summary', '## 2. Deliverables (criteria-trace inline)', '## 5. Validation log', '## 7. Self-acceptance (>=1 concern, >=1 tagged [crit-N])'],
  M: ['## 1. Diff summary', '## 2. Deliverables', '## 3. Criteria trace', '## 4. Executor reports', '## 5. Validation log', '## 7. Self-acceptance (>=2 concerns, >=1 tagged [crit-N] or [scope-creep])', '## 8. Deploy', '## 11. Known deferrals'],
}
HANDOFF_SECTIONS.L = HANDOFF_SECTIONS.M

// ===========================================================================
// SCHEMAS
// ===========================================================================
const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['engagement', 'domain', 'tier', 'ux_heavy', 'deliverable_mode', 'specialists', 'validators', 'waves', 'tasks', 'decompose', 'notes'],
  properties: {
    engagement: { type: 'string' }, domain: { type: 'string' },
    tier: { type: 'string', enum: ['S', 'M', 'L'] }, ux_heavy: { type: 'string' },
    deliverable_mode: { type: 'string', enum: ['code', 'artefact'], description: 'code = git-mergeable source (worktree+octopus, repo tests); artefact = files written to engagement/ paths (no git, manifest-verify). dev=code; design/marketing=artefact unless they ship repo code.' },
    specialists: { type: 'array', items: { type: 'string' } },
    validators: { type: 'array', items: { type: 'string' }, description: 'validator agentTypes that apply to this engagement' },
    waves: { type: 'array', items: { type: 'array', items: { type: 'string' } }, description: 'ordered waves; wave N+1 may depend on wave N' },
    tasks: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'title', 'owner', 'files', 'crit_refs', 'depends_on'],
        properties: {
          id: { type: 'string' }, title: { type: 'string' }, owner: { type: 'string', description: 'specialist agentType' },
          files: { type: 'array', items: { type: 'string' }, description: 'repo-relative paths this task creates/edits (disjoint from same-wave peers)' },
          crit_refs: { type: 'array', items: { type: 'string' } },
          depends_on: { type: 'array', items: { type: 'string' }, description: 'task ids in earlier waves this needs' },
        },
      },
    },
    decompose: { type: 'boolean' }, notes: { type: 'string' },
  },
}
const SPEC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['task_id', 'branch', 'head_sha', 'files_touched', 'report_path', 'self_tests_pass', 'status', 'notes'],
  properties: {
    task_id: { type: 'string' }, branch: { type: 'string' }, head_sha: { type: 'string' },
    files_touched: { type: 'array', items: { type: 'string' } }, report_path: { type: 'string' },
    self_tests_pass: { type: 'boolean' }, status: { type: 'string', enum: ['done', 'blocked'] }, notes: { type: 'string' },
  },
}
const REVIEW_VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['verdict', 'findings', 'summary'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'rework'] },
    findings: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['severity', 'message'], properties: { severity: { type: 'string' }, file: { type: ['string', 'null'] }, message: { type: 'string' }, crit_ref: { type: ['string', 'null'] } } } },
    summary: { type: 'string' },
  },
}
const CONSOLIDATE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['merge_ok', 'conflicts', 'conflict_resolved', 'strategy', 'merge_head', 'tests_passed', 'test_output', 'notes'],
  properties: {
    merge_ok: { type: 'boolean' }, conflicts: { type: 'boolean' }, conflict_resolved: { type: 'boolean' },
    strategy: { type: 'string', description: 'octopus | sequential+resolve | fast-forward' },
    merge_head: { type: 'string' }, tests_passed: { type: 'boolean' }, test_output: { type: 'string' }, notes: { type: 'string' },
  },
}
const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['validator', 'status', 'summary', 'findings'],
  properties: {
    validator: { type: 'string' }, status: { type: 'string' }, summary: { type: 'string' }, methodology: { type: ['string', 'null'] },
    findings: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['severity', 'message'], properties: { severity: { type: 'string' }, message: { type: 'string' }, file: { type: ['string', 'null'] }, line: { type: ['integer', 'null'] }, fix: { type: ['string', 'null'] } } } },
  },
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['is_real', 'adjusted_severity', 'rationale'],
  properties: { is_real: { type: 'boolean' }, adjusted_severity: { type: 'string' }, rationale: { type: 'string' } },
}
const WRITER_SCHEMA = { type: 'object', additionalProperties: false, required: ['files_written', 'validation_log_written', 'notes'], properties: { files_written: { type: 'array', items: { type: 'string' } }, validation_log_written: { type: 'boolean' }, notes: { type: 'string' } } }
const HANDOFF_SCHEMA = { type: 'object', additionalProperties: false, required: ['handoff_written', 'sections_present', 'iteration_file_written', 'cited_paths_exist', 'notes'], properties: { handoff_written: { type: 'boolean' }, sections_present: { type: 'array', items: { type: 'string' } }, iteration_file_written: { type: 'boolean' }, cited_paths_exist: { type: 'boolean' }, notes: { type: 'string' } } }
const GATE_SCHEMA = { type: 'object', additionalProperties: false, required: ['precheck_pass', 'exit_code', 'checks', 'failures', 'raw_tail'], properties: { precheck_pass: { type: 'boolean' }, exit_code: { type: 'integer' }, checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['name', 'status'], properties: { name: { type: 'string' }, status: { type: 'string' }, detail: { type: ['string', 'null'] } } } }, failures: { type: 'array', items: { type: 'string' } }, raw_tail: { type: 'string' } } }

// ===========================================================================
// PHASE 1 — discovery: lead reads criteria.md, plans freely, returns roster.
// ===========================================================================
phase('discovery')
const planOpts = { label: 'lead:plan', phase: 'discovery', schema: PLAN_SCHEMA }
if (DOMAIN) planOpts.agentType = `${DOMAIN}-lead` // run planning as the domain's lead (its planning doctrine applies)
const plan = await agent(
  `You are the planning step of an agency engagement workflow. The SCRIPT orchestrates fan-out; you do NOT dispatch sub-agents. Read ${ENG}/criteria.md (Bash/Read) and plan the engagement from it — do NOT assume any particular task; derive everything from the criteria.

Decide and RETURN (and also WRITE ${ENG}/plan.md with matching YAML frontmatter — keys engagement, domain, tier, specialists, waves):
- engagement, domain (dev|design|marketing), tier (S|M|L), ux_heavy (true|false|minor) — from criteria frontmatter.
- specialists: the agentTypes that will do the work (e.g. dev-fullstack-engineer, dev-backend-engineer).
- validators: the validator agentTypes that apply (dev default: code-reviewer; add test-reviewer if tests are produced; security-auditor if auth/data; etc.).
- tasks: ATOMIC units. Each {id, title, owner (specialist agentType), files (repo-relative paths it creates/edits — MUST be disjoint from same-wave peers), crit_refs, depends_on (ids of earlier tasks it needs)}.
- waves: ordered groups of task ids. Tasks in the SAME wave run in parallel and MUST have disjoint files. A later wave may depend on an earlier one (put dependents in a later wave). Foundational/shared modules go in an earlier wave alone.
- decompose: true if tier L, or tier M with >=2 specialists.
- deliverable_mode: "code" if deliverables are git-mergeable source the project's repo will build/test (most dev); "artefact" if deliverables are files written under engagement/ that are not merged into repo code (design: brand/, ui/, screens/, tokens; marketing: copy, reports, banners). dev defaults to code; design/marketing default to artefact. In artefact mode each task's files are engagement-relative paths (e.g. ui/dashboard.html, copy/landing.md) and same-wave tasks still write DISJOINT paths.

Constraints: keep files within same wave strictly disjoint (code mode: parallel worktrees merge by octopus; artefact mode: distinct files, no merge). Avoid "slot N of M"/"last attempt"/"final round" language in plan.md. Return per schema.`,
  planOpts)
if (!plan) return { error: 'planning failed', readyForAcceptance: false }
const TIER = plan.tier || 'M'
const MODE = plan.deliverable_mode || (plan.domain === 'dev' ? 'code' : 'artefact') // code: worktree+octopus+tests; artefact: write-to-engagement+manifest
const MAX_ATTEMPTS = TIER_ITER_MAX[TIER] || 2
const tasksById = {}
plan.tasks.forEach(t => { tasksById[t.id] = t })
// Plan-graph validation — fail loud on a malformed plan BEFORE any delivery.
// Duplicate ids silently overwrite in tasksById; orphan tasks (not in any wave)
// never run; unknown/duplicate wave refs misroute. One upfront check, not per-wave.
{
  const ids = plan.tasks.map(t => t.id)
  const flatWaves = plan.waves.flat()
  const dupIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))]
  const dupWaveRefs = [...new Set(flatWaves.filter((id, i) => flatWaves.indexOf(id) !== i))]
  const unknownRefs = [...new Set(flatWaves.filter(id => !tasksById[id]))]
  const orphanTasks = ids.filter(id => !flatWaves.includes(id))
  const planErrs = []
  if (dupIds.length) planErrs.push(`duplicate task id(s): ${dupIds.join(', ')}`)
  if (dupWaveRefs.length) planErrs.push(`task(s) referenced in >1 wave: ${dupWaveRefs.join(', ')}`)
  if (unknownRefs.length) planErrs.push(`wave(s) cite unknown task id(s): ${unknownRefs.join(', ')}`)
  if (orphanTasks.length) planErrs.push(`task(s) never scheduled in any wave: ${orphanTasks.join(', ')}`)
  if (planErrs.length) return { error: `plan malformed — ${planErrs.join('; ')}`, engagementDir: ENG, domain: plan.domain, tier: TIER, gate: { precheck_pass: false, exit_code: null, failures: planErrs, checks: [] }, readyForAcceptance: false }
}
log(`plan: domain=${plan.domain} tier=${TIER}; ${plan.tasks.length} tasks across ${plan.waves.length} wave(s); validators=${plan.validators.join(',')}`)

// ===========================================================================
// PHASE 2 — decompose (gated)
// ===========================================================================
phase('decompose')
if (plan.decompose) {
  await agent(
    `Write atomic task files (Bash/Write). Create ${ENG}/tasks/ then one file per task:
${plan.tasks.map(t => `- ${ENG}/tasks/${t.id}.md : title "${t.title}", owner ${t.owner}, files ${t.files.join(', ')}, criteria ${t.crit_refs.join('/')}, depends_on ${JSON.stringify(t.depends_on)}; include "done-when" bullets.`).join('\n')}
- ${ENG}/tasks/INDEX.md : wave grouping ${JSON.stringify(plan.waves)}; one line per task (id + owner + crit_refs + depends_on).
Keep files short. Return {written:[paths]}.`,
    { label: 'lead:decompose', phase: 'decompose', schema: { type: 'object', additionalProperties: false, required: ['written'], properties: { written: { type: 'array', items: { type: 'string' } } } } })
}

// ===========================================================================
// PHASE 3 — deliver: sequential waves; parallel specialists per wave w/ per-task
// rework. MODE branches the mechanic:
//   code     — each task in its own git worktree off main (wave N+1 sees N's
//              merged work); per-wave octopus consolidation (overlap fallback
//              w/ resolver) + repo tests. (dev)
//   artefact — each task writes deliverable files to disjoint engagement/ paths
//              (no git); per-wave manifest-verify (exist & non-empty). Deps work
//              because wave N+1 reads engagement/ where N's artefacts already are.
//              (design / marketing)
// ===========================================================================
phase('deliver')
function wt(t) { return `${SIBLING}/wt_${t.id}` }
function br(t) { return `wf_${t.id}` }

function implPrompt(t, attempt) {
  const deps = (t.depends_on && t.depends_on.length)
    ? `\nThis task DEPENDS ON earlier work already merged into main: ${t.depends_on.join(', ')}. Your worktree (branched off main) already contains those files — import/use them; do NOT recreate them.` : ''
  return `You are a dev specialist implementing ONE atomic task in your OWN git worktree. Use \`git -C <abs>\` + absolute paths; do NOT cd into shared dirs.

Task ${t.id}: ${t.title}
Repo ${REPO} (integration branch: main). Worktree ${wt(t)}. Branch ${br(t)}.
Files YOU create/edit (disjoint from same-wave peers): ${t.files.join(', ')}. Criteria: ${t.crit_refs.join(', ')}.${deps}

Steps:
1. Provision worktree off the CURRENT integration HEAD: git -C ${REPO} worktree add -b ${br(t)} ${wt(t)} main  (retry once after sleep 2 on lock error; if it already exists from a prior attempt, skip).
2. Implement your files INSIDE ${wt(t)}/. Standard library ONLY unless criteria allow deps. Follow the criteria contract LITERALLY (exact body shapes/keys). Tests = stdlib unittest importable from repo root.
3. Run your own tests: python -m unittest discover -s ${wt(t)}/tests -t ${wt(t)} (or py -3). Capture pass/fail.
4. Commit: git -C ${wt(t)} add -A && git -C ${wt(t)} commit -m '${t.id}: ${t.title} (attempt ${attempt})'
5. head_sha = git -C ${wt(t)} rev-parse HEAD
6. Write/refresh executor-report at CANONICAL ${ENG}/executor-reports/${t.id}.md (absolute, NOT in worktree). MUST open with "## Criteria acknowledgement" then one bullet per criterion naming the crit id. Then "## Work". No slot/last-attempt language.
Return per schema.`
}
function reviewTaskPrompt(t, spec) {
  return `You are code-reviewer doing a SCOPED per-task review inside the delivery loop. Review ONLY task ${t.id}'s files in worktree ${wt(t)}, judged against the cited criteria — passing tests is NOT sufficient; the implementation MUST match the criteria contract literally (exact keys/shapes/status codes).
Read: ${t.files.map(f => wt(t) + '/' + f).join(' , ')} and ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}). Specialist report ${spec.report_path}, self_tests_pass=${spec.self_tests_pass}.
Return per schema: verdict ('pass' if all cited criteria literally satisfied else 'rework'), findings[] (severity/file/message/crit_ref), summary.`
}
function reworkPrompt(t, review, attempt) {
  return `You are the SAME dev specialist reworking task ${t.id} in worktree ${wt(t)} (branch ${br(t)}) after a scoped review returned 'rework'. Address EVERY finding so cited criteria are LITERALLY satisfied. Fix BOTH implementation AND its test if needed. Re-run python -m unittest for your test (confirm green). Commit: git -C ${wt(t)} add -A && git -C ${wt(t)} commit -m '${t.id}: rework attempt ${attempt}'. Append "## Rework attempt ${attempt}" to ${ENG}/executor-reports/${t.id}.md.
Review findings: ${JSON.stringify(review.findings)}
Return per schema (head_sha=new HEAD).`
}

// ---- artefact mode (design / marketing): write deliverables to engagement/ paths, no git, critique review ----
function artefactImplPrompt(t, attempt) {
  const deps = (t.depends_on && t.depends_on.length)
    ? `\nThis task DEPENDS ON earlier deliverables already written under ${ENG}: ${t.depends_on.join(', ')}. Read and build on them; do NOT recreate them.` : ''
  return `You are a ${plan.domain} specialist producing ONE atomic deliverable as ARTEFACT files (no code build, no git). Write directly under the engagement dir using Bash/Write + absolute paths.

Task ${t.id}: ${t.title}
Engagement ${ENG}. Files YOU create (engagement-relative, DISJOINT from same-wave peers): ${t.files.join(', ')}. Criteria: ${t.crit_refs.join(', ')}.${deps}

Steps:
1. Produce each deliverable at ${ENG}/<file>. Satisfy the criteria contract LITERALLY (exact sections / values / copy the criteria name). For VISUAL artefacts follow the project's Codex-default creative direction (codex-bridge); Claude assembles / specs / QAs.
2. Write/refresh executor-report at ${ENG}/executor-reports/${t.id}.md. MUST open with "## Criteria acknowledgement" then one bullet per criterion naming the crit id. Then "## Work". No slot/last-attempt language.
Return per schema: task_id, branch="" , head_sha="" , files_touched (the engagement-relative paths you wrote), report_path, self_tests_pass (true if the deliverable meets its own done-when), status ('done'|'blocked'), notes.`
}
function artefactReviewPrompt(t, spec) {
  return `You are a ${plan.domain} critique reviewer doing a SCOPED per-task review inside the delivery loop. Judge ONLY task ${t.id}'s artefact(s) against the cited criteria — "the file exists" is NOT sufficient; the deliverable MUST satisfy the criteria contract. Apply the right lens: design -> critique / design-review (intent, hierarchy, token / brand consistency, a11y basics); marketing -> reality-check every claim + brand-voice fit.
Read: ${t.files.map(f => ENG + '/' + f).join(' , ')} and ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}). Specialist report ${spec.report_path}.
Return per schema: verdict ('pass' if all cited criteria satisfied else 'rework'), findings[] (severity/file/message/crit_ref), summary.`
}
function artefactReworkPrompt(t, review, attempt) {
  return `You are the SAME ${plan.domain} specialist reworking task ${t.id}'s artefact(s) under ${ENG} after a scoped critique returned 'rework'. Address EVERY finding so the cited criteria are satisfied. Rewrite the file(s) in place. Append "## Rework attempt ${attempt}" to ${ENG}/executor-reports/${t.id}.md.
Review findings: ${JSON.stringify(review.findings)}
Return per schema (branch="" , head_sha="" , files_touched = the paths).`
}
// A task that never produced a spec (impl agent returned nothing) is BLOCKED,
// not absent — surface it so the wave guard hard-stops instead of silently
// dropping the task on the downstream `.filter(Boolean)`.
function blockedSpec(t, reason) {
  return { task_id: t.id, status: 'blocked', branch: '', head_sha: '', files_touched: [], report_path: '', self_tests_pass: false, notes: reason, review_trail: ['impl-failed'], review_ok: false }
}
async function deliverArtefactTask(t) {
  let spec = await agent(artefactImplPrompt(t, 1), { label: `impl:${t.id}#1`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
  if (!spec) return blockedSpec(t, 'artefact implementation agent returned no result')
  const trail = []
  let review_ok = false
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const review = await agent(artefactReviewPrompt(t, spec), { label: `review:${t.id}#${attempt}`, phase: 'deliver', schema: REVIEW_VERDICT_SCHEMA })
    trail.push(review ? review.verdict : 'error')
    if (review && review.verdict === 'pass') { review_ok = true; break }
    if (!review) break  // review agent FAILED (null) — do NOT treat as pass; wave guard hard-stops on review_ok=false
    if (attempt === MAX_ATTEMPTS) break  // rework budget exhausted still on 'rework' — review_ok stays false
    const reworked = await agent(artefactReworkPrompt(t, review, attempt + 1), { label: `rework:${t.id}#${attempt + 1}`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
    if (!reworked) break
    spec = reworked
  }
  return { ...spec, review_trail: trail, review_ok }
}
async function deliverOneTask(t) {
  let spec = await agent(implPrompt(t, 1), { label: `impl:${t.id}#1`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
  if (!spec) return blockedSpec(t, 'implementation agent returned no result')
  const trail = []
  let review_ok = false
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const review = await agent(reviewTaskPrompt(t, spec), { label: `review:${t.id}#${attempt}`, phase: 'deliver', agentType: 'code-reviewer', schema: REVIEW_VERDICT_SCHEMA })
    trail.push(review ? review.verdict : 'error')
    if (review && review.verdict === 'pass') { review_ok = true; break }
    if (!review) break  // review agent FAILED (null) — do NOT treat as pass; wave guard hard-stops on review_ok=false
    if (attempt === MAX_ATTEMPTS) break  // rework budget exhausted still on 'rework' — review_ok stays false
    const reworked = await agent(reworkPrompt(t, review, attempt + 1), { label: `rework:${t.id}#${attempt + 1}`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
    if (!reworked) break
    spec = reworked
  }
  return { ...spec, review_trail: trail, review_ok }
}

const allSpecs = []
const waveSummaries = []
for (let wi = 0; wi < plan.waves.length; wi++) {
  const waveTasks = plan.waves[wi].map(id => tasksById[id])  // refs validated upfront
  if (!waveTasks.length) continue
  log(`deliver wave ${wi + 1}/${plan.waves.length}: ${waveTasks.map(t => t.id).join(', ')}`)
  const specs = (await parallel(waveTasks.map(t => () => (MODE === 'code' ? deliverOneTask(t) : deliverArtefactTask(t))))).filter(Boolean)
  allSpecs.push(...specs)
  // Pre-consolidation HARD-STOP: never merge/manifest a wave that (a) lost a task
  // to a thrown thunk (parallel() turns a throw into null -> filtered out), (b) has
  // a blocked task, or (c) has a task that did not genuinely pass review (review_ok
  // =false covers null/error review AND rework-budget exhausted on 'rework'). Later
  // waves depend on this one, so proceeding past a broken wave is wrong. Worktrees
  // are PRESERVED for resume (resumeFromRunId reuses them); cleanupCommands let a
  // fresh rerun clear failed state instead of silently reusing it.
  const dropped = waveTasks.length - specs.length
  const bad = specs.filter(s => s.status === 'blocked' || s.review_ok === false)
  if (dropped > 0 || bad.length) {
    const reasons = []
    if (dropped > 0) reasons.push(`${dropped} task(s) crashed (no spec returned)`)
    if (bad.length) reasons.push(`blocked/review-failed: ${bad.map(s => `${s.task_id}[${s.status === 'blocked' ? 'blocked' : 'review:' + (s.review_trail || []).join('>')}]`).join(', ')}`)
    log(`deliver wave ${wi + 1} HARD-STOP: ${reasons.join('; ')}`)
    return {
      error: `deliver wave ${wi + 1} did not cleanly complete — ${reasons.join('; ')}. No consolidation; fix and resume (resumeFromRunId), or clean worktrees first.`,
      engagementDir: ENG, domain: plan.domain, tier: TIER,
      deliver: allSpecs.map(s => ({ id: s.task_id, status: s.status, review_trail: s.review_trail, review_ok: s.review_ok })),
      cleanupCommands: (MODE === 'code') ? waveTasks.map(t => `git -C ${REPO} worktree remove --force ${wt(t)}`) : [],
      gate: { precheck_pass: false, exit_code: null, failures: [`deliver-wave-${wi + 1}-incomplete`], checks: [] },
      readyForAcceptance: false,
    }
  }
  const cons = (MODE === 'code')
    ? await agent(
      `Wave-barrier CONSOLIDATOR for repo ${REPO}, wave ${wi + 1}. Merge these branches into main (they branched off main; same-wave files are disjoint so octopus should be clean):
${JSON.stringify(specs.map(s => ({ task: s.task_id, branch: s.branch, head: s.head_sha })), null, 2)}
Steps (Bash, capture raw):
1. git -C ${REPO} checkout main
2. FAST PATH — octopus: git -C ${REPO} merge --no-ff -m 'consolidate wave ${wi + 1}' ${specs.map(s => s.branch).join(' ')}
3. If step 2 fails / refuses ("Should not be doing an octopus" or a CONFLICT): git -C ${REPO} merge --abort, then FALLBACK — merge branches ONE AT A TIME (git -C ${REPO} merge --no-ff <branch>). On a conflict, RESOLVE it by reconciling BOTH task intents (read the conflicting hunks + the task list), then git add + commit. Set conflict_resolved=true, strategy='sequential+resolve'.
4. Run repo-root tests: python -m unittest discover -s ${REPO}/tests -t ${REPO} (or py -3). Capture output + pass/fail.
5. merge_head = git -C ${REPO} rev-parse HEAD ; then remove this wave's worktrees + prune:
   ${waveTasks.map(t => `git -C ${REPO} worktree remove --force ${wt(t)}`).join('\n   ')}
   git -C ${REPO} worktree prune
Return per schema: merge_ok, conflicts (any seen), conflict_resolved, strategy, merge_head, tests_passed, test_output (trimmed), notes.`,
      { label: `consolidate:w${wi + 1}`, phase: 'deliver', schema: CONSOLIDATE_SCHEMA })
    : await agent(
      `Wave-barrier MANIFEST-VERIFY for ${plan.domain} ARTEFACT deliverables, wave ${wi + 1}. There is NO git merge — artefacts are distinct files written under ${ENG}. Verify each task's files exist and are non-empty:
${JSON.stringify(specs.map(s => ({ task: s.task_id, files: s.files_touched })), null, 2)}
Steps (Bash): for EACH file run \`test -s ${ENG}/<file> && echo OK <file> || echo MISSING <file>\` (exists AND non-empty). Then \`ls -la\` the touched paths for the listing.
Return per schema: merge_ok (true iff ALL files exist and are non-empty), conflicts:false, conflict_resolved:false, strategy:'artefact-manifest', merge_head:"" , tests_passed (same as merge_ok — all artefacts present & non-empty), test_output (the OK/MISSING lines + ls, trimmed), notes (name any MISSING / empty file).`,
      { label: `manifest:w${wi + 1}`, phase: 'deliver', schema: CONSOLIDATE_SCHEMA })
  waveSummaries.push({ wave: wi + 1, tasks: waveTasks.map(t => t.id), merge_ok: cons && cons.merge_ok, strategy: cons && cons.strategy, tests: cons && cons.tests_passed })
  log(`wave ${wi + 1} consolidated: ok=${cons && cons.merge_ok} strategy=${cons && cons.strategy} tests=${cons && cons.tests_passed}`)
}

// ===========================================================================
// PHASE 4 — validate: plan.validators review -> adversarial-verify each finding.
// ===========================================================================
phase('validate')
const VALIDATORS = (plan.validators && plan.validators.length) ? plan.validators : ['code-reviewer']
const reviewTarget = (MODE === 'code')
  ? `the consolidated work in repo ${REPO} (HEAD on main)`
  : `the delivered artefacts under ${ENG} (the files the specialists wrote — this is an artefact engagement: no git repo, no HEAD)`
const verifyReadLoc = (MODE === 'code') ? REPO : ENG
const verifiedResults = await pipeline(
  VALIDATORS,
  (v) => agent(
    `You are ${v}. Review ${reviewTarget} against ${ENG}/criteria.md. Read the relevant files. Return findings per schema: validator="${v}", status (approved|approved_with_suggestions|changes_required|blocked), summary, methodology (null unless a formal standard like WCAG/OWASP applies), findings[] (severity critical|high|medium|low|info / message / file / line / fix).`,
    { label: `validate:${v}`, phase: 'validate', agentType: v, schema: FINDINGS_SCHEMA }),
  (review, v) => {
    if (!review) return null
    const issues = (review.findings || []).filter(f => String(f.severity).toLowerCase() !== 'info')
    if (!issues.length) return { ...review, verified: [] }
    return parallel(issues.map((f, i) => () =>
      agent(`Independently and adversarially verify ONE validator finding — try to REFUTE it; default is_real=false if it is noise/non-issue/unsupported. Read the cited file under ${verifyReadLoc}.
Validator: ${v}. Finding: ${JSON.stringify(f)}. Criteria: ${ENG}/criteria.md.
Return per schema: is_real, adjusted_severity, rationale.`,
        { label: `verify:${v}#${i}`, phase: 'validate', schema: VERDICT_SCHEMA }).then(verdict => ({ finding: f, verdict }))
    )).then(checks => ({ ...review, verified: checks.filter(Boolean) }))
  })
const vals = verifiedResults.filter(Boolean)
const checked = vals.reduce((n, r) => n + (r.verified ? r.verified.length : 0), 0)
const confirmed = vals.reduce((n, r) => n + (r.verified ? r.verified.filter(x => x.verdict && x.verdict.is_real).length : 0), 0)
log(`validate: ${vals.length} validators; adversarial-verify ${confirmed}/${checked} confirmed`)

const writer = await agent(
  `Write validator proof-of-run files in the EXACT on-disk format handoff-precheck + manager read (Bash/Write).
For EACH validator result: FINAL findings = (severity=="info" findings) PLUS (verified findings where verdict.is_real==true; use verdict.adjusted_severity); DROP refuted (is_real==false).
Write ${ENG}/validation-outputs/{validator}-iter-${ITER}-${TS}.json = json.dumps(payload, ensure_ascii=False, indent=2), payload =
{ "validator","status","summary","methodology",
  "findings": [ {"severity","message","file","line","fix"} ],            // FINAL list
  "adversarial_verification": {"checked":N,"confirmed":M,"refuted":K},
  "canonical": { "schema_version":"1.0","validator":"<name>",
    "validator_type":"judgement",   // "numerical" only if name in ${JSON.stringify(NUMERICAL)}
    "verdict":"<approved_with_suggestions->approved_with_caveats; approved->approved; changes_required->changes_required; blocked->blocked>",
    "summary","methodology",
    "findings":[ {"id":"<name>#<idx>","severity","category":null,"issue":"<message>","fix":null|str,"evidence":null,"location":null|file} ],  // FINAL list
    "metrics":null } }
Also write ${ENG}/validation-log.md with one "### <validator>" (lowercase) block each: verdict line, "adversarial-verify: <M> confirmed / <K> refuted of <N>", one-line summary, output: path.
Validator results WITH verdicts: ${JSON.stringify(vals, null, 2)}
Return per schema.`,
  { label: 'validation-writer', phase: 'validate', schema: WRITER_SCHEMA })
log(`validation-outputs: ${writer ? writer.files_written.length : 0} files`)

// ===========================================================================
// PHASE 5 — handoff (tier-aware sections)
// ===========================================================================
phase('handoff')
const sections = HANDOFF_SECTIONS[TIER] || HANDOFF_SECTIONS.M
const pathWord = (MODE === 'code') ? 'code paths' : 'artefact paths'
const diffGuidance = (MODE === 'code')
  ? `diff base = the repo's initial commit (run git -C ${REPO} log --oneline | tail -1 for it, or git -C ${REPO} diff --stat <root>..HEAD).`
  : `§1 Diff = a FILE MANIFEST of the artefacts created/modified under ${ENG} (Bash: ls -la the deliverable paths; mark created vs modified). There is NO git diff — this is an artefact engagement, so do not run git diff. CITE EVERY artefact deliverable ENGAGEMENT-ROOTED, e.g. \`engagement/design-system/tokens.json\` or \`engagement/copy/landing.md\` — NOT bare \`design-system/tokens.json\`. The path-checker only existence-verifies engagement-rooted paths; a bare artefact root (ui/, brand/, copy/, reports/, …) is silently skipped, so a bare citation would pass unchecked.`
const handoff = await agent(
  `Assemble the engagement HANDOFF for a ${plan.domain} ${TIER}-tier engagement, then STOP (human gate is downstream). Use Bash/Write/Read. All cited ${pathWord} MUST exist.
CITATION RULE: cite ONLY bare file paths in backticks (e.g. \`tests/x.py\`). NEVER write \`path::testname\` or \`path:line\` as a backticked token (path-checker fails it). Name tests in prose, path separate.

Context: ${MODE === 'code' ? `repo ${REPO} (HEAD main = all waves merged)` : `base ${REPO} (artefacts under the engagement dir)`}. engagement ${ENG}. criteria ${ENG}/criteria.md. executor-reports in ${ENG}/executor-reports/. validation-log + validation-outputs written. Waves delivered: ${JSON.stringify(waveSummaries)}. ${diffGuidance}

Write ${ENG}/handoff.md with EXACTLY these sections (headings regex-checked; ${TIER}-tier):
${sections.join('\n')}
${plan.ux_heavy && plan.ux_heavy !== 'false' ? '## 6. Exercised (required for ux_heavy)\n' : ''}For §7 use format "1. [crit-N] concern: body"; non-criteria concerns capped at 1. Do NOT include the literal token "src/". No slot/last-attempt language.
Also write ${ENG}/iteration containing exactly: ${ITER}
SELF-CHECK: run python ${SCRIPTS}/handoff-paths-check.py ${ENG}/handoff.md --json and confirm status=pass; fix any missing-path citation per the CITATION RULE and rewrite until it passes. Return per schema.`,
  { label: 'lead:handoff', phase: 'handoff', schema: HANDOFF_SCHEMA })
log(`handoff: written=${handoff && handoff.handoff_written} paths_ok=${handoff && handoff.cited_paths_exist}`)

// ===========================================================================
// PHASE 6 — gate
// ===========================================================================
phase('gate')
const gate = await agent(
  `You are the gate-runner. Run EXACTLY (Bash, capture stdout + exit code): python ${SCRIPTS}/handoff-precheck.py ${ENG} --json --mode ready  (if "python" missing try "py -3 ..."). Parse the JSON.
Return per schema: precheck_pass=(exit_code==0), exit_code, checks=[{name,status,detail}], failures=[names with status=="fail"], raw_tail=last ~600 chars.`,
  { label: 'gate-runner', phase: 'gate', schema: GATE_SCHEMA })

// ---- SEAM ----
return {
  engagementDir: ENG, engagement: plan.engagement, domain: plan.domain, tier: TIER,
  waves: waveSummaries,
  deliver: allSpecs.map(s => ({ id: s.task_id, review_trail: s.review_trail, self_tests_pass: s.self_tests_pass })),
  adversarial_verify: { checked, confirmed, refuted: checked - confirmed },
  validation_files: writer ? writer.files_written : [],
  gate: gate ? { precheck_pass: gate.precheck_pass, exit_code: gate.exit_code, failures: gate.failures } : null,
  gate_full: gate || null,
  readyForAcceptance: !!(gate && gate.precheck_pass),
}
