export const meta = {
  name: 'harnessopt-workflow',
  description: 'Harness-evolution loop as a workflow — the peer of skillopt-workflow for the SCRIPT/ENGINE layer SkillOpt excludes (scripts/*.py, scripts/lib/precheck/*, workflows/engagement-workflow.js). harvest harness-ready clusters -> Codex AUTHORS patch BUNDLES (test_patch red->green + fix_patch) -> harness-director SELECTS (zone-aware: Zone-2 engine rejects new-flag / default-changing edits; rejection-buffer; edit_budget) -> EXECUTABLE gate (throwaway temp copies: red->green regression + existing *-regress + py_compile/ruff or AsyncFunction-compile + a LIVE subprocess repro + byte-identity-when-OFF for Zone-2) -> PROMOTE(owned script/engine fix) | ESCALATE(commons-protocol / CLAUDE.md / trigger / hook = human) | REJECT(buffer) -> RECORD (resolved lines + cycle note). Codex authors; the director judges (never the same brain). dryRun-safe (gate writes only temp; promote/reject/record write nothing in dry-run; never auto-pushes). Out-of-band; NOT routed through agency-intake.',
  phases: [
    { title: 'harvest' }, { title: 'reflect' }, { title: 'select' },
    { title: 'gate' }, { title: 'promote' }, { title: 'stage-mr' }, { title: 'record' },
  ],
}

// ---------------------------------------------------------------------------
// params via args (defensive). The caller (a harness-evolution invocation)
// MUST supply claudeDir, memoryDir, ts. Harness is a LAYER, not a domain —
// no `domain` arg (cf. skillopt-workflow which is per-domain).
// ---------------------------------------------------------------------------
const A = (typeof args === 'string') ? JSON.parse(args) : (args || {})
const CLAUDE = A.claudeDir                            // abs path to ~/.claude (working corpus)
const MEMORY = A.memoryDir                            // abs path to the memory dir (log / buffer)
const TS = A.ts                                       // UTC "YYYYMMDDTHHMMSSZ" (Date.now banned in-script)
if (!CLAUDE || !MEMORY || !TS) {
  return { ok: false, error: 'harnessopt-workflow requires args.claudeDir, args.memoryDir, args.ts' }
}
const SCRIPTS = A.scriptsDir || (CLAUDE + '/scripts')
const MIRROR = A.mirrorDir || 'C:/releases/agentic-workflow'   // blessed sanitized mirror
const DRY = !!A.dryRun                                // dry-run: gate still runs in temp; promote/record mutate NOTHING
const LOG = A.logPath || (MEMORY + '/skill-evolution-log.md')
const EDIT_BUDGET = A.editBudget || 2                 // lower than SkillOpt — executable gates are heavy
const BUFFER = `${MEMORY}/harness-rejected-edits.md`
const DIRECTOR = 'harness-director'                   // agentType for the judge-only steps
const BYTEID_HARNESS = `${SCRIPTS}/harness/engine-byteid-harness.cjs`
const ENGINE_REL = 'workflows/engagement-workflow.js'
const VENV_PY = `${SCRIPTS}/.venv-adversary-lg/Scripts/python.exe`  // adversary_lg re-execs into this

