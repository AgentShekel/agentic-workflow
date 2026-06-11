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
// Reject backslash repoDir. SIBLING = REPO.replace(/\/[^/]+$/,'') assumes forward slashes;
// a Windows-style backslash path would silently nest every worktree INSIDE the repo. This is
// validation-not-transformation — it fires ONLY on an already-invalid input, so every valid
// (forward-slash) repoDir renders byte-identically (no flag needed; same class as the guard above).
if (REPO.includes('\\')) {
  return { error: 'repoDir must use forward slashes (git rev-parse --show-toplevel format), not backslashes — a backslash path nests worktrees inside the repo', readyForAcceptance: false }
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
    // `assertion_ref` is the ONE unconditional contract delta: an optional, nullable field so a
    // review finding may cite the co-signed contract assertion it maps to. Absent/null when
    // there is no contract (flag off) — additionalProperties:false requires it be declared
    // here for agents to be allowed to return it, but it never changes flag-off behaviour.
    findings: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['severity', 'message'], properties: { severity: { type: 'string' }, file: { type: ['string', 'null'] }, message: { type: 'string' }, crit_ref: { type: ['string', 'null'] }, assertion_ref: { type: ['string', 'null'] } } } },
    summary: { type: 'string' },
  },
}
// ---- Per-task contract handshake schemas (used only when A.contracts === true) ----
const CONTRACT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['assertions'],
  properties: {
    assertions: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['id', 'crit_ref', 'assertion', 'check_how', 'status'],
        properties: {
          id: { type: 'string' }, crit_ref: { type: 'string', description: 'the crit-N parent this assertion derives from (parentless = scope-creep)' },
          assertion: { type: 'string', description: 'one concrete, checkable claim of done-ness' },
          check_how: { type: 'string', description: 'how to verify it (drive script / command / inspection)' },
          status: { type: 'string', enum: ['agreed', 'contested'] },
        },
      },
    },
  },
}
const CONTEST_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['contested', 'rationale'],
  properties: { contested: { type: 'array', items: { type: 'string' } }, rationale: { type: 'string' } },
}
// ---- Bounded replan hatch (used only when A.replan === true) ----
const REPLAN_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['waves', 'tasks', 'reason'],
  properties: {
    waves: { type: 'array', items: { type: 'array', items: { type: 'string' } }, description: 'NEW remaining waves only (completed waves are locked, not repeated)' },
    tasks: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['id', 'title', 'owner', 'files', 'crit_refs', 'depends_on'],
        properties: { id: { type: 'string' }, title: { type: 'string' }, owner: { type: 'string' }, files: { type: 'array', items: { type: 'string' } }, crit_refs: { type: 'array', items: { type: 'string' } }, depends_on: { type: 'array', items: { type: 'string' } } },
      },
    },
    reason: { type: 'string' },
  },
}
// ---- Artefact render-eval findings (used only when A.renderEval === true) ----
const RENDER_EVAL_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['status', 'summary', 'findings'],
  properties: {
    status: { type: 'string' }, summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['severity', 'message', 'file'],
        properties: { severity: { type: 'string' }, message: { type: 'string' }, file: { type: ['string', 'null'] }, crit_ref: { type: ['string', 'null'] }, assertion_ref: { type: ['string', 'null'] }, observed: { type: ['string', 'null'] } },
      },
    },
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

// ---- Engine prompt diet --------------------------------------------------------
// Trim fat in-memory payloads before embedding them in engine prompts. Pure JS
// pre-processing — it changes NO instruction the receiving agent acts on, only
// strips bytes the agent never reads. validation-writer decides the FINAL list
// from `verdict.is_real` + `verdict.adjusted_severity` and never reads the
// adversarial `rationale`, so dropping rationale (and capping over-long message/
// fix/summary text) is behaviour-identical while cutting the largest embedded
// payload. Compact (no-indent) stringify on top. On the subscription path this
// is waste/latency reduction, not direct billing; the wins compound under
// api-mode caching.
const _cap = (s, n) => { const t = String(s == null ? '' : s); return t.length > n ? t.slice(0, n) + '…[trimmed]' : t }
function trimForWriter(vals) {
  return (vals || []).map(r => ({
    validator: r.validator, status: r.status, summary: _cap(r.summary, 280), methodology: r.methodology,
    findings: (r.findings || []).map(f => ({ severity: f.severity, message: _cap(f.message, 280), file: f.file, line: f.line, fix: f.fix == null ? null : _cap(f.fix, 200) })),
    verified: (r.verified || []).map(x => ({
      finding: { severity: x.finding.severity, message: _cap(x.finding.message, 280), file: x.finding.file, line: x.finding.line, fix: x.finding.fix == null ? null : _cap(x.finding.fix, 200) },
      // keep verdict.is_real + verdict.adjusted_severity (the writer's decision inputs);
      // DROP verdict.rationale — never read by the writer, often the longest field.
      verdict: x.verdict ? { is_real: x.verdict.is_real, adjusted_severity: x.verdict.adjusted_severity } : null,
    })),
  }))
}
// ---- Cache-friendly prompt discipline (invariant, audited) ----------------------
// Prompt caching (automatic on the subscription path, breakpointed in api-mode)
// matches a left-to-right prefix. KEEP STABLE CONTENT AT THE HEAD of every prompt
// (role + task text + criteria path + co-signed contract) and put VOLATILE content
// LAST (attempt numbers, per-call timestamps, the embedded payload). No timestamp /
// UUID / "attempt N" may appear in a prompt's first ~120 chars. Builders below
// already lead with stable role text; preserve that ordering when editing.

