export const meta = {
  name: 'skillopt-workflow',
  description: 'SkillOpt / director skill-evolution cycle as a workflow: harvest due signals -> Codex AUTHORS bounded edits -> director SELECTS (rejection-buffer + edit_budget) -> per-edit golden GATE (Codex proposes pass/fail, director adjudicates) -> PROMOTE(domain-owned) | ESCALATE(commons = human seam) | REJECT(buffer) -> SLOW-UPDATE(high-blast only). Codex authors; the director judges (never the same brain). dryRun-safe (zero corpus/mirror/buffer writes). Out-of-band; NOT routed through agency-intake.',
  phases: [
    { title: 'harvest' }, { title: 'reflect' }, { title: 'select' },
    { title: 'gate' }, { title: 'promote' }, { title: 'slow-update' },
  ],
}

// ---------------------------------------------------------------------------
// params via args (defensive). The caller (system-improvement session / a
// *-director invocation) MUST supply domain, claudeDir, memoryDir, ts.
// ---------------------------------------------------------------------------
const A = (typeof args === 'string') ? JSON.parse(args) : (args || {})
const DOMAIN = A.domain                              // dev | design | marketing (required)
const CLAUDE = A.claudeDir                           // abs path to ~/.claude (working corpus)
const MEMORY = A.memoryDir                           // abs path to the memory dir (log / buffer / meta)
const TS = A.ts                                      // UTC timestamp "YYYYMMDDTHHMMSSZ" (Date.now banned in-script)
if (!DOMAIN || !CLAUDE || !MEMORY || !TS) {
  return { ok: false, error: 'skillopt-workflow requires args.domain, args.claudeDir, args.memoryDir, args.ts' }
}
const SCRIPTS = A.scriptsDir || (CLAUDE + '/scripts')
const MIRROR = A.mirrorDir || 'C:/releases/agentic-workflow'   // blessed best_skill mirror
const DRY = !!A.dryRun                               // dry-run: report would-actions, mutate NOTHING
const LOG = A.logPath || (MEMORY + '/skill-evolution-log.md')  // scratch log for smoke; else the real log
const NO_REFLECTIONS = !!A.noReflections             // smoke: Channel A (log) only
const FORCE_GATE = !!A.forceGate                     // run the gate even for low-blast (smoke proves the mechanic)
const EDIT_BUDGET = A.editBudget || 4                // L default per protocol (start 4-6)
const GOLDEN = `${CLAUDE}/skills/system-optimization-protocol/golden/${DOMAIN}`
const BUFFER = `${MEMORY}/skill-rejected-edits.md`
const META = `${MEMORY}/skill-evolution-meta.md`
const DIRECTOR = `${DOMAIN}-director`                // agentType for the judge-only steps