// ===========================================================================
// SCHEMAS
// ===========================================================================
const HARVEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ready', 'due', 'signals', 'raw_tail'],
  properties: {
    ready: { type: 'boolean', description: 'true iff >=1 due (script x class) cluster' },
    due: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'class', 'count'], properties: { target: { type: 'string' }, class: { type: 'string' }, count: { type: 'integer' } } } },
    signals: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['engagement', 'failure_class', 'class_key', 'traced_to', 'evidence', 'zone'], properties: { engagement: { type: 'string' }, failure_class: { type: 'string' }, class_key: { type: 'string' }, traced_to: { type: 'string' }, evidence: { type: 'string' }, zone: { type: 'string', enum: ['zone1', 'zone2'] } } } },
    raw_tail: { type: 'string' },
  },
}
const PATCH_PROPS = {
  cluster: { type: 'string', description: 'the (target | class) cluster this patch closes' },
  target: { type: 'string', description: 'scripts/X.py | scripts/lib/precheck/Y.py | workflows/engagement-workflow.js' },
  zone: { type: 'string', enum: ['zone1', 'zone2'] },
  is_new_flag: { type: 'boolean', description: 'Zone-2 only: does the engine edit add a NEW A.* flag? (auto-reject if true)' },
  test_patch: { type: 'string', description: 'the NEW regression test text (a standalone test file body) that FAILS pre-fix and PASSES post-fix — split from the fix so red->green is provable' },
  fix_patch: { type: 'string', description: 'the production fix as an exact edit spec: target + "::<exact anchor>" + new content, or a unified-diff-style block the gate-runner can apply to a temp copy' },
  files_touched: { type: 'array', items: { type: 'string' } },
  new_regression_command: { type: 'string', description: 'the command that runs test_patch (e.g. `python <tmp>/test_x.py`; venv python for adversary classes)' },
  live_subprocess_command: { type: ['string', 'null'], description: 'a real-subprocess repro for orchestration scripts (null if a pure-function import test suffices)' },
  expected_pre_failure: { type: 'string' }, expected_post_success: { type: 'string' },
  rationale: { type: 'string' },
}
const REFLECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['codex_ran', 'reasoning', 'patches'],
  properties: {
    codex_ran: { type: 'boolean', description: 'true iff mcp__codex__codex actually returned' },
    reasoning: { type: 'string' },
    patches: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['cluster', 'target', 'zone', 'is_new_flag', 'test_patch', 'fix_patch', 'files_touched', 'new_regression_command', 'live_subprocess_command', 'expected_pre_failure', 'expected_post_success', 'rationale'], properties: PATCH_PROPS } },
  },
}
const SELECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['selected', 'dropped', 'edit_budget'],
  properties: {
    selected: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'zone', 'ownership', 'rationale', 'patch'], properties: { target: { type: 'string' }, zone: { type: 'string', enum: ['zone1', 'zone2'] }, ownership: { type: 'string', enum: ['owned', 'escalate'] }, rationale: { type: 'string' }, patch: { type: 'object', additionalProperties: true } } } },
    dropped: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'reason'], properties: { target: { type: 'string' }, reason: { type: 'string' } } } },
    edit_budget: { type: 'integer' },
  },
}
const GATE_RUN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['target', 'red_green_proven', 'regressions_green', 'static_clean', 'live_repro_pass', 'byteid_off_pass', 'captured', 'proposed_verdict'],
  properties: {
    target: { type: 'string' },
    red_green_proven: { type: 'boolean', description: 'test FAILED on pre-fix copy AND PASSED on post-fix copy' },
    regressions_green: { type: 'boolean', description: 'existing *-regress / harness tests still pass (true if none found)' },
    static_clean: { type: 'boolean', description: 'py_compile + ruff (no NEW diagnostics) / AsyncFunction-compile for the engine' },
    live_repro_pass: { type: ['boolean', 'null'], description: 'live subprocess repro passed (null if not applicable)' },
    byteid_off_pass: { type: ['boolean', 'null'], description: 'Zone-2: byte-identity-when-OFF proven (null for Zone-1)' },
    captured: { type: 'string', description: 'commands + cwd + exit codes + stdout/stderr excerpts (the audit trail)' },
    proposed_verdict: { type: 'string', enum: ['pass', 'fail'] },
  },
}
const GATE_VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['target', 'verdict', 'rationale'],
  properties: { target: { type: 'string' }, verdict: { type: 'string', enum: ['pass', 'fail'] }, rationale: { type: 'string' } },
}
const PROMOTE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['target', 'decision', 'applied', 'ownership', 'paths_written', 'rationale'],
  properties: { target: { type: 'string' }, decision: { type: 'string', enum: ['promote', 'escalate-human', 'reject'] }, applied: { type: 'boolean' }, ownership: { type: 'string', enum: ['owned', 'escalate'] }, paths_written: { type: 'array', items: { type: 'string' } }, rationale: { type: 'string' } },
}
const DRAFTMR_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['staged', 'branch', 'body_path', 'files', 'detail'],
  properties: {
    staged: { type: 'boolean' },
    branch: { type: 'string' },
    body_path: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    detail: { type: 'string' },
  },
}
const RECORD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'resolved_signals', 'cycle_note_path', 'detail'],
  properties: { ran: { type: 'boolean' }, resolved_signals: { type: 'array', items: { type: 'string' } }, cycle_note_path: { type: ['string', 'null'] }, detail: { type: 'string' } },
}