// Plan-graph validation, shared by PHASE 1 (initial plan) and the bounded replan hatch
// (merged graph). Returns [] when clean, else a list of human-readable errors:
// duplicate ids silently overwrite in tasksById; orphan tasks never run; unknown/
// duplicate wave refs misroute. Same checks in both call sites (panel requirement).
function planGraphErrors(tasks, waves) {
  const ids = tasks.map(t => t.id)
  const known = new Set(ids)
  const flatWaves = waves.flat()
  const dupIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))]
  const dupWaveRefs = [...new Set(flatWaves.filter((id, i) => flatWaves.indexOf(id) !== i))]
  const unknownRefs = [...new Set(flatWaves.filter(id => !known.has(id)))]
  const orphanTasks = ids.filter(id => !flatWaves.includes(id))
  const e = []
  if (dupIds.length) e.push(`duplicate task id(s): ${dupIds.join(', ')}`)
  if (dupWaveRefs.length) e.push(`task(s) referenced in >1 wave: ${dupWaveRefs.join(', ')}`)
  if (unknownRefs.length) e.push(`wave(s) cite unknown task id(s): ${unknownRefs.join(', ')}`)
  if (orphanTasks.length) e.push(`task(s) never scheduled in any wave: ${orphanTasks.join(', ')}`)
  return e
}

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
// ---- Repo-portability gate: detect the integration branch + test runner (+ server-boot
// for future preview-eval, stashed/unused) instead of hardcoding 'main' /
// 'python -m unittest'. Default OFF. When OFF, INTEGRATION_BRANCH + TEST keep the historical
// hardcodes, so every code-mode prompt is byte-identical to the flag-off engine. When ON
// (code mode only), ONE discovery-phase detector agent sets them per
// the repo; artefact mode never touches them. ----
const PORTABLE = A.repoPortable === true
let INTEGRATION_BRANCH = 'main'
let TEST = {
  desc: 'Tests = stdlib unittest importable from repo root.',
  discover: (p) => `python -m unittest discover -s ${p}/tests -t ${p} (or py -3)`,
  rerun: 'python -m unittest',
}
let SERVER_BOOT = null // {cmd, port} — detected for future code-mode preview-eval; UNUSED for now.
const PORTABILITY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['is_git_repo', 'integration_branch', 'test_desc', 'test_run_template', 'test_rerun', 'server_boot_cmd', 'server_port', 'evidence'],
  properties: {
    is_git_repo: { type: 'boolean', description: 'false if repoDir is NOT a git work tree (git -C <repo> rev-parse --is-inside-work-tree fails) — code mode is impossible there' },
    integration_branch: { type: 'string', description: "the repo's integration/default branch, e.g. main|master|develop" },
    test_desc: { type: 'string', description: 'one-line description of how this repo runs its test suite' },
    test_run_template: { type: 'string', description: 'shell command to run the suite from a directory; use the LITERAL token __DIR__ where the dir path goes, e.g. "(cd __DIR__ && npm test)" or "python -m unittest discover -s __DIR__/tests -t __DIR__ (or py -3)"' },
    test_rerun: { type: 'string', description: 'short phrase for re-running a single test after a fix, e.g. "npm test" or "python -m unittest"' },
    server_boot_cmd: { type: ['string', 'null'], description: 'dev-server boot command if the repo has one (future preview-eval), else null' },
    server_port: { type: ['integer', 'null'], description: 'dev-server port if known, else null' },
    evidence: { type: 'string', description: 'files/signals used (package.json, pyproject.toml, git symbolic-ref, …)' },
  },
}
function portabilityDetectPrompt() {
  return `You are a repo-portability detector for the engagement engine. Inspect the git repo at ${REPO} (READ-ONLY) and report how THIS repo is built so the engine can drive it without hardcoding 'main' / 'python -m unittest'.
Detect:
0. is_git_repo — run git -C ${REPO} rev-parse --is-inside-work-tree. Set is_git_repo=false if it fails / ${REPO} has no .git (code mode needs a git work tree; if the git root is a sub/parent dir, say so in evidence).
1. integration_branch — the default/integration branch. Try in order: git -C ${REPO} symbolic-ref --short refs/remotes/origin/HEAD (strip leading 'origin/'); else git -C ${REPO} branch --show-current; else look for main|master|develop among branches.
2. test runner — inspect the repo root: package.json (scripts.test → npm/yarn/pnpm test), pyproject.toml / pytest.ini / tox.ini (pytest), setup.py or a tests/ dir (python -m unittest), go.mod (go test ./...), Cargo.toml (cargo test). Return test_run_template using the LITERAL token __DIR__ for the directory (e.g. "(cd __DIR__ && npm test)"), a one-line test_desc, and a short test_rerun phrase.
3. server boot (best-effort, for future use) — a dev-server command + port if obvious (package.json scripts.dev, a Procfile, uvicorn/flask/fastapi entry in pyproject); else null/null.
Use Bash + Read ONLY. Do NOT modify anything. Return per schema with evidence citing the files you read.`
}
// ---- Contract gate: per-task contract handshake. Default OFF. M/L only (S skips). When OFF the
// deliver loop is byte-identical to the flag-off engine. ----
const CONTRACTS_ON = (A.contracts === true) && (TIER === 'M' || TIER === 'L')
// Two roles in the contract handshake:
//  - Per-task REVIEW JUDGE: code → code-reviewer; artefact → reality-checker (CRITIQUE_AGENT, a real
//    critique-class adversary replacing the anonymous default artefact critic).
//  - Contract WRITER (call 2, persists tasks/{id}.md): reality-checker in BOTH modes, because it HAS
//    Write and code-reviewer is Read/Glob/Grep only. So in code mode the contract co-signer/writer
//    (reality-checker) is deliberately a DIFFERENT party from the later review judge (code-reviewer) —
//    extra independent eyes, and the only way to persist the file without expanding a reviewer's tools.
// Domain-specific critics (accessibility-validator, etc.) still run in the validate phase via plan.validators.
const CRITIQUE_AGENT = 'reality-checker'
const CONTRACT_WRITER = 'reality-checker'
// ---- Replan gate: bounded replan hatch (failure recovery). Default OFF. When OFF a wave hard-stop
// returns the EXISTING error contract unchanged. When ON,
// ONE replan per run is allowed: cleanup failed wave → re-plan remaining waves → re-validate →
// continue. Max 1 replan; a second hard-stop returns the existing error contract (no loop). ----
const REPLAN_ON = A.replan === true
let replanCount = 0
// ---- Consolidation-guard gate: wave-consolidation guard. Default OFF. When OFF the post-
// consolidation result is only logged (flag-off behaviour). When ON, a null
// consolidator / merge_ok:false / (code-mode) merge-landed-but-tests-failed hard-stops the run
// with the same error-contract shape as the pre-consolidation hard-stop, so dependent waves never
// branch off a missing or broken integration HEAD. Bug-fix class: behaviour differs ONLY on a
// failed consolidation; clean runs are unchanged. Activation policy is the conductor's —
// guard-class flags may default ON earlier than feature-class flags. ----
const CONSGUARD_ON = A.consGuard === true
function replanPrompt(failedWaveNo, reason, completedTaskIds, remainingCritRefs, suffix) {
  return `You are re-planning an agency engagement after wave ${failedWaveNo} hard-stopped: ${reason}. The SCRIPT orchestrates fan-out; you do NOT dispatch. Read ${ENG}/criteria.md.
COMPLETED & LOCKED (do NOT re-schedule, do NOT reuse these ids): ${JSON.stringify(completedTaskIds)} — their merged work stays on the integration branch / under ${ENG}.
Re-plan ONLY the REMAINING work needed to finish the criteria still open (${JSON.stringify(remainingCritRefs)}). Produce NEW waves + NEW atomic tasks for that remaining work. EVERY new task id MUST end with the suffix "${suffix}" and MUST NOT collide with any completed/locked id. Keep same-wave files disjoint; a later wave may depend on an earlier one. Also append a "## Replan ${replanCount + 1} — ${reason}" section to ${ENG}/plan.md (Bash/Write) describing the new remaining-waves graph, and emit a ledger event: python ${SCRIPTS}/ledger-emit.py ${ENG} --agent ${DOMAIN ? DOMAIN + '-lead' : 'lead'} --tier ${TIER} --type replan --phase deliver --note "wave ${failedWaveNo}: ${reason}" (best-effort; never blocks).
Return per schema: waves (remaining only), tasks (remaining only, ids suffixed "${suffix}"), reason.`
}
const tasksById = {}
plan.tasks.forEach(t => { tasksById[t.id] = t })
// Plan-graph validation — fail loud on a malformed plan BEFORE any delivery.
// Duplicate ids silently overwrite in tasksById; orphan tasks (not in any wave)
// never run; unknown/duplicate wave refs misroute. One upfront check, not per-wave.
{
  const planErrs = planGraphErrors(plan.tasks, plan.waves)
  if (planErrs.length) return { error: `plan malformed — ${planErrs.join('; ')}`, engagementDir: ENG, domain: plan.domain, tier: TIER, gate: { precheck_pass: false, exit_code: null, failures: planErrs, checks: [] }, readyForAcceptance: false }
}
log(`plan: domain=${plan.domain} tier=${TIER}; ${plan.tasks.length} tasks across ${plan.waves.length} wave(s); validators=${plan.validators.join(',')}`)