// ===========================================================================
// SCHEMAS
// ===========================================================================
const HARVEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ready', 'domain', 'due', 'signals', 'raw_tail'],
  properties: {
    ready: { type: 'boolean', description: 'true iff >=1 due cluster for THIS domain' },
    domain: { type: 'string' },
    due: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['class', 'count', 'kind'], properties: { class: { type: 'string' }, count: { type: 'integer' }, kind: { type: 'string', enum: ['log', 'reflection'] }, target: { type: ['string', 'null'] } } } },
    signals: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['engagement', 'failure_class', 'class_key', 'traced_to', 'evidence', 'target_kind'], properties: { engagement: { type: 'string' }, failure_class: { type: 'string' }, class_key: { type: 'string' }, traced_to: { type: 'string' }, evidence: { type: 'string' }, target_kind: { type: 'string', enum: ['skill_agent', 'script', 'other'] } } } },
    raw_tail: { type: 'string' },
  },
}
const REFLECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['codex_ran', 'reasoning', 'edits'],
  properties: {
    codex_ran: { type: 'boolean', description: 'true iff mcp__codex__codex actually returned' },
    reasoning: { type: 'string', description: "Codex's reasoning, relayed" },
    edits: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['op', 'target', 'content', 'failure_class', 'cross_check'], properties: {
      op: { type: 'string', enum: ['append', 'insert_after', 'replace', 'delete'] },
      target: { type: 'string', description: 'skills/X/SKILL.md or agents/Y.md, with ::<exact anchor> for insert_after/replace/delete' },
      content: { type: 'string', description: 'edit body (empty for delete)' },
      failure_class: { type: 'string' },
      cross_check: { type: 'string', description: 'which golden scenario / rule confirms the target CONTENT enforces the catch' },
    } } },
  },
}
const SELECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['selected', 'dropped', 'edit_budget'],
  properties: {
    selected: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['op', 'target', 'content', 'blast', 'ownership', 'rationale'], properties: {
      op: { type: 'string', enum: ['append', 'insert_after', 'replace', 'delete'] },
      target: { type: 'string' }, content: { type: 'string' },
      blast: { type: 'string', enum: ['high', 'low'] },
      ownership: { type: 'string', enum: ['owned', 'commons'] },
      rationale: { type: 'string' },
    } } },
    dropped: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'reason'], properties: { target: { type: 'string' }, reason: { type: 'string' } } } },
    edit_budget: { type: 'integer' },
  },
}
const GATE_PROPOSAL_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['codex_ran', 'proposed_verdict', 'per_scenario', 'reasoning'],
  properties: {
    codex_ran: { type: 'boolean' },
    proposed_verdict: { type: 'string', enum: ['pass', 'fail'] },
    per_scenario: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['scenario', 'assessment', 'note'], properties: { scenario: { type: 'string' }, assessment: { type: 'string', enum: ['pass', 'fail', 'na'] }, note: { type: 'string' } } } },
    reasoning: { type: 'string' },
  },
}
const GATE_VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['target', 'verdict', 'regression_risk', 'targeted_failure_closed', 'rationale'],
  properties: {
    target: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'fail'] },
    regression_risk: { type: 'string', enum: ['none', 'low', 'high'] },
    targeted_failure_closed: { type: 'boolean' },
    per_scenario: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['scenario', 'verdict', 'note'], properties: { scenario: { type: 'string' }, verdict: { type: 'string' }, note: { type: 'string' } } } },
    rationale: { type: 'string' },
  },
}
const PROMOTE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['target', 'decision', 'applied', 'ownership', 'paths_written', 'rationale'],
  properties: {
    target: { type: 'string' },
    decision: { type: 'string', enum: ['promote', 'escalate-human', 'reject'] },
    applied: { type: 'boolean', description: 'false in dry-run (would-action only)' },
    ownership: { type: 'string', enum: ['owned', 'commons'] },
    paths_written: { type: 'array', items: { type: 'string' } },
    rationale: { type: 'string' },
  },
}
const SLOWUPDATE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'buckets', 'blocked', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    buckets: { type: ['object', 'null'], additionalProperties: false, properties: { regressed: { type: 'integer' }, persistent_fail: { type: 'integer' }, improved: { type: 'integer' }, stable_success: { type: 'integer' } } },
    blocked: { type: 'boolean', description: 'true if regressed>0 (anti-forgetting block)' },
    detail: { type: 'string' },
  },
}

// ===========================================================================
// PHASE 1 — harvest: readiness (skillopt-ready.py) + the live signals for the
// due cluster(s) in THIS domain. dryrun/resolved are excluded by the checker
// AND re-confirmed here. Scratch log + --no-reflections isolate the smoke.
// ===========================================================================
phase('harvest')
const reflFlag = NO_REFLECTIONS ? '--no-reflections' : ''
const harvest = await agent(
  `You are the SkillOpt HARVEST step for domain="${DOMAIN}". Do TWO things (Bash + Read), return per schema.

1. READINESS — run: \`python ${SCRIPTS}/skillopt-ready.py --json --log "${LOG}" ${reflFlag}\`  (if "python" is missing, try "py -3"). IMPORTANT: this script exits 1 when a cycle IS DUE and 0 when none — exit 1 is NOT an error here; parse its stdout JSON regardless of exit code. It reports due[] (Channel A log clusters: {domain,class,count}), reflection_due[] (Channel B: {domain,target,class,count}) and ready.

2. SIGNALS — Read the log at ${LOG}. For EVERY due cluster whose domain=="${DOMAIN}" (from BOTH due[] and reflection_due[]), extract the LIVE signals belonging to it. A signal is LIVE iff its block has NO "dryrun: true" line AND NO "resolved:" line. For each live signal capture: engagement, the exact "Failure class:" text, its class_key (the stable slug — strip a trailing "(rule_token)"), the "Traced to:" target, the "Evidence:" pointer, and target_kind ("skill_agent" if Traced-to names skills/.. or agents/..; "script" if scripts/..; else "other").

Return per schema: ready (true iff >=1 due cluster for THIS domain), domain="${DOMAIN}", due[] (this domain only; kind="log" or "reflection"; target=null for log clusters), signals[] (the live signals for those clusters), raw_tail (last ~600 chars of the skillopt-ready JSON).`,
  { label: 'harvest', phase: 'harvest', schema: HARVEST_SCHEMA })