// ===========================================================================
// PHASE 1 — harvest: harness-ready.py clusters open harness signals by
// (script x class), >=2 = due. Exit 1 means DUE (not an error). zone2 iff the
// target is the FROZEN engine. dryrun/resolved/platform are excluded by the
// checker AND re-confirmed here.
// ===========================================================================
phase('harvest')
const harvest = await agent(
  `You are the HARNESS-EVOLUTION harvest step. Do TWO things (Bash + Read), return per schema.

1. READINESS — run: \`python ${SCRIPTS}/harness-ready.py --json --log "${LOG}"\` (if "python" is missing try "py -3"). It EXITS 1 when a cluster IS DUE and 0 when none — exit 1 is NOT an error; parse stdout JSON regardless of exit code. It reports due[] ({target,class,count}) and ready.

2. SIGNALS — Read the log at ${LOG}. For EVERY due cluster, extract the OPEN signals belonging to it. A signal is OPEN iff its block has NO "dryrun: true" line AND NO line starting "resolved" (incl. partials like "resolved (SCRIPT half):") AND is not a platform-limitation. For each: engagement, the exact "Failure class:" text, its class_key (strip a trailing "(rule_token)"), the "Traced to:" target, the "Evidence:" pointer, and zone ("zone2" iff Traced-to names ${ENGINE_REL}; else "zone1").

Return per schema: ready (true iff >=1 due cluster), due[], signals[], raw_tail (last ~600 chars of the harness-ready JSON).`,
  { label: 'harvest', phase: 'harvest', schema: HARVEST_SCHEMA })
if (!harvest || !harvest.ready) {
  return { ok: true, status: 'no-cluster-due', dryRun: DRY, harvest: harvest || null }
}
log(`harvest: ${harvest.due.length} due cluster(s); ${harvest.signals.length} open signal(s)`)

// ===========================================================================
// PHASE 2 — reflect: Codex AUTHORS the patch BUNDLES (cross-family). The
// orchestrating agent is a faithful RELAY, never an author. test_patch is SPLIT
// from fix_patch so red->green is provable.
// ===========================================================================
phase('reflect')
const reflect = await agent(
  `You ORCHESTRATE Codex (cross-family) as the PATCH author for a harness-evolution cycle. You do NOT author or improve patches yourself — defend-bias is exactly what this Codex-authors / director-judges separation prevents.

Call mcp__codex__codex (load via tool search if needed) with approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}". Give Codex the due harness signals below (each with Traced-to + Evidence) and the task: for each cluster author ONE patch BUNDLE that fixes the script/engine defect, SPLIT into:
- test_patch: a NEW standalone regression test (a runnable file body) that FAILS against the pre-fix code and PASSES after the fix — this is what proves red->green; it must NOT contain the fix.
- fix_patch: the production fix as an exact edit (target + "::<exact anchor>" + new content, or a clearly-applyable block).
- new_regression_command, live_subprocess_command (a REAL subprocess repro for orchestration scripts — e.g. adversary_lg classes re-exec into ${VENV_PY}; null only if a pure import-level test is faithful), expected_pre_failure / expected_post_success, files_touched, zone, is_new_flag.
ZONE-2 RULE (${ENGINE_REL} is FROZEN): the fix MUST be byte-identical when its flag is OFF and MUST NOT add a new A.* flag unless unavoidable (set is_new_flag accordingly — the director will reject new flags). Prefer a bug-fix inert when flags are off.
At most ${EDIT_BUDGET} patches. An EMPTY patches list is valid.

Due signals:
${JSON.stringify(harvest.signals, null, 2)}

Then RELAY Codex's bundles into the schema faithfully — do NOT author/expand/fix them. codex_ran=true iff mcp__codex__codex returned.`,
  { label: 'reflect:codex', phase: 'reflect', schema: REFLECT_SCHEMA })