// ---- Repo-portability detection (gated; code mode only). Adds exactly ONE discovery agent
// call when ON; when OFF nothing runs and the hardcoded defaults stand (byte-identity). ----
if (PORTABLE && MODE === 'code') {
  const det = await agent(portabilityDetectPrompt(), { label: 'detect:repo', phase: 'discovery', schema: PORTABILITY_SCHEMA })
  if (det && det.is_git_repo === false) {
    return { error: `repo-portability: ${REPO} is not a git work tree — code mode (worktree+octopus) requires git. Pass repoDir = the actual git root. Detector evidence: ${det.evidence || 'n/a'}`, engagementDir: ENG, domain: plan.domain, tier: TIER, gate: { precheck_pass: false, exit_code: null, failures: ['repoDir-not-git'], checks: [] }, readyForAcceptance: false }
  }
  if (det) {
    INTEGRATION_BRANCH = det.integration_branch || INTEGRATION_BRANCH
    if (det.test_run_template) {
      const tmpl = String(det.test_run_template)
      // The schema asks for a __DIR__ token; if the detector omits it, wrap the bare command in
      // the target dir rather than silently running it from the wrong cwd.
      const discover = tmpl.includes('__DIR__')
        ? (p) => tmpl.split('__DIR__').join(p)
        : (p) => `(cd ${p} && ${tmpl})`
      TEST = { desc: det.test_desc || TEST.desc, discover, rerun: det.test_rerun || 'the test command above' }
    }
    SERVER_BOOT = det.server_boot_cmd ? { cmd: det.server_boot_cmd, port: det.server_port || null } : null
    log(`repo-portability: branch=${INTEGRATION_BRANCH}; test='${(det.test_run_template || '').slice(0, 48)}'; serverBoot=${SERVER_BOOT ? SERVER_BOOT.cmd : 'none'}`)
  }
}

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