if (!harvest || !harvest.ready) {
  return { ok: true, status: 'no-cycle-due', domain: DOMAIN, dryRun: DRY, harvest: harvest || null }
}
log(`harvest: ${harvest.due.length} due cluster(s) for ${DOMAIN}; ${harvest.signals.length} live signal(s)`)

// ===========================================================================
// PHASE 2 — reflect: Codex AUTHORS the bounded edit list (cross-family). The
// orchestrating agent is a faithful RELAY, never an author (defend-bias is the
// failure this separation prevents). The director does NOT appear here.
// ===========================================================================
phase('reflect')
const reflect = await agent(
  `You ORCHESTRATE Codex (cross-family) as the edit PROPOSER for a ${DOMAIN} SkillOpt cycle. You do NOT author or improve edits yourself — defend-bias is exactly what this Codex-authors / director-judges separation prevents.

Call mcp__codex__codex (load it via tool search if its schema is not loaded) with: approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}". Give Codex a prompt containing:
- The due failure signals below (each with its Traced-to target + Evidence).
- The task: classify each recurring pattern and attribute it to a SPECIFIC skills/X/SKILL.md or agents/Y.md under ${CLAUDE}. Op by taxonomy: rule_missing -> append / insert_after; rule_wrong -> replace; rule_ignored -> a STRUCTURAL fix (raise it / make it a gate / tighten emphasis), NEVER just more text. Plus the ${DOMAIN} domain failure types from the ${DIRECTOR} taxonomy.
- CROSS-CHECK rule (load-bearing): before emitting each edit, Codex MUST verify the target file's CONTENT is what would ENFORCE the catch (the rule/validator that PRODUCES the catching artefact) by reading the relevant golden scenario(s) under ${GOLDEN}/ — NOT the producer of the buggy output. A wrong trace yields a right-pattern / wrong-file edit the gate will reject.
- Edit format: {"reasoning": "...", "edits": [{"op": "append|insert_after|replace|delete", "target": "skills/..|agents/.. (with ::<exact anchor> for insert_after/replace/delete)", "content": "..."}]}. At most ${EDIT_BUDGET} edits. An EMPTY edits list is a valid output (nothing warranted).

Due signals:
${JSON.stringify(harvest.signals, null, 2)}

Then RELAY Codex's proposal into the schema faithfully — do NOT author, expand, or "fix" the edits; if Codex wraps JSON in prose, extract the JSON; for each edit copy Codex's failure_class and its cross_check note. Set codex_ran=true iff mcp__codex__codex actually returned a result. If Codex proposed nothing, return edits:[].`,
  { label: 'reflect:codex', phase: 'reflect', schema: REFLECT_SCHEMA })
const proposed = (reflect && reflect.edits) ? reflect.edits : []
log(`reflect: codex_ran=${reflect && reflect.codex_ran}; ${proposed.length} edit(s) proposed`)
if (!proposed.length) {
  return { ok: true, status: 'no-edits-proposed', domain: DOMAIN, dryRun: DRY, codex_ran: reflect && reflect.codex_ran, reflect: reflect || null }
}