const proposed = (reflect && reflect.patches) ? reflect.patches : []
log(`reflect: codex_ran=${reflect && reflect.codex_ran}; ${proposed.length} patch(es) proposed`)
if (!proposed.length) {
  return { ok: true, status: 'no-patches-proposed', dryRun: DRY, codex_ran: reflect && reflect.codex_ran, reflect: reflect || null }
}

// ===========================================================================
// PHASE 3 — select: harness-director (judge) reads the rejection buffer, drops
// re-litigation, REJECTS Zone-2 new-flag / default-changing patches up front
// (before wasting gate time), classifies ownership, caps at edit_budget.
// ===========================================================================
phase('select')
const selection = await agent(
  `You are the ${DIRECTOR} — judge-only (you author NOTHING; you did not write these patches). Codex proposed the patches below. Do (Read), return per schema:

1. READ the rejection buffer ${BUFFER} if it exists (negative memory). DROP any patch re-litigating a previously-reverted one (same target + same intent) unless its content materially changed; record the buffer reason.
2. ZONE-2 GUARD: for any patch with zone=="zone2" (${ENGINE_REL}), DROP it immediately if is_new_flag==true OR it changes default (flag-OFF) behaviour — the engine is FROZEN; only a bug-fix that is inert when flags are OFF is eligible. Record the drop.
3. For each surviving patch classify ownership: "owned" = a script/engine fix the harness-director may self-apply + mirror; "escalate" = it touches commons protocol, CLAUDE.md, a trigger phrase, a hook, or other human-doctrine/config — propose only, the human applies.
4. Cap at edit_budget=${EDIT_BUDGET} (highest-impact first).

Patches:
${JSON.stringify(proposed, null, 2)}

Return per schema: selected[] (target/zone/ownership/rationale + the full patch object under "patch"), dropped[] (target/reason), edit_budget=${EDIT_BUDGET}.`,
  { label: 'select:director', phase: 'select', schema: SELECT_SCHEMA })
const selected = (selection && selection.selected) ? selection.selected : []
const dropped = (selection && selection.dropped) ? selection.dropped : []
log(`select: ${selected.length} selected, ${dropped.length} dropped`)
if (!selected.length) {
  return { ok: true, status: 'all-patches-dropped', dryRun: DRY, dropped, selection }
}