// ---- Per-task contract handshake (pinned 3-call sequence; gated CONTRACTS_ON; M/L only) ----
// Call 1 owner proposes in-band (writes NO file). Call 2 reviewer (code → code-reviewer;
// artefact → CRITIQUE_AGENT) amends/accepts AND writes tasks/{id}.md "## Contract (co-signed)".
// Call 3 owner contests (only if reviewer amended). Returns the agreed assertions + contested
// ids + the negotiation transcript, or null (flag off / S / empty proposal → deliver loop runs
// exactly as flag-off). The contract is later injected ONLY into the review prompt (conditional).
function contractProposePrompt(t) {
  return `You are the OWNER (${t.owner}) of one atomic task. BEFORE implementing, propose the per-task acceptance CONTRACT. Read ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}).
Task ${t.id}: ${t.title}. Files you will produce: ${t.files.join(', ')}.
Propose >=1 CONCRETE, CHECKABLE assertion PER cited criterion. Each assertion = one observable claim of done-ness + a 'check_how' (the exact way to verify it: a drive step, command, or inspection). Every assertion MUST cite its crit-N parent in crit_ref — a parentless assertion is scope-creep, do NOT add work the criteria do not ask for. Turn vague criteria into measurable checks (e.g. "page looks clean" -> "no element overflows the 1280px viewport" check_how "load at 1280px, assert no horizontal scrollbar"; "all controls have a visible focus ring" check_how "tab through, observe :focus outline").
Do NOT write any engagement file — return the proposal in-band per schema (status 'agreed'). The reviewer co-signs and writes the file.`
}
function contractCosignPrompt(t, proposal) {
  const judge = (MODE === 'code') ? 'code-reviewer' : 'you (reality-checker)'
  return `You are reality-checker, co-signing the per-task contract for task ${t.id} on behalf of the review — the per-task reviewer (${judge}) will judge this task against the co-signed rubric, so make it concrete and checkable. Read ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}).
Owner proposed: ${JSON.stringify(proposal.assertions)}
Amend or accept — you have LAST WORD on the rubric: tighten a vague assertion, add a missing checkable assertion for any cited criterion the owner under-specified, drop scope-creep (any assertion whose crit_ref is not in ${JSON.stringify(t.crit_refs)}). Keep every assertion bound to a crit-N parent.
THEN WRITE the converged contract into ${ENG}/tasks/${t.id}.md under a "## Contract (co-signed)" section (create the file if absent — legal on M/L). One line per assertion: "- {id} [{crit_ref}] ({status}): {assertion} — check_how: {check_how}". Use Bash/Write + absolute path.
Return the converged assertions in-band per schema.`
}
function contractContestPrompt(t, proposal, cosignedAssertions) {
  return `You are the OWNER (${t.owner}) of task ${t.id}. The reviewer amended your proposed contract.
You proposed: ${JSON.stringify(proposal.assertions)}
Reviewer co-signed: ${JSON.stringify(cosignedAssertions)}
CONTEST any assertion you believe over-reaches the cited criteria (you have last word on contest; the reviewer on the rubric). Return the contested assertion ids + a one-line rationale. Contested assertions are judged against ${ENG}/criteria.md text DIRECTLY (not against the contested wording). Contest nothing -> contested: [].`
}
function contractReviewBlock(contract) {
  if (!contract) return ''
  return `

## Co-signed contract (the agreed per-task rubric — judge against THIS *and* criteria.md)
Assertions: ${JSON.stringify(contract.assertions)}
Negotiation transcript: ${JSON.stringify(contract.transcript)}
Rules: (1) the contract is the agreed rubric for this review, but it NEVER waives criteria.md — if the deliverable satisfies EVERY assertion yet violates a cited crit-N, your verdict is STILL 'rework' (assertions cannot waive criteria). (2) For any assertion id in contested=${JSON.stringify(contract.contested)}, judge against ${ENG}/criteria.md text DIRECTLY, not the contested wording. (3) On each finding, set assertion_ref to the assertion id it maps to (or null). (4) In your summary, name any contested ids and how you judged them.`
}
function contractImplNote(t, contract) {
  if (!contract) return ''
  return `\nThis task has a CO-SIGNED CONTRACT at ${ENG}/tasks/${t.id}.md ("## Contract (co-signed)"): satisfy each assertion's check_how. Acknowledge the contract in your executor-report and note any contested ids ${JSON.stringify(contract.contested)} (those are judged against criteria.md directly).`
}
async function negotiateContract(t) {
  if (!CONTRACTS_ON) return null
  const proposal = await agent(contractProposePrompt(t), { label: `contract-propose:${t.id}`, phase: 'deliver', agentType: t.owner, schema: CONTRACT_SCHEMA })
  if (!proposal || !proposal.assertions || !proposal.assertions.length) return null
  // the WRITER co-signs + persists tasks/{id}.md (reality-checker, both modes — it has Write).
  const cosigned = await agent(contractCosignPrompt(t, proposal), { label: `contract-cosign:${t.id}`, phase: 'deliver', agentType: CONTRACT_WRITER, schema: CONTRACT_SCHEMA })
  const assertions = (cosigned && cosigned.assertions && cosigned.assertions.length) ? cosigned.assertions : proposal.assertions
  let contested = []
  if (JSON.stringify(assertions) !== JSON.stringify(proposal.assertions)) {
    const contest = await agent(contractContestPrompt(t, proposal, assertions), { label: `contract-contest:${t.id}`, phase: 'deliver', agentType: t.owner, schema: CONTEST_SCHEMA })
    contested = (contest && Array.isArray(contest.contested)) ? contest.contested : []
  }
  return { assertions, contested, transcript: { proposed: proposal.assertions, cosigned: assertions, contested } }
}