// ===========================================================================
// PHASE 3 — select: director (judge) reads the rejection buffer, drops
// re-litigated edits, classifies blast + ownership, caps at edit_budget.
// ===========================================================================
phase('select')
const selection = await agent(
  `You are the ${DIRECTOR} — judge-only system-optimizer (you author NOTHING; you did not write these edits). Codex proposed the edits below for a ${DOMAIN} SkillOpt cycle. Do THREE things (Read), return per schema:

1. READ the rejection buffer ${BUFFER} (negative memory — MANDATORY). DROP any proposed edit that re-litigates a previously-reverted edit (same target + same intent) unless its content materially changed; record each drop with the buffer reason it matches.
2. For each surviving edit classify:
   - blast: "high" if the target is a lead / manager / director agent, a COMMONS file, or a widely-loaded skill; else "low". (Use the blast-radius table in system-optimization-protocol.)
   - ownership: "owned" = a ${DOMAIN}-domain file you may self-promote; "commons" = a shared file you may only PROPOSE (the human promotes). Use your "Domain-owned vs commons" boundary.
3. Cap accepted edits at edit_budget=${EDIT_BUDGET} (highest-impact first).

Proposed edits:
${JSON.stringify(proposed, null, 2)}

Return per schema: selected[] (op/target/content/blast/ownership/rationale), dropped[] (target/reason), edit_budget=${EDIT_BUDGET}.`,
  { label: 'select:director', phase: 'select', schema: SELECT_SCHEMA })
const selected = (selection && selection.selected) ? selection.selected : []
const dropped = (selection && selection.dropped) ? selection.dropped : []
log(`select: ${selected.length} selected, ${dropped.length} dropped`)
if (!selected.length) {
  return { ok: true, status: 'all-edits-dropped', domain: DOMAIN, dryRun: DRY, dropped, selection }
}

// ===========================================================================
// PHASE 4 — gate (per-edit pipeline): Codex proposes a pass/fail read over the
// golden scenarios; the director ADJUDICATES (mirror of adversary -> supreme
// judge). NO patch is applied — pure rubric reasoning. Blast-tiered: high =
// mandatory; low = optional unless forceGate.
// ===========================================================================
phase('gate')
function skipVerdict() { return { verdict: 'pass', regression_risk: 'low', targeted_failure_closed: true, rationale: 'low-blast; golden gate optional per protocol and not forced' } }
const gated = await pipeline(
  selected,
  (e) => {
    const runGate = (e.blast === 'high') || FORCE_GATE
    if (!runGate) return { edit: e, skipped: true, proposal: null, verdict: skipVerdict() }
    return agent(
      `You ORCHESTRATE Codex to propose a GATE read for ONE candidate ${DOMAIN} skill/agent edit. NO patch is applied — this is rubric reasoning over the golden scenarios. You relay Codex's read; you do not decide here.
Call mcp__codex__codex (approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}") asking Codex to: read EVERY golden scenario file under ${GOLDEN}/ and the proposed edit (and, if it helps, the current target file under ${CLAUDE}); for each scenario judge whether the edited skill/agent STILL satisfies that scenario's Pass-criteria (no regression) AND whether the targeted failure is now closed; output JSON {"proposed_verdict":"pass|fail","per_scenario":[{"scenario":"NN-slug","assessment":"pass|fail|na","note":"..."}],"reasoning":"..."}.
Proposed edit: ${JSON.stringify(e)}
RELAY Codex's read into the schema (do NOT substitute your own verdict). codex_ran=true iff Codex returned.`,
      { label: `gate:codex:${e.target}`, phase: 'gate', schema: GATE_PROPOSAL_SCHEMA })
      .then(prop => ({ edit: e, skipped: false, proposal: prop }))
  },
  (g) => {
    if (g.skipped) return g
    return agent(
      `You are the ${DIRECTOR} ADJUDICATING the golden gate for ONE ${DOMAIN} edit. Codex proposed the pass/fail read (below); YOU decide (mirror of adversary -> supreme judge). Read the golden scenarios under ${GOLDEN}/ and the edit; weigh Codex's proposal but reason independently. PASS iff NO scenario regresses AND the targeted failure is closed. A right-pattern / wrong-file edit (F2) FAILS.
Edit: ${JSON.stringify(g.edit)}
Codex gate proposal: ${JSON.stringify(g.proposal)}
Return per schema: target="${g.edit.target}", verdict (pass|fail), regression_risk (none|low|high), targeted_failure_closed (bool), per_scenario[], rationale.`,
      { label: `gate:judge:${g.edit.target}`, phase: 'gate', schema: GATE_VERDICT_SCHEMA })
      .then(v => ({ edit: g.edit, skipped: false, proposal: g.proposal, verdict: v }))
  })