// ===========================================================================
// PHASE 4 — gate (per-patch pipeline): an EXECUTION-ONLY gate-runner proves
// red->green + static + live + (zone2) byte-identity in THROWAWAY temp copies
// (never the real corpus — safe even in dry-run); then the director ADJUDICATES
// the captured results. Gate is MANDATORY for every patch (no skip, no golden).
// Candidates are NOT parallelized — scripts share venv/sqlite/cwd state.
// ===========================================================================
phase('gate')
const gated = await pipeline(
  selected,
  (s) => agent(
    `You are a GATE-RUNNER — EXECUTION ONLY, no judgement. Prove this harness patch in THROWAWAY temp copies; NEVER edit anything under ${CLAUDE} or ${MIRROR}. Use a fresh temp dir.
Patch: ${JSON.stringify(s.patch)}
Steps (Bash, capture every command + cwd + exit + stdout/stderr excerpt):
1. Copy the target file(s) ${JSON.stringify(s.patch.files_touched)} into temp as the PRE copy. Write test_patch to a temp test file.
2. RED: run new_regression_command against the PRE copy — require it FAILS (expected: ${s.patch.expected_pre_failure}).
3. Apply fix_patch to the PRE copy -> POST copy. GREEN: run new_regression_command against POST — require it PASSES (expected: ${s.patch.expected_post_success}).
4. Run any existing harness/*-regress tests you can discover for this target (regressions_green=true if none exist).
5. STATIC: for Python run \`python -m py_compile\` + \`ruff check\` on the POST copy (static_clean=true iff no NEW diagnostics vs the PRE file's baseline). For ${ENGINE_REL} run an AsyncFunction-compile (NOT node --check — top-level await/return).
6. LIVE: if live_subprocess_command is set, run it (orchestration scripts only fail in a real subprocess; for adversary_lg classes use ${VENV_PY}). live_repro_pass accordingly; null if not applicable.
7. ZONE-2 byte-identity: if zone=="zone2", run a byte-identity-when-OFF proof using ${BYTEID_HARNESS} adapted to compare git HEAD vs the POST copy (copy the harness to temp, point it at the POST engine copy, set its FLAG/ACTIVATION_LABEL for this patch). byteid_off_pass = OFF call-logs identical. null for Zone-1.
Return per schema with captured (the audit trail) + proposed_verdict (pass iff red->green proven AND regressions_green AND static_clean AND (live_repro_pass!==false) AND (byteid_off_pass!==false)).`,
    { label: `gate:run:${s.target}`, phase: 'gate', schema: GATE_RUN_SCHEMA })
    .then(run => ({ sel: s, run })),
  (g) => agent(
    `You are the ${DIRECTOR} ADJUDICATING the executable gate for ONE harness patch (mirror of adversary -> supreme judge). The gate-runner CAPTURED these results — reason independently over the captured output, do NOT rubber-stamp its proposed_verdict. PASS iff: red->green is genuinely proven (the test FAILED pre and PASSED post — not a no-op test), existing regressions green, static clean, the live-subprocess repro passed where applicable, and for Zone-2 byte-identity-when-OFF holds. Any gap => fail.
Patch: ${JSON.stringify(g.sel.patch)}
Gate-runner results: ${JSON.stringify(g.run)}
Return per schema: target="${g.sel.target}", verdict (pass|fail), rationale.`,
    { label: `gate:judge:${g.sel.target}`, phase: 'gate', schema: GATE_VERDICT_SCHEMA })
    .then(v => ({ sel: g.sel, run: g.run, verdict: v })))
const gatedClean = gated.filter(Boolean)
const passed = gatedClean.filter(x => x.verdict && x.verdict.verdict === 'pass')
log(`gate: ${passed.length}/${gatedClean.length} patch(es) passed the executable gate`)