function implPrompt(t, attempt, contract) {
  const deps = (t.depends_on && t.depends_on.length)
    ? `\nThis task DEPENDS ON earlier work already merged into ${INTEGRATION_BRANCH}: ${t.depends_on.join(', ')}. Your worktree (branched off ${INTEGRATION_BRANCH}) already contains those files — import/use them; do NOT recreate them.` : ''
  return `You are a dev specialist implementing ONE atomic task in your OWN git worktree. Use \`git -C <abs>\` + absolute paths; do NOT cd into shared dirs.

Task ${t.id}: ${t.title}
Repo ${REPO} (integration branch: ${INTEGRATION_BRANCH}). Worktree ${wt(t)}. Branch ${br(t)}.
Files YOU create/edit (disjoint from same-wave peers): ${t.files.join(', ')}. Criteria: ${t.crit_refs.join(', ')}.${deps}

Steps:
1. Provision worktree off the CURRENT integration HEAD: git -C ${REPO} worktree add -b ${br(t)} ${wt(t)} ${INTEGRATION_BRANCH}  (retry once after sleep 2 on lock error; if it already exists from a prior attempt, skip).
2. Implement your files INSIDE ${wt(t)}/. Standard library ONLY unless criteria allow deps. Follow the criteria contract LITERALLY (exact body shapes/keys). ${TEST.desc}
3. Run your own tests: ${TEST.discover(wt(t))}. Capture pass/fail.
4. Commit: git -C ${wt(t)} add -A && git -C ${wt(t)} commit -m '${t.id}: ${t.title} (attempt ${attempt})'
5. head_sha = git -C ${wt(t)} rev-parse HEAD
6. Write/refresh executor-report at CANONICAL ${ENG}/executor-reports/${t.id}.md (absolute, NOT in worktree). MUST open with "## Criteria acknowledgement" then one bullet per criterion naming the crit id. Then "## Work". No slot/last-attempt language.
Return per schema.` + contractImplNote(t, contract)
}
function reviewTaskPrompt(t, spec, contract) {
  return `You are code-reviewer doing a SCOPED per-task review inside the delivery loop. Review ONLY task ${t.id}'s files in worktree ${wt(t)}, judged against the cited criteria — passing tests is NOT sufficient; the implementation MUST match the criteria contract literally (exact keys/shapes/status codes).
Read: ${t.files.map(f => wt(t) + '/' + f).join(' , ')} and ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}). Specialist report ${spec.report_path}, self_tests_pass=${spec.self_tests_pass}.
Return per schema: verdict ('pass' if all cited criteria literally satisfied else 'rework'), findings[] (severity/file/message/crit_ref), summary.` + contractReviewBlock(contract)
}
function reworkPrompt(t, review, attempt) {
  return `You are the SAME dev specialist reworking task ${t.id} in worktree ${wt(t)} (branch ${br(t)}) after a scoped review returned 'rework'. Address EVERY finding so cited criteria are LITERALLY satisfied. Fix BOTH implementation AND its test if needed. Re-run ${TEST.rerun} for your test (confirm green). Commit: git -C ${wt(t)} add -A && git -C ${wt(t)} commit -m '${t.id}: rework attempt ${attempt}'. Append "## Rework attempt ${attempt}" to ${ENG}/executor-reports/${t.id}.md.
Review findings: ${JSON.stringify(review.findings)}
Return per schema (head_sha=new HEAD).`
}