const gatedClean = gated.filter(Boolean)
const passed = gatedClean.filter(x => x.verdict && x.verdict.verdict === 'pass')
log(`gate: ${passed.length}/${gatedClean.length} edit(s) passed`)

// ===========================================================================
// PHASE 5 — promote / escalate / reject (dry-run-aware).
//   owned + PASS    -> apply to ~/.claude + blessed mirror (real) | report (dry)
//   commons + PASS  -> HUMAN SEAM: write escalation note, never self-apply
//   FAIL            -> append to rejection buffer (real) | report (dry)
// ===========================================================================
phase('promote')
const promotions = (await parallel(gatedClean.map(g => () => {
  const v = g.verdict
  const isPass = v && v.verdict === 'pass'
  if (!isPass) {
    if (DRY) return Promise.resolve({ target: g.edit.target, decision: 'reject', applied: false, ownership: g.edit.ownership, paths_written: [], rationale: `gate FAIL (dry-run: would append to rejection buffer): ${v ? v.rationale : 'no verdict'}` })
    return agent(
      `You are the ${DIRECTOR}. This ${DOMAIN} edit FAILED the golden gate. Append ONE rejection-buffer entry to ${BUFFER} (append-only) per its schema: "## <summary> | target: ${g.edit.target} | domain: ${DOMAIN === 'dev' || DOMAIN === 'design' || DOMAIN === 'marketing' ? (g.edit.ownership === 'commons' ? 'commons' : DOMAIN) : DOMAIN} | <YYYY-MM-DD from ${TS}>" then "Tried:", "Reverted because:", "Status: GATE-FAIL". Do NOT modify any skill/agent or the mirror. Return per schema (decision:'reject', applied:true, paths_written:["${BUFFER}"]).
Edit: ${JSON.stringify(g.edit)}
Gate verdict: ${JSON.stringify(v)}`,
      { label: `reject:${g.edit.target}`, phase: 'promote', schema: PROMOTE_SCHEMA })
  }
  if (g.edit.ownership === 'commons') {
    if (DRY) return Promise.resolve({ target: g.edit.target, decision: 'escalate-human', applied: false, ownership: 'commons', paths_written: [], rationale: 'commons edit passed the gate (dry-run: would write a human-escalation note; commons is NEVER self-promoted)' })
    return agent(
      `You are the ${DIRECTOR}. This COMMONS edit PASSED the gate, but per system-optimization-protocol governance you CANNOT self-promote a commons file. Write a human-escalation note to ${MEMORY}/skillopt-escalation-${DOMAIN}-${TS}.md containing: the proposed edit (op/target/content), the gate verdict, and a one-line ask that the human commons-maintainer decides. Do NOT modify the commons file or the mirror. Return per schema (decision:'escalate-human', applied:true, ownership:'commons', paths_written:[the note path], rationale).
Edit: ${JSON.stringify(g.edit)}
Gate verdict: ${JSON.stringify(v)}`,
      { label: `escalate:${g.edit.target}`, phase: 'promote', schema: PROMOTE_SCHEMA })
  }
  if (DRY) return Promise.resolve({ target: g.edit.target, decision: 'promote', applied: false, ownership: 'owned', paths_written: [], rationale: `domain-owned + gate PASS (dry-run: would apply ${g.edit.op} to ${CLAUDE}/${g.edit.target} and mirror to ${MIRROR}/${g.edit.target})` })
  return agent(
    `You are the ${DIRECTOR}. This DOMAIN-OWNED edit PASSED the gate. Apply it and promote to the blessed mirror:
1. Apply ${g.edit.op} to ${CLAUDE}/${g.edit.target}. For insert_after/replace/delete the target carries "::<exact anchor>" — match it EXACTLY (Edit). For append, append to file end. For a brand-new heading use insert_after on an existing anchor.
2. Promote the SAME change to ${MIRROR}/${g.edit.target} (the blessed best_skill). PRESERVE that file's existing line-endings (CRLF vs LF) — match the committed blob, do not reflow the whole file.
3. Read back both edited regions to confirm.
Edit: ${JSON.stringify(g.edit)}
Return per schema (decision:'promote', applied:true, ownership:'owned', paths_written:[the 2 files], rationale).`,
    { label: `promote:${g.edit.target}`, phase: 'promote', schema: PROMOTE_SCHEMA })
}))).filter(Boolean)
const nProm = promotions.filter(p => p.decision === 'promote').length
const nEsc = promotions.filter(p => p.decision === 'escalate-human').length
const nRej = promotions.filter(p => p.decision === 'reject').length
log(`promote: ${nProm} promote, ${nEsc} escalate-human, ${nRej} reject (dryRun=${DRY})`)