// ===========================================================================
// PHASE 5 — promote / escalate / reject (dry-run-aware; NEVER auto-pushes).
//   owned + PASS    -> apply to ~/.claude live; mirror side -> draft MR (stage-mr) | report (dry)
//   escalate + PASS -> human seam: draft-MR proposal note, never self-apply
//   FAIL            -> append to rejection buffer | report (dry)
// ===========================================================================
phase('promote')
const promotions = (await parallel(gatedClean.map(g => () => {
  const isPass = g.verdict && g.verdict.verdict === 'pass'
  const tgt = g.sel.target
  if (!isPass) {
    if (DRY) return Promise.resolve({ target: tgt, decision: 'reject', applied: false, ownership: g.sel.ownership, paths_written: [], rationale: `gate FAIL (dry-run: would buffer): ${g.verdict ? g.verdict.rationale : 'no verdict'}` })
    return agent(
      `You are the ${DIRECTOR}. This harness patch FAILED the executable gate. Append ONE entry to the rejection buffer ${BUFFER} (append-only; create if absent): "## <summary> | target: ${tgt} | <YYYY-MM-DD from ${TS}>" then "Tried:", "Reverted because: <gate fail>", "Status: GATE-FAIL". Modify NOTHING else. Return per schema (decision:'reject', applied:true, paths_written:["${BUFFER}"]).
Gate verdict: ${JSON.stringify(g.verdict)}`,
      { label: `reject:${tgt}`, phase: 'promote', schema: PROMOTE_SCHEMA })
  }
  if (g.sel.ownership === 'escalate') {
    if (DRY) return Promise.resolve({ target: tgt, decision: 'escalate-human', applied: false, ownership: 'escalate', paths_written: [], rationale: 'passed gate but touches commons/doctrine/config (dry-run: would write a draft-MR proposal note)' })
    return agent(
      `You are the ${DIRECTOR}. This patch PASSED the gate but touches commons protocol / CLAUDE.md / a trigger / a hook / config — you CANNOT self-apply. Write a DRAFT-MR PROPOSAL note to ${MEMORY}/harnessopt-escalation-${TS}.md — a reviewable artefact: the patch (target/anchor/content), the executable-gate verdict (red→green + byte-id-OFF), and a one-line ask that the human review and apply. Modify nothing else. Return per schema (decision:'escalate-human', applied:true, ownership:'escalate', paths_written:[the note]).
Patch: ${JSON.stringify(g.sel.patch)}`,
      { label: `escalate:${tgt}`, phase: 'promote', schema: PROMOTE_SCHEMA })
  }
  if (DRY) return Promise.resolve({ target: tgt, decision: 'promote', applied: false, ownership: 'owned', paths_written: [], rationale: `owned + gate PASS (dry-run: would apply fix_patch to ${CLAUDE}/${tgt} live; mirror side staged as a draft MR in the stage-mr phase; NO push)` })
  return agent(
    `You are the ${DIRECTOR}. This OWNED harness patch PASSED the executable gate. Apply it to the LIVE ${CLAUDE} working tree ONLY — do NOT touch the mirror here; the mirror side is staged as a draft MR later (stage-mr phase):
1. Apply fix_patch to ${CLAUDE}/${tgt} (match the "::<exact anchor>" EXACTLY via Edit; for the engine preserve byte-identity-when-OFF).
2. Read back the edited region to confirm.
Patch: ${JSON.stringify(g.sel.patch)}
Return per schema (decision:'promote', applied:true, ownership:'owned', paths_written:[the ~/.claude file], rationale).`,
    { label: `promote:${tgt}`, phase: 'promote', schema: PROMOTE_SCHEMA })
}))).filter(Boolean)
const nProm = promotions.filter(p => p.decision === 'promote').length
const nEsc = promotions.filter(p => p.decision === 'escalate-human').length
const nRej = promotions.filter(p => p.decision === 'reject').length
log(`promote: ${nProm} promote, ${nEsc} escalate-human, ${nRej} reject (dryRun=${DRY})`)