// ---- artefact mode (design / marketing): write deliverables to engagement/ paths, no git, critique review ----
function artefactImplPrompt(t, attempt, contract) {
  const deps = (t.depends_on && t.depends_on.length)
    ? `\nThis task DEPENDS ON earlier deliverables already written under ${ENG}: ${t.depends_on.join(', ')}. Read and build on them; do NOT recreate them.` : ''
  return `You are a ${plan.domain} specialist producing ONE atomic deliverable as ARTEFACT files (no code build, no git). Write directly under the engagement dir using Bash/Write + absolute paths.

Task ${t.id}: ${t.title}
Engagement ${ENG}. Files YOU create (engagement-relative, DISJOINT from same-wave peers): ${t.files.join(', ')}. Criteria: ${t.crit_refs.join(', ')}.${deps}

Steps:
1. Produce each deliverable at ${ENG}/<file>. Satisfy the criteria contract LITERALLY (exact sections / values / copy the criteria name). For VISUAL artefacts follow the project's Codex-default creative direction (codex-bridge); Claude assembles / specs / QAs.
2. Write/refresh executor-report at ${ENG}/executor-reports/${t.id}.md. MUST open with "## Criteria acknowledgement" then one bullet per criterion naming the crit id. Then "## Work". No slot/last-attempt language.
Return per schema: task_id, branch="" , head_sha="" , files_touched (the engagement-relative paths you wrote), report_path, self_tests_pass (true if the deliverable meets its own done-when), status ('done'|'blocked'), notes.` + contractImplNote(t, contract)
}
function artefactReviewPrompt(t, spec, contract) {
  return `You are a ${plan.domain} critique reviewer doing a SCOPED per-task review inside the delivery loop. Judge ONLY task ${t.id}'s artefact(s) against the cited criteria — "the file exists" is NOT sufficient; the deliverable MUST satisfy the criteria contract. Apply the right lens: design -> critique / design-review (intent, hierarchy, token / brand consistency, a11y basics); marketing -> reality-check every claim + brand-voice fit.
Read: ${t.files.map(f => ENG + '/' + f).join(' , ')} and ${ENG}/criteria.md (criteria ${t.crit_refs.join(', ')}). Specialist report ${spec.report_path}.
Return per schema: verdict ('pass' if all cited criteria satisfied else 'rework'), findings[] (severity/file/message/crit_ref), summary.` + contractReviewBlock(contract)
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
  const contract = await negotiateContract(t)  // null when flag off / S / empty proposal → identical to flag-off
  let spec = await agent(artefactImplPrompt(t, 1, contract), { label: `impl:${t.id}#1`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
  if (!spec) return blockedSpec(t, 'artefact implementation agent returned no result')
  const trail = []
  let review_ok = false
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const reviewOpts = { label: `review:${t.id}#${attempt}`, phase: 'deliver', schema: REVIEW_VERDICT_SCHEMA }
    if (contract) reviewOpts.agentType = CRITIQUE_AGENT  // real critic instead of anonymous default (contract path only)
    const review = await agent(artefactReviewPrompt(t, spec, contract), reviewOpts)
    trail.push(review ? review.verdict : 'error')
    if (review && review.verdict === 'pass') { review_ok = true; break }
    if (!review) break  // review agent FAILED (null) — do NOT treat as pass; wave guard hard-stops on review_ok=false
    if (attempt === MAX_ATTEMPTS) break  // rework budget exhausted still on 'rework' — review_ok stays false
    const reworked = await agent(artefactReworkPrompt(t, review, attempt + 1), { label: `rework:${t.id}#${attempt + 1}`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
    if (!reworked) break
    spec = reworked
  }
  return { ...spec, review_trail: trail, review_ok, contract }
}
async function deliverOneTask(t) {
  const contract = await negotiateContract(t)  // null when flag off / S / empty proposal → identical to flag-off
  let spec = await agent(implPrompt(t, 1, contract), { label: `impl:${t.id}#1`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
  if (!spec) return blockedSpec(t, 'implementation agent returned no result')
  const trail = []
  let review_ok = false
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const review = await agent(reviewTaskPrompt(t, spec, contract), { label: `review:${t.id}#${attempt}`, phase: 'deliver', agentType: 'code-reviewer', schema: REVIEW_VERDICT_SCHEMA })
    trail.push(review ? review.verdict : 'error')
    if (review && review.verdict === 'pass') { review_ok = true; break }
    if (!review) break  // review agent FAILED (null) — do NOT treat as pass; wave guard hard-stops on review_ok=false
    if (attempt === MAX_ATTEMPTS) break  // rework budget exhausted still on 'rework' — review_ok stays false
    const reworked = await agent(reworkPrompt(t, review, attempt + 1), { label: `rework:${t.id}#${attempt + 1}`, phase: 'deliver', agentType: t.owner, schema: SPEC_SCHEMA })
    if (!reworked) break
    spec = reworked
  }
  return { ...spec, review_trail: trail, review_ok, contract }
}

// ---- Render-eval gate: artefact render-eval. Default OFF. Artefact mode only; runs AFTER manifest-verify.
// When OFF (or code mode, or no renderable HTML in the wave) the step makes zero agent calls. ----
const RENDEREVAL_ON = A.renderEval === true
const RENDER_BASE = A.previewUrl || ('file://' + ENG + '/')  // caller-supplied http base where file:// is blocked
const isRenderable = f => /\.html?$/i.test(String(f))
// ---- Cheap-tier gate: cheap-model tiering for mechanical engine steps. Default OFF. When OFF, no `model`
// key is added to any opts → byte-identical to current behaviour. When ON: manifest-verify + gate-runner
// → haiku (string-match / exit-code work); adversarial-verify → sonnet. impl/review/plan/handoff/
// consolidate stay on the inherited model (judgement work). Quality gate: A/B identical verdicts. ----
const CHEAP = A.cheapTiers === true
const cheapModel = (m) => CHEAP ? { model: m } : {}
function renderEvalPrompt(waveNo, pass, checklist) {
  return `You are render-eval for ${plan.domain} ARTEFACT deliverables, wave ${waveNo} (pass ${pass}). RENDER each artefact and check the RENDERED result — not that the file exists. No server boot.
Engagement ${ENG}. Render base: ${RENDER_BASE} (navigate to RENDER_BASE + the file path).
Files + per-file check-list (co-signed contract assertions preferred; else crit_refs — read criteria.md for text):
${checklist.map(c => `- ${c.file} (task ${c.task}): ${c.assertions ? 'CONTRACT assertions ' + JSON.stringify(c.assertions) : 'crit_refs ' + JSON.stringify(c.crit_refs)}`).join('\n')}
For each file: navigate to ${RENDER_BASE}<file>, read OBSERVED values (browser_snapshot / browser_evaluate / browser_console_messages), exercise any control named in a check_how, and compare to its check-list. Emit a finding for each miss with a CONCRETE observed value, crit_ref, and assertion_ref (when the check came from a contract assertion). Return per schema.`
}

const allSpecs = []
const waveSummaries = []
// `waves` is mutable so the bounded replan hatch can splice in re-planned remaining waves; with
// REPLAN_ON=false it is just plan.waves.slice() and this loop runs exactly as the prior for-loop.
let waves = plan.waves.slice()
let wi = 0
// ---- Bounded replan hatch, EXTRACTED so the pre-consolidation hard-stop AND
// the post-consolidation consolidation guard (below) share ONE replan path — no duplicated machinery,
// no second replan loop. Returns true iff a replan was spliced (caller `continue`s at the same wi);
// false → caller falls through to its own error contract. Reassigns the outer waves/replanCount and
// mutates tasksById/waveSummaries + the passed-in specs (same object refs as before extraction). When
// REPLAN_ON is false it returns false immediately with ZERO agent calls — so every prior call site is
// behaviour-identical when the flag is off. ----
async function tryReplan(reasonStr, waveTasks, specs) {
  if (!(REPLAN_ON && replanCount < 1)) return false
  // (1) NEW cleanup step: cleanupCommands ARE NOW EXECUTED (returned data was never run before) — plus
  //     `git branch -D wf_{id}` because branches SURVIVE worktree removal. Trade-off: this sacrifices the
  //     failed wave's resume-reuse; completed waves' prefix-cache is untouched.
  const cleanupCmds = (MODE === 'code')
    ? waveTasks.flatMap(t => [`git -C ${REPO} worktree remove --force ${wt(t)}`, `git -C ${REPO} branch -D ${br(t)}`]).concat([`git -C ${REPO} worktree prune`])
    : []
  if (cleanupCmds.length) {
    await agent(
      `CLEANUP before replan of failed wave ${wi + 1} (Bash). Execute EACH command in order; a worktree/branch may already be gone — ignore "not found"/"is not a working tree" errors and continue. Then report.\n${cleanupCmds.map(c => '  ' + c).join('\n')}\nReturn per schema.`,
      { label: `replan-cleanup:w${wi + 1}`, phase: 'deliver', schema: { type: 'object', additionalProperties: false, required: ['done'], properties: { done: { type: 'boolean' }, notes: { type: ['string', 'null'] } } } })
  }
  // (2) mark the failed wave's specs superseded (same object refs live in allSpecs → no ghost tasks at seam)
  specs.forEach(s => { s.superseded_by_replan = true })
  waveSummaries.push({ wave: wi + 1, tasks: waveTasks.map(t => t.id), replanned: true, reason: reasonStr })
  // (3) re-invoke lead:plan for REMAINING work with completed-waves locked
  const completedTaskIds = waves.slice(0, wi).flat()
  const remainingCritRefs = [...new Set(waves.slice(wi).flat().map(id => tasksById[id]).filter(Boolean).flatMap(t => t.crit_refs || []))]
  const suffix = `-r${replanCount + 1}`
  const repOpts = { label: `replan:w${wi + 1}`, phase: 'deliver', schema: REPLAN_SCHEMA }
  if (DOMAIN) repOpts.agentType = `${DOMAIN}-lead`
  const rep = await agent(replanPrompt(wi + 1, reasonStr, completedTaskIds, remainingCritRefs, suffix), repOpts)
  // (4) re-run BOTH validations: PLAN_SCHEMA (enforced on the agent call) + graph block on the MERGED graph,
  //     plus id-collision / suffix / completed-ids-unchanged.
  if (rep && Array.isArray(rep.tasks) && Array.isArray(rep.waves)) {
    const newIds = rep.tasks.map(t => t.id)
    const collisions = newIds.filter(id => tasksById[id] !== undefined)             // collide with ANY prior id
    const badSuffix = newIds.filter(id => !String(id).endsWith(suffix))
    const completedTasks = completedTaskIds.map(id => tasksById[id]).filter(Boolean)
    const mergedTasks = [...completedTasks, ...rep.tasks]
    const mergedWaves = [...waves.slice(0, wi), ...rep.waves]
    const replanErrs = planGraphErrors(mergedTasks, mergedWaves)
    if (collisions.length) replanErrs.push(`replan id collides with a prior id: ${collisions.join(', ')}`)
    if (badSuffix.length) replanErrs.push(`replan id(s) missing suffix ${suffix}: ${badSuffix.join(', ')}`)
    if (!completedTaskIds.every(id => tasksById[id])) replanErrs.push('completed task id(s) changed during replan')
    if (replanErrs.length === 0) {
      // (5) splice: install new tasks, replace waves from wi onward with the replan's remaining waves
      rep.tasks.forEach(t => { tasksById[t.id] = t })
      waves = [...waves.slice(0, wi), ...rep.waves]
      replanCount++
      log(`replan ${replanCount}: wave ${wi + 1} superseded (${reasonStr}); +${rep.tasks.length} task(s) across ${rep.waves.length} new wave(s)`)
      return true  // caller does `continue` → re-enter at wi with the first replan wave (no wi++)
    }
    log(`replan REJECTED (validation): ${replanErrs.join('; ')} — falling back to error contract`)
  } else {
    log('replan produced no usable plan — falling back to error contract')
  }
  return false  // replan invalid → caller falls through to the existing error contract (no loop)
}
while (wi < waves.length) {
  const waveTasks = waves[wi].map(id => tasksById[id])  // refs validated upfront (incl. replan-spliced waves)
  if (!waveTasks.length) { wi++; continue }
  log(`deliver wave ${wi + 1}/${waves.length}: ${waveTasks.map(t => t.id).join(', ')}`)
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
    const reasonStr = reasons.join('; ')
    log(`deliver wave ${wi + 1} HARD-STOP: ${reasonStr}`)
    // ---- Bounded replan hatch (ONE per run). When OFF or already used → existing error contract. ----
    if (await tryReplan(reasonStr, waveTasks, specs)) continue
    return {
      error: `deliver wave ${wi + 1} did not cleanly complete — ${reasonStr}. No consolidation; fix and resume (resumeFromRunId), or clean worktrees first.`,
      engagementDir: ENG, domain: plan.domain, tier: TIER,
      deliver: allSpecs.map(s => ({ id: s.task_id, status: s.status, review_trail: s.review_trail, review_ok: s.review_ok, superseded_by_replan: !!s.superseded_by_replan })),
      cleanupCommands: (MODE === 'code') ? waveTasks.map(t => `git -C ${REPO} worktree remove --force ${wt(t)}`) : [],
      gate: { precheck_pass: false, exit_code: null, failures: [`deliver-wave-${wi + 1}-incomplete`], checks: [] },
      readyForAcceptance: false,
    }
  }
  const cons = (MODE === 'code')
    ? await agent(
      `Wave-barrier CONSOLIDATOR for repo ${REPO}, wave ${wi + 1}. Merge these branches into ${INTEGRATION_BRANCH} (they branched off ${INTEGRATION_BRANCH}; same-wave files are disjoint so octopus should be clean):
${specs.map(s => `- ${s.task_id}: branch ${s.branch} @ ${s.head_sha}`).join('\n')}
Steps (Bash, capture raw):
1. git -C ${REPO} checkout ${INTEGRATION_BRANCH}
2. FAST PATH — octopus: git -C ${REPO} merge --no-ff -m 'consolidate wave ${wi + 1}' ${specs.map(s => s.branch).join(' ')}
3. If step 2 fails / refuses ("Should not be doing an octopus" or a CONFLICT): git -C ${REPO} merge --abort, then FALLBACK — merge branches ONE AT A TIME (git -C ${REPO} merge --no-ff <branch>). On a conflict, RESOLVE it by reconciling BOTH task intents (read the conflicting hunks + the task list), then git add + commit. Set conflict_resolved=true, strategy='sequential+resolve'.
4. Run repo-root tests: ${TEST.discover(REPO)}. Capture output + pass/fail.
5. merge_head = git -C ${REPO} rev-parse HEAD ; then remove this wave's worktrees + prune:
   ${waveTasks.map(t => `git -C ${REPO} worktree remove --force ${wt(t)}`).join('\n   ')}
   git -C ${REPO} worktree prune
Return per schema: merge_ok, conflicts (any seen), conflict_resolved, strategy, merge_head, tests_passed, test_output (trimmed), notes.`,
      { label: `consolidate:w${wi + 1}`, phase: 'deliver', schema: CONSOLIDATE_SCHEMA })
    : await agent(
      `Wave-barrier MANIFEST-VERIFY for ${plan.domain} ARTEFACT deliverables, wave ${wi + 1}. There is NO git merge — artefacts are distinct files written under ${ENG}. Verify each task's files exist and are non-empty:
${specs.map(s => `- ${s.task_id}: ${(s.files_touched || []).join(', ')}`).join('\n')}
Steps (Bash): for EACH file run \`test -s ${ENG}/<file> && echo OK <file> || echo MISSING <file>\` (exists AND non-empty). Then \`ls -la\` the touched paths for the listing.
Return per schema: merge_ok (true iff ALL files exist and are non-empty), conflicts:false, conflict_resolved:false, strategy:'artefact-manifest', merge_head:"" , tests_passed (same as merge_ok — all artefacts present & non-empty), test_output (the OK/MISSING lines + ls, trimmed), notes (name any MISSING / empty file).`,
      { label: `manifest:w${wi + 1}`, phase: 'deliver', schema: CONSOLIDATE_SCHEMA, ...cheapModel('haiku') })
  // ---- Wave-consolidation guard (A.consGuard). The pre-consolidation hard-stop above guards task
  // DELIVERY; this guards the consolidation RESULT, which was previously only logged before the loop
  // proceeded to dependent waves. A null consolidator or merge_ok:false means the merge never landed
  // → the integration branch is unchanged, so it is replan-compatible (routed through the SAME bounded
  // tryReplan when A.replan is ON). A code-mode merge that LANDED but failed tests is NOT auto-replannable
  // — the bad merge already sits on the integration branch and unwinding a merge commit is manual — so it
  // ALWAYS hard-stops without replan. Either way: no further waves branch off a missing/broken HEAD.
  const consMissing = !cons || cons.merge_ok === false
  const consTestsFailed = MODE === 'code' && !!cons && cons.merge_ok === true && cons.tests_passed === false
  if (CONSGUARD_ON && (consMissing || consTestsFailed)) {
    const why = consMissing
      ? `consolidation did not land (${!cons ? 'consolidator returned nothing' : 'merge_ok=false'})`
      : `consolidation merged but repo tests failed — NOT auto-replannable (the merge already sits on ${INTEGRATION_BRANCH}; unwind the merge commit manually, then resume)`
    log(`wave ${wi + 1} CONSOLIDATION HARD-STOP: ${why}`)
    if (consMissing && await tryReplan(why, waveTasks, specs)) continue  // merge never landed → bounded replan when A.replan ON
    return {
      error: `wave ${wi + 1} consolidation failed — ${why}. No further waves; fix and resume (resumeFromRunId)${consMissing ? ' or clean worktrees first' : ''}.`,
      engagementDir: ENG, domain: plan.domain, tier: TIER,
      deliver: allSpecs.map(s => ({ id: s.task_id, status: s.status, review_trail: s.review_trail, review_ok: s.review_ok, superseded_by_replan: !!s.superseded_by_replan })),
      cleanupCommands: (MODE === 'code') ? waveTasks.map(t => `git -C ${REPO} worktree remove --force ${wt(t)}`) : [],
      gate: { precheck_pass: false, exit_code: null, failures: [`wave-${wi + 1}-consolidation-failed`], checks: [] },
      readyForAcceptance: false,
    }
  }
  // ---- Artefact render-eval (gated; artefact mode; after manifest). Renders the wave's HTML
  // artefacts and attacks each task's co-signed assertions (preferred) or crit_refs; a finding
  // re-dispatches the OWNING task ONCE (no merge/worktree machinery in artefact mode), then re-renders. ----
  if (MODE === 'artefact' && RENDEREVAL_ON) {
    const renderable = specs.flatMap(s => (s.files_touched || []).filter(isRenderable).map(f => ({ task: s.task_id, file: f })))
    if (renderable.length) {
      const checklist = renderable.map(r => {
        const sp = specs.find(s => s.task_id === r.task)
        const tk = tasksById[r.task]
        return { task: r.task, file: r.file, assertions: (sp && sp.contract && sp.contract.assertions) ? sp.contract.assertions : null, crit_refs: tk ? tk.crit_refs : [] }
      })
      let re = await agent(renderEvalPrompt(wi + 1, 1, checklist), { label: `render-eval:w${wi + 1}#1`, phase: 'deliver', agentType: 'render-eval', schema: RENDER_EVAL_SCHEMA })
      const actionable = ((re && re.findings) || []).filter(f => String(f.severity).toLowerCase() !== 'info' && (f.crit_ref || f.assertion_ref))
      if (actionable.length) {
        const byTask = {}
        for (const f of actionable) { const owner = (renderable.find(r => r.file === f.file) || {}).task; if (owner) (byTask[owner] = byTask[owner] || []).push(f) }
        for (const tid of Object.keys(byTask)) {
          const tk = tasksById[tid]
          if (tk) await agent(artefactReworkPrompt(tk, { findings: byTask[tid] }, 2), { label: `render-rework:${tid}`, phase: 'deliver', agentType: tk.owner, schema: SPEC_SCHEMA })
        }
        re = await agent(renderEvalPrompt(wi + 1, 2, checklist), { label: `render-eval:w${wi + 1}#2`, phase: 'deliver', agentType: 'render-eval', schema: RENDER_EVAL_SCHEMA })
      }
      log(`render-eval wave ${wi + 1}: status=${re && re.status} findings=${((re && re.findings) || []).length}`)
    }
  }
  waveSummaries.push({ wave: wi + 1, tasks: waveTasks.map(t => t.id), merge_ok: cons && cons.merge_ok, strategy: cons && cons.strategy, tests: cons && cons.tests_passed })
  log(`wave ${wi + 1} consolidated: ok=${cons && cons.merge_ok} strategy=${cons && cons.strategy} tests=${cons && cons.tests_passed}`)
  wi++
}

// ===========================================================================
// PHASE 4 — validate: plan.validators review -> adversarial-verify each finding.
// ===========================================================================
phase('validate')
const VALIDATORS = (plan.validators && plan.validators.length) ? plan.validators : ['code-reviewer']
const reviewTarget = (MODE === 'code')
  ? `the consolidated work in repo ${REPO} (HEAD on ${INTEGRATION_BRANCH})`
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
        { label: `verify:${v}#${i}`, phase: 'validate', schema: VERDICT_SCHEMA, ...cheapModel('sonnet') }).then(verdict => ({ finding: f, verdict }))
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
Validator results WITH verdicts (refuted-finding rationales dropped — use verdict.is_real / verdict.adjusted_severity): ${JSON.stringify(trimForWriter(vals))}
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

Context: ${MODE === 'code' ? `repo ${REPO} (HEAD ${INTEGRATION_BRANCH} = all waves merged)` : `base ${REPO} (artefacts under the engagement dir)`}. engagement ${ENG}. criteria ${ENG}/criteria.md. executor-reports in ${ENG}/executor-reports/. validation-log + validation-outputs written. Waves delivered: ${JSON.stringify(waveSummaries)}. ${diffGuidance}

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
  { label: 'gate-runner', phase: 'gate', schema: GATE_SCHEMA, ...cheapModel('haiku') })

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