// ===========================================================================
// PHASE 6 — slow-update (anti-forgetting; high-blast domain-owned promotions
// only). Re-run the golden set pre/post, 4-bucket; regressed>0 blocks.
// ===========================================================================
phase('slow-update')
const promotedHigh = gatedClean.filter(g => g.verdict && g.verdict.verdict === 'pass' && g.edit.blast === 'high' && g.edit.ownership === 'owned')
let slowUpdate = { ran: false, buckets: null, blocked: false, detail: 'no high-blast domain-owned promotion this cycle — slow-update not required' }
if (promotedHigh.length) {
  if (DRY) {
    slowUpdate = { ran: false, buckets: null, blocked: false, detail: `${promotedHigh.length} high-blast promotion(s) present but dry-run — slow-update would re-baseline the golden set in a real cycle` }
  } else {
    const su = await agent(
      `You are the ${DIRECTOR} running SLOW-UPDATE (anti-forgetting) after ${promotedHigh.length} high-blast domain-owned promotion(s) in ${DOMAIN}. Re-run the golden set under ${GOLDEN}/ as a rubric read on the POST-edit corpus and compare to each scenario's "Expected behavior" baseline. Categorise EACH scenario: regressed (was-good->now-bad), persistent_fail (bad->bad), improved (bad->good), stable_success (good->good). regressed>0 BLOCKS the cycle (flag for rollback of the offending edit).
Promoted edits: ${JSON.stringify(promotedHigh.map(g => g.edit))}
Return per schema: ran:true, buckets {regressed,persistent_fail,improved,stable_success}, blocked (regressed>0), detail.`,
      { label: 'slow-update', phase: 'slow-update', schema: SLOWUPDATE_SCHEMA })
    slowUpdate = su || slowUpdate
  }
}
log(`slow-update: ran=${slowUpdate.ran} blocked=${slowUpdate.blocked}`)

// ---- SEAM ----
// Commons edits that passed the gate STOP here for the human commons-maintainer
// (mirror of the engagement handoff seam — consistent with Decision B). The
// human consumes humanSeam[] + the escalation notes and decides the commons edit.
return {
  ok: true,
  domain: DOMAIN,
  dryRun: DRY,
  forceGate: FORCE_GATE,
  editBudget: EDIT_BUDGET,
  codex_ran: !!(reflect && reflect.codex_ran),
  due: harvest.due,
  proposed: proposed.length,
  selected: selected.length,
  dropped,
  gate: gatedClean.map(g => ({ target: g.edit.target, blast: g.edit.blast, ownership: g.edit.ownership, skipped: !!g.skipped, gate_codex_ran: g.proposal ? g.proposal.codex_ran : null, verdict: g.verdict && g.verdict.verdict, regression_risk: g.verdict && g.verdict.regression_risk, targeted_failure_closed: g.verdict && g.verdict.targeted_failure_closed })),
  promotions,
  slowUpdate,
  humanSeam: promotions.filter(p => p.decision === 'escalate-human'),
}