// ===========================================================================
// PHASE 5.5 — stage-mr: reroute OWNED promotions from a silent mirror copy to a
// reviewable DRAFT MR (promotion branch on the mirror + MR body). NEVER
// merges or pushes; the human reviews `git diff main..<branch>` + the body and
// merges = publish. Byte-identity-when-OFF is preserved for the engine.
// ===========================================================================
phase('stage-mr')
const ownedPassed = gatedClean.filter(g => g.verdict && g.verdict.verdict === 'pass' && g.sel.ownership === 'owned')
let draftMR = { staged: false, branch: '', body_path: '', files: [], detail: 'no owned promotion this cycle — no MR staged' }
if (ownedPassed.length) {
  const BR = `harnessopt/${TS}`
  const BODY = `${MEMORY}/promotions/${TS}-harness.md`
  if (DRY) {
    draftMR = { staged: false, branch: BR, body_path: BODY, files: ownedPassed.map(g => g.sel.target), detail: `dry-run: would stage ${ownedPassed.length} owned patch(es) as a draft MR (branch ${BR} on ${MIRROR} + MR body ${BODY}); no merge/push` }
  } else {
    draftMR = await agent(
      `You are the ${DIRECTOR} staging this cycle's OWNED gate-passed patches as a DRAFT MR on the blessed mirror ${MIRROR} (a git repo). Do NOT merge, do NOT git-push — publication is the human's step. Leave a reviewable branch + an MR body.
Run git via Bash (always with \`git -C ${MIRROR}\`):
1. \`git -C ${MIRROR} checkout -B ${BR}\` — promotion branch off current HEAD; main untouched.
2. For EACH patch below, apply the SAME fix as a surgical delta to ${MIRROR}/<target> (match "::<exact anchor>" via Edit). PRESERVE line-endings (CRLF vs LF); for the engine (workflows/engagement-workflow.js) PRESERVE byte-identity-when-OFF; edit in place rather than copying the whole file over. If a mirror path is absent, note it and skip (no stray files).
3. \`git -C ${MIRROR} add -A && git -C ${MIRROR} commit -m "harnessopt: draft ${TS}"\`, then \`git -C ${MIRROR} checkout main\` (main's working tree clean; the delta lives on ${BR}).
4. Write the MR body to ${BODY} (create ${MEMORY}/promotions/ if absent) — the review note (reasoning attached): a ## title, a Summary of the defect class closed, the (script x class) signals addressed, an "Ownership: owned" line, a Files+patches list, the executable-gate evidence (red->green proven + existing *-regress green + byte-id-OFF for the engine), a "Codex-authored / ${DIRECTOR}-judged" line, and a one-line merge-ask.
5. Confirm with \`git -C ${MIRROR} log --oneline -1 ${BR}\`.
Owned patches: ${JSON.stringify(ownedPassed.map(g => ({ target: g.sel.target, zone: g.sel.zone, patch: g.sel.patch, gate: g.verdict, run: g.run })))}
Return per schema: staged:true, branch:"${BR}", body_path:"${BODY}", files:[the mirror paths written], detail.`,
      { label: 'stage-mr', phase: 'stage-mr', schema: DRAFTMR_SCHEMA }) || draftMR
  }
}
log(`stage-mr: staged=${draftMR.staged} branch=${draftMR.branch || '(none)'}`)

// ===========================================================================
// PHASE 6 — record: append a "resolved (...)" line to each closed signal in the
// log (so harness-ready drops it) + a cycle note. Mixed script+skill traces get
// "resolved (SCRIPT half):" / "resolved (ENGINE...):" — NOT a generic "resolved:"
// (else SkillOpt's parser loses the still-open skill half). Skipped in dry-run.
// ===========================================================================
phase('record')
let record = { ran: false, resolved_signals: [], cycle_note_path: null, detail: 'dry-run or nothing promoted — no log writes' }
const promotedReal = promotions.filter(p => p.applied && p.decision === 'promote')
if (!DRY && promotedReal.length) {
  record = await agent(
    `You are the ${DIRECTOR} RECORDING a harness-evolution cycle in ${LOG}. For each PROMOTED patch below, append a partial-resolved line under its source signal block: \`resolved (SCRIPT half): ${'${'}YYYY-MM-DD from ${TS}${'}'} — <what was fixed; runtime red->green; py_compile/ruff/live-repro/byte-id status>\` for a script, or \`resolved (ENGINE...):\` for ${ENGINE_REL}. NEVER a bare "resolved:" on a mixed script+skill signal (it would hide the still-open skill half from SkillOpt). Then append a short cycle note. Modify only ${LOG}.
Promoted: ${JSON.stringify(promotedReal)}
Return per schema: ran:true, resolved_signals[] (the signal engagements/classes you marked), cycle_note_path, detail.`,
    { label: 'record:director', phase: 'record', schema: RECORD_SCHEMA }) || record
}
log(`record: ran=${record.ran}`)

return {
  ok: true,
  dryRun: DRY,
  editBudget: EDIT_BUDGET,
  codex_ran: !!(reflect && reflect.codex_ran),
  due: harvest.due,
  proposed: proposed.length,
  selected: selected.length,
  dropped,
  gate: gatedClean.map(g => ({ target: g.sel.target, zone: g.sel.zone, ownership: g.sel.ownership, verdict: g.verdict && g.verdict.verdict, red_green: g.run && g.run.red_green_proven, byteid_off: g.run && g.run.byteid_off_pass })),
  promotions,
  draftMR,
  record,
  humanSeam: promotions.filter(p => p.decision === 'escalate-human'),
}
