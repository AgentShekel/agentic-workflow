export const meta = {
  name: 'skillopt-workflow',
  description: 'SkillOpt / director skill-evolution cycle as a workflow: harvest due signals + success fuel -> Codex AUTHORS bounded edits on BOTH channels (corrective + reinforcement) -> director SELECTS (failure-first merge, rejection-buffer, support_count, edit_budget) -> per-edit golden GATE (Codex proposes pass/fail, director adjudicates) -> snapshot + PROMOTE(domain-owned) | ESCALATE(commons = human seam) | REJECT(buffer) -> DIFF-GUARD (no write outside the declared targets) -> SLOW-UPDATE(high-blast; a regression ROLLS BACK from the snapshot and blocks the MR) -> stage draft MR -> RECORD (resolved lines + cycle note) -> META (optimizer-side memory for the next cycle). Codex authors; the director judges (never the same brain). dryRun-safe (zero corpus/mirror/buffer writes). Out-of-band; NOT routed through agency-intake.',
  phases: [
    { title: 'harvest' }, { title: 'reflect' }, { title: 'select' },
    { title: 'gate' }, { title: 'promote' }, { title: 'slow-update' }, { title: 'stage-mr' },
    { title: 'record' }, { title: 'meta' },
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
const NO_SUCCESS = !!A.noSuccess                     // smoke: skip Channel C (reinforcement)
const FORCE_GATE = !!A.forceGate                     // run the gate even for low-blast (smoke proves the mechanic)
const EDIT_BUDGET = A.editBudget || 4                // L default per protocol (start 4-6)
const GOLDEN = `${CLAUDE}/skills/system-optimization-protocol/golden/${DOMAIN}`
const BUFFER = `${MEMORY}/skill-rejected-edits.md`
const META = `${MEMORY}/skill-evolution-meta.md`
const SNAPSHOTS = `${MEMORY}/skillopt-snapshots/${TS}`  // pre-edit copies = the rollback target
const DIRECTOR = `${DOMAIN}-director`                // agentType for the judge-only steps

// ===========================================================================
// SCHEMAS
// ===========================================================================
const HARVEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ready', 'domain', 'due', 'signals', 'success_due', 'success_signals', 'raw_tail'],
  properties: {
    ready: { type: 'boolean', description: 'true iff >=1 due cluster for THIS domain (A/B only — success never triggers)' },
    domain: { type: 'string' },
    due: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['class', 'count', 'kind'], properties: { class: { type: 'string' }, count: { type: 'integer' }, kind: { type: 'string', enum: ['log', 'reflection'] }, target: { type: ['string', 'null'] } } } },
    signals: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['engagement', 'failure_class', 'class_key', 'traced_to', 'evidence', 'target_kind'], properties: { engagement: { type: 'string' }, failure_class: { type: 'string' }, class_key: { type: 'string' }, traced_to: { type: 'string' }, evidence: { type: 'string' }, target_kind: { type: 'string', enum: ['skill_agent', 'script', 'other'] } } } },
    success_due: { type: 'array', description: 'Channel C clusters for THIS domain (>=2 worked-reflections on one target/class)', items: { type: 'object', additionalProperties: false, required: ['target', 'class', 'count'], properties: { target: { type: 'string' }, class: { type: 'string' }, count: { type: 'integer' } } } },
    success_signals: { type: 'array', description: 'the worked-records behind those clusters, relayed verbatim from the checker', items: { type: 'object', additionalProperties: false, required: ['engagement', 'pattern_class', 'primary_target'], properties: { engagement: { type: ['string', 'null'] }, pattern_class: { type: 'string' }, class_key: { type: 'string' }, primary_target: { type: 'string' }, target: { type: 'string' }, source_file: { type: ['string', 'null'] }, date: { type: ['string', 'null'] } } } },
    raw_tail: { type: 'string' },
  },
}
// One schema for BOTH reflect channels. `source_type` is what the select step's
// failure-first merge rule keys on; `support_count` is how many distinct signals back the
// edit, so the budget cut has a number under it and not only prose.
const REFLECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['codex_ran', 'reasoning', 'edits'],
  properties: {
    codex_ran: { type: 'boolean', description: 'true iff mcp__codex__codex actually returned' },
    reasoning: { type: 'string', description: "Codex's reasoning, relayed" },
    edits: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['op', 'target', 'content', 'pattern_class', 'source_type', 'support_count', 'cross_check'], properties: {
      op: { type: 'string', enum: ['append', 'insert_after', 'replace', 'delete'] },
      target: { type: 'string', description: 'skills/X/SKILL.md or agents/Y.md, with ::<exact anchor> for insert_after/replace/delete' },
      content: { type: 'string', description: 'edit body (empty for delete)' },
      pattern_class: { type: 'string', description: 'the failure class (corrective) or the reinforcement slug (success)' },
      source_type: { type: 'string', enum: ['failure', 'success'] },
      support_count: { type: 'integer', description: 'how many distinct signals in the batch back this edit' },
      cross_check: { type: 'string', description: 'which golden scenario / rule confirms the target CONTENT enforces the catch' },
    } } },
  },
}
const SELECT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['selected', 'dropped', 'edit_budget', 'ranking_note'],
  properties: {
    selected: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['op', 'target', 'content', 'blast', 'ownership', 'source_type', 'support_count', 'rationale'], properties: {
      op: { type: 'string', enum: ['append', 'insert_after', 'replace', 'delete'] },
      target: { type: 'string' }, content: { type: 'string' },
      blast: { type: 'string', enum: ['high', 'low'] },
      ownership: { type: 'string', enum: ['owned', 'commons'] },
      source_type: { type: 'string', enum: ['failure', 'success'] },
      support_count: { type: 'integer' },
      pattern_class: { type: 'string' },
      rationale: { type: 'string' },
    } } },
    dropped: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'reason'], properties: { target: { type: 'string' }, reason: { type: 'string' } } } },
    edit_budget: { type: 'integer' },
    ranking_note: { type: 'string', description: 'why this order — the criteria that decided the budget cut' },
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
const SNAPSHOT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['taken', 'dir', 'files', 'baseline_dirty', 'detail'],
  properties: {
    taken: { type: 'boolean' },
    dir: { type: 'string' },
    files: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['target', 'copy'], properties: { target: { type: 'string' }, copy: { type: 'string' } } } },
    baseline_dirty: { type: 'array', items: { type: 'string' }, description: 'files already modified in ~/.claude BEFORE this cycle touched anything' },
    detail: { type: 'string' },
  },
}
const DIFFGUARD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'clean', 'newly_touched', 'violations', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    clean: { type: 'boolean', description: 'true iff every newly-touched path was a declared target or an allowed side-effect' },
    newly_touched: { type: 'array', items: { type: 'string' } },
    violations: { type: 'array', items: { type: 'string' } },
    detail: { type: 'string' },
  },
}
const ROLLBACK_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'restored', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    restored: { type: 'array', items: { type: 'string' } },
    detail: { type: 'string' },
  },
}
const RECORD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'resolved_signals', 'cycle_note_path', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    resolved_signals: { type: 'array', items: { type: 'string' } },
    cycle_note_path: { type: ['string', 'null'] },
    detail: { type: 'string' },
  },
}
const META_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'lessons', 'line_count', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    lessons: { type: 'array', items: { type: 'string' }, description: 'the process/content lessons written this cycle' },
    line_count: { type: 'integer', description: 'total lines of the meta file after the write (cap ~150)' },
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
const succFlag = NO_SUCCESS ? '--no-success' : ''
const harvest = await agent(
  `You are the SkillOpt HARVEST step for domain="${DOMAIN}". Do THREE things (Bash + Read), return per schema.

1. READINESS — run: \`python ${SCRIPTS}/skillopt-ready.py --json --log "${LOG}" --domain ${DOMAIN} ${reflFlag} ${succFlag}\`  (if "python" is missing, try "py -3"). IMPORTANT: this script exits 1 when a cycle IS DUE and 0 when none — exit 1 is NOT an error here; parse its stdout JSON regardless of exit code. It reports due[] (Channel A log clusters: {domain,class,count}), reflection_due[] (Channel B: {domain,target,class,count}), success_due[] + success_signals[] (Channel C) and ready.

2. SIGNALS — Read the log at ${LOG}. For EVERY due cluster whose domain=="${DOMAIN}" (from BOTH due[] and reflection_due[]), extract the LIVE signals belonging to it. A signal is LIVE iff its block has NO "dryrun: true" line AND NO "resolved:" line. For each live signal capture: engagement, the exact "Failure class:" text, its class_key (the stable slug — strip a trailing "(rule_token)"), the "Traced to:" target, the "Evidence:" pointer, and target_kind ("skill_agent" if Traced-to names skills/.. or agents/..; "script" if scripts/..; else "other").

3. SUCCESS FUEL — relay success_due[] and success_signals[] for domain=="${DOMAIN}" from the SAME JSON, verbatim. Read NOTHING extra for this: the checker already walked the reflection tree. If the key is absent or empty, return empty arrays. This channel NEVER decides readiness — it only rides along so the reflect step has something to reinforce.

Return per schema: ready (true iff >=1 due cluster for THIS domain — from due[]/reflection_due[] ONLY, never from success_due), domain="${DOMAIN}", due[] (this domain only; kind="log" or "reflection"; target=null for log clusters), signals[] (the live signals for those clusters), success_due[], success_signals[], raw_tail (last ~600 chars of the skillopt-ready JSON).`,
  { label: 'harvest', phase: 'harvest', schema: HARVEST_SCHEMA })
if (!harvest || !harvest.ready) {
  return { ok: true, status: 'no-cycle-due', domain: DOMAIN, dryRun: DRY, harvest: harvest || null }
}
const successSignals = (harvest.success_signals || []).filter(s => !NO_SUCCESS)
log(`harvest: ${harvest.due.length} due cluster(s) for ${DOMAIN}; ${harvest.signals.length} live signal(s); ${successSignals.length} success record(s) in ${(harvest.success_due || []).length} cluster(s)`)

// ===========================================================================
// PHASE 2 — reflect: Codex AUTHORS the bounded edit list (cross-family). The
// orchestrating agent is a faithful RELAY, never an author (defend-bias is the
// failure this separation prevents). The director does NOT appear here.
//
// TWO channels run side by side, as SkillOpt does: a corrective one over the due
// failure signals, and — only when Channel C carried fuel — a reinforcement one over
// what demonstrably worked. Success analysis is deliberately conservative (tighten
// what exists, never add a top-level rule) and it LOSES every conflict at select.
// Without it, each cycle can only add suspicion, and the corpus ratchets one way.
//
// Both calls are handed the optimizer-side meta memory. It used to be a declared
// constant this script never read, so every cycle re-learned what the last one knew.
// ===========================================================================
phase('reflect')
const metaBlock = `\n\nOPTIMIZER MEMORY — before proposing, Read ${META} (it may not exist; that is fine). It is optimizer-side memory from earlier cycles: which kinds of edit helped in this domain, which were too vague, brittle or redundant, and which regressions to guard against. Pass its "Shared process" section and its "${DOMAIN}" section to Codex as context. Prefer it when the current evidence is ambiguous; do NOT force a past lesson when this batch's signals plainly contradict it.`

const reflectCalls = [
  () => agent(
    `You ORCHESTRATE Codex (cross-family) as the CORRECTIVE edit PROPOSER for a ${DOMAIN} SkillOpt cycle. You do NOT author or improve edits yourself — defend-bias is exactly what this Codex-authors / director-judges separation prevents.

Call mcp__codex__codex (load it via tool search if its schema is not loaded) with: approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}". Give Codex a prompt containing:
- The due failure signals below (each with its Traced-to target + Evidence).
- The task: classify each recurring pattern and attribute it to a SPECIFIC skills/X/SKILL.md or agents/Y.md under ${CLAUDE}. Op by taxonomy: rule_missing -> append / insert_after; rule_wrong -> replace; rule_ignored -> a STRUCTURAL fix (raise it / make it a gate / tighten emphasis), NEVER just more text. Plus the ${DOMAIN} domain failure types from the ${DIRECTOR} taxonomy.
- COMMON PATTERNS ONLY: propose against a pattern shared by the batch, never a single trajectory. Report support_count per edit = how many of the signals below it addresses.
- CROSS-CHECK rule (load-bearing): before emitting each edit, Codex MUST verify the target file's CONTENT is what would ENFORCE the catch (the rule/validator that PRODUCES the catching artefact) by reading the relevant golden scenario(s) under ${GOLDEN}/ — NOT the producer of the buggy output. A wrong trace yields a right-pattern / wrong-file edit the gate will reject.
- Edit format: {"reasoning": "...", "edits": [{"op": "append|insert_after|replace|delete", "target": "skills/..|agents/.. (with ::<exact anchor> for insert_after/replace/delete)", "content": "...", "pattern_class": "<the failure class>", "support_count": <int>}]}. At most ${EDIT_BUDGET} edits. An EMPTY edits list is a valid output (nothing warranted).${metaBlock}

Due signals:
${JSON.stringify(harvest.signals, null, 2)}

Then RELAY Codex's proposal into the schema faithfully — do NOT author, expand, or "fix" the edits; if Codex wraps JSON in prose, extract the JSON; for each edit copy Codex's pattern_class, support_count and cross_check note, and set source_type="failure". Set codex_ran=true iff mcp__codex__codex actually returned a result. If Codex proposed nothing, return edits:[].`,
    { label: 'reflect:codex:failure', phase: 'reflect', schema: REFLECT_SCHEMA }),
]
if (successSignals.length) {
  reflectCalls.push(() => agent(
    `You ORCHESTRATE Codex (cross-family) as the REINFORCEMENT edit PROPOSER for a ${DOMAIN} SkillOpt cycle. Same rule as the corrective channel: you RELAY, you never author.

These are Channel C records — behaviours that CARRIED an engagement, each seen on at least two of them. This channel exists because every other input to this loop is a failure, so without it every cycle can only make the corpus more suspicious.

Call mcp__codex__codex (approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}") and ask it to propose edits that ENCODE these patterns, under HARD constraints:
- Only patterns NOT already covered by the target file. Read the file first; if the rule is already there, propose nothing for it.
- Prefer TIGHTENING an existing section over adding a new top-level heading. A reinforcement edit that grows the file is usually the wrong edit.
- The pattern must generalise. A behaviour that worked because of one engagement's specifics is not a rule.
- Be willing to return an empty list. Silence is the correct output when the corpus already says it.
- Edit format: {"reasoning": "...", "edits": [{"op": "append|insert_after|replace|delete", "target": "skills/..|agents/.. (with ::<exact anchor>)", "content": "...", "pattern_class": "<the reinforcement slug>", "support_count": <how many of the records below back it>}]}. At most ${EDIT_BUDGET} edits.${metaBlock}

Success records:
${JSON.stringify(successSignals, null, 2)}

RELAY faithfully into the schema with source_type="success" on every edit; cross_check = the golden scenario (or the file section) confirming the target already governs this behaviour. codex_ran=true iff Codex returned.`,
    { label: 'reflect:codex:success', phase: 'reflect', schema: REFLECT_SCHEMA }))
}
// NOT `.filter(Boolean)` before indexing. parallel() puts a null in the FAILED thunk's own
// position, so filtering first slides the success result into slot 0, where the next two
// lines stamp it source_type:"failure" — the reinforcement edit then gets judged by the
// corrective gate test ("is the targeted failure closed?"), which cannot apply to it.
const reflectResults = await parallel(reflectCalls)
const reflect = reflectResults[0] || null
const successReflect = reflectResults[1] || null
const failureEdits = (reflect && reflect.edits) ? reflect.edits.map(e => ({ ...e, source_type: 'failure' })) : []
const successEdits = (successReflect && successReflect.edits) ? successReflect.edits.map(e => ({ ...e, source_type: 'success' })) : []
const proposed = failureEdits.concat(successEdits)
log(`reflect: codex_ran=${reflect && reflect.codex_ran}; ${failureEdits.length} corrective + ${successEdits.length} reinforcement edit(s) proposed`)
// A null cycle MUST leave a trace. Without one, "Codex looked and found nothing to fix"
// is byte-identical on disk to "nobody ever ran a cycle": the workflow returns, writes
// nothing, and skillopt-ready.py re-fires the same cluster DUE forever. The harness loop
// carries an `adjudicated:` line for exactly this case; the skill loop needs the same one.
// A trigger that is always on stops being read.
//
// `adjudicated:` is deliberately NOT `resolved:` — nothing was fixed, and skillopt-ready
// only strips `resolved:`, so the signal stays live and keeps counting. One new signal
// joining the cluster therefore re-fires it immediately.
async function adjudicateNullCycle(reason, detailPayload) {
  if (DRY || !harvest.due.length) {
    return { ran: false, resolved_signals: [], cycle_note_path: null, detail: `dry-run or no due cluster — no log writes (${reason})` }
  }
  return await agent(
    `You are the ${DIRECTOR} closing a NULL ${DOMAIN} SkillOpt cycle in ${LOG}.

Outcome: ${reason}. That verdict has to land in the log, or the readiness trigger keeps firing on this same cluster forever.

For EACH signal belonging to a due cluster below, append ONE line to its signal block:

  adjudicated: <YYYY-MM-DD from ${TS}> | skillopt cycle ${TS} | no-edit. <why THIS signal produced no edit, from the actual reasoning below>. <one clause on what would reopen it>.

Rules:
- Do NOT write \`resolved:\` — nothing was fixed and the gap still stands.
- Append only. Do not edit, soften or delete anything already in the log.
- Use the ACTUAL reasoning. If one reason covers several signals, say so rather than inventing a distinct-sounding reason per signal.
- Modify only ${LOG}.

Due clusters: ${JSON.stringify(harvest.due)}
Signals: ${JSON.stringify(harvest.signals, null, 2)}
Reasoning (verbatim): ${JSON.stringify(detailPayload)}

Return per schema: ran:true, resolved_signals[] (the signals you marked adjudicated), cycle_note_path:null, detail.`,
    { label: 'adjudicate:director', phase: 'record', schema: RECORD_SCHEMA })
    || { ran: false, resolved_signals: [], cycle_note_path: null, detail: 'adjudication agent returned nothing' }
}

if (!proposed.length) {
  const adjudication = await adjudicateNullCycle(
    'Codex proposed zero edits on both channels',
    { failure: (reflect && reflect.reasoning) || '', success: (successReflect && successReflect.reasoning) || '' })
  log(`null cycle: adjudication ran=${adjudication.ran}`)
  return { ok: true, status: 'no-edits-proposed', domain: DOMAIN, dryRun: DRY, codex_ran: reflect && reflect.codex_ran, adjudication, reflect: reflect || null, successReflect }
}

// ===========================================================================
// PHASE 3 — select: director (judge) merges the two channels failure-first, reads
// the rejection buffer, drops re-litigated edits, classifies blast + ownership,
// then RANKS on stated criteria before the budget cut. The ranking used to be an
// unexplained "highest-impact first"; a cut with no stated criteria is a cut nobody
// can audit, and support_count gives it a number to stand on.
// ===========================================================================
phase('select')
const selection = await agent(
  `You are the ${DIRECTOR} — judge-only system-optimizer (you author NOTHING; you did not write these edits). Codex proposed the edits below for a ${DOMAIN} SkillOpt cycle, on two channels: source_type="failure" (corrective) and source_type="success" (reinforcement). Do FOUR things (Read), return per schema:

1. READ the rejection buffer ${BUFFER} (negative memory — MANDATORY). DROP any proposed edit that re-litigates a previously-reverted edit (same target + same intent) unless its content materially changed; record each drop with the buffer reason it matches.
2. MERGE the two channels, FAILURE-FIRST:
   - Where a failure edit and a success edit touch the same region or make the same point, KEEP THE FAILURE ONE. Fixing what broke outranks reinforcing what held.
   - Keep a success edit only where it covers ground no failure edit touches.
   - Two edits in the final set must never target the same text region.
   - Drop any success edit whose content merely restates something the target file already says (read the file to check) — a reinforcement edit that adds length without changing behaviour is the failure mode of this channel.
3. For each surviving edit classify:
   - blast: "high" if the target is a lead / manager / director agent, a COMMONS file, or a widely-loaded skill; else "low". (Use the blast-radius table in system-optimization-protocol.)
   - ownership: "owned" = a ${DOMAIN}-domain file you may self-promote; "commons" = a shared file you may only PROPOSE (the human promotes). Use your "Domain-owned vs commons" boundary.
4. RANK, then cut at edit_budget=${EDIT_BUDGET}. Rank on, in this order: (a) systematic impact — an edit backed by more of the batch (support_count) and closing a recurring class beats one closing an edge case; (b) complementarity — it fills a real gap rather than duplicating existing content; (c) generality — a principle beats a case-specific instruction; (d) actionability — concrete and checkable beats vague. State the criteria that decided the cut in ranking_note.${metaBlock}

Proposed edits:
${JSON.stringify(proposed, null, 2)}

Return per schema: selected[] (op/target/content/blast/ownership/source_type/support_count/pattern_class/rationale, in ranked order), dropped[] (target/reason), edit_budget=${EDIT_BUDGET}, ranking_note.`,
  { label: 'select:director', phase: 'select', schema: SELECT_SCHEMA })
const selected = (selection && selection.selected) ? selection.selected : []
const dropped = (selection && selection.dropped) ? selection.dropped : []
log(`select: ${selected.length} selected, ${dropped.length} dropped`)
if (!selected.length) {
  // Same hole as the zero-proposal path: every edit dropped is a real verdict, and it has
  // to reach the log or the cluster re-fires unchanged next session.
  const adjudication = await adjudicateNullCycle(
    'every proposed edit was dropped at select (rejection buffer / merge / no gap left)',
    { dropped, ranking_note: (selection && selection.ranking_note) || '' })
  log(`null cycle: adjudication ran=${adjudication.ran}`)
  return { ok: true, status: 'all-edits-dropped', domain: DOMAIN, dryRun: DRY, dropped, adjudication, selection }
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
Call mcp__codex__codex (approval-policy:"never", sandbox:"read-only", cwd:"${CLAUDE}") asking Codex to: read EVERY golden scenario file under ${GOLDEN}/ and the proposed edit (and, if it helps, the current target file under ${CLAUDE}); for each scenario judge whether the edited skill/agent STILL satisfies that scenario's Pass-criteria (no regression), and then apply the channel-appropriate second test:
- source_type="failure": is the targeted failure now CLOSED?
- source_type="success": the edit reinforces a behaviour that already works, so there is no failure to close. The second test is instead: does the edit stay NEUTRAL-OR-BETTER on every scenario, and does it add anything the target file does not already say? A reinforcement edit that only restates existing wording is a FAIL — it grows the corpus for nothing.
The non-rejection scenario (the one that fails an over-eager validator) carries the same weight as the rest: an edit that closes its target but trips the false-positive floor is a fail, not a trade-off.
Output JSON {"proposed_verdict":"pass|fail","per_scenario":[{"scenario":"NN-slug","assessment":"pass|fail|na","note":"..."}],"reasoning":"..."}.
Proposed edit (source_type="${e.source_type || 'failure'}"): ${JSON.stringify(e)}
RELAY Codex's read into the schema (do NOT substitute your own verdict). codex_ran=true iff Codex returned.`,
      { label: `gate:codex:${e.target}`, phase: 'gate', schema: GATE_PROPOSAL_SCHEMA })
      .then(prop => ({ edit: e, skipped: false, proposal: prop }))
  },
  (g) => {
    if (g.skipped) return g
    return agent(
      `You are the ${DIRECTOR} ADJUDICATING the golden gate for ONE ${DOMAIN} edit. Codex proposed the pass/fail read (below); YOU decide (mirror of adversary -> supreme judge). Read the golden scenarios under ${GOLDEN}/ and the edit; weigh Codex's proposal but reason independently.
PASS iff NO scenario regresses AND the channel's second test holds:
- source_type="failure": the targeted failure is closed.
- source_type="success": the edit is neutral-or-better on every scenario AND says something the target file does not already say. Set targeted_failure_closed=true for a success edit only when both hold.
The false-positive floor is not negotiable on either channel: an edit that trips the domain's non-rejection scenario is a REJECT, whatever else it fixes. A right-pattern / wrong-file edit (F2) FAILS.
Edit (source_type="${g.edit.source_type || 'failure'}"): ${JSON.stringify(g.edit)}
Codex gate proposal: ${JSON.stringify(g.proposal)}
Return per schema: target="${g.edit.target}", verdict (pass|fail), regression_risk (none|low|high), targeted_failure_closed (bool), per_scenario[], rationale.`,
      { label: `gate:judge:${g.edit.target}`, phase: 'gate', schema: GATE_VERDICT_SCHEMA })
      .then(v => ({ edit: g.edit, skipped: false, proposal: g.proposal, verdict: v }))
  })
const gatedClean = gated.filter(Boolean)
const passed = gatedClean.filter(x => x.verdict && x.verdict.verdict === 'pass')
log(`gate: ${passed.length}/${gatedClean.length} edit(s) passed`)

// ===========================================================================
// PHASE 4.5 — snapshot: copy every file this cycle is about to edit, BEFORE it is
// edited. Slow-update has always been able to report `blocked` on a regression and
// the protocol has always said "flag for rollback of the offending edit" — but the
// live corpus had no restore point, so the flag was a note to a human who would then
// reconstruct the prior text by hand. SkillOpt keeps `round<r>__before.md` per round
// and HarnessOpt keeps a git tag; this is the same idea at file granularity.
//
// File copies, not a git tag: ~/.claude is a git repo but is routinely dirty, so
// `git reset --hard` would take unrelated in-flight work with it. The baseline dirty
// list captured here is also what makes the diff guard precise — it can then tell a
// file THIS cycle touched from one that was already modified when it started.
// ===========================================================================
phase('promote')
const ownedGatePassed = gatedClean.filter(g => g.verdict && g.verdict.verdict === 'pass' && g.edit.ownership === 'owned')
let snapshot = { taken: false, dir: SNAPSHOTS, files: [], baseline_dirty: [], detail: 'no owned gate-passed edit — nothing to snapshot' }
if (ownedGatePassed.length) {
  snapshot = await agent(
    `You are taking the PRE-EDIT SNAPSHOT for a ${DOMAIN} SkillOpt cycle. Mechanical step, no judgement. Use Bash + Read/Write.

1. BASELINE (always, read-only): run \`git -C ${CLAUDE} status --porcelain\` and list every path already modified/untracked BEFORE this cycle writes anything. This is baseline_dirty. It is what lets the later diff guard distinguish this cycle's writes from work that was already in flight.
${DRY
      ? `2. DRY-RUN: do NOT copy anything. Return taken:false, files:[] and a detail saying which files WOULD have been snapshotted into ${SNAPSHOTS}.`
      : `2. COPY: create ${SNAPSHOTS} and copy the CURRENT content of each target file below from ${CLAUDE}/<target> into it, flattening the path into the filename (e.g. skills/foo/SKILL.md -> skills__foo__SKILL.md). Preserve bytes exactly (line endings included) — this copy is the rollback source. Skip a target that does not exist and say so in detail. Return taken:true and files[] mapping target -> copy path.`}

Targets (strip any "::anchor" suffix — snapshot the FILE):
${JSON.stringify(ownedGatePassed.map(g => g.edit.target))}

Return per schema.`,
    { label: 'snapshot', phase: 'promote', schema: SNAPSHOT_SCHEMA }) || snapshot
}
log(`snapshot: taken=${snapshot.taken} files=${(snapshot.files || []).length} baseline_dirty=${(snapshot.baseline_dirty || []).length}`)

// No snapshot, no promote. The rollback in step 6.5 restores from these copies and from
// nothing else, so applying edits without them buys a cycle that can detect a regression and
// cannot undo it — strictly worse than not running, because slow-update's buckets would then
// report a block that never happened. Fail closed instead.
if (!DRY && ownedGatePassed.length && !(snapshot.taken && (snapshot.files || []).length)) {
  log('ABORT: snapshot missing — refusing to apply edits with no restore point')
  return {
    ok: false, status: 'snapshot-failed', domain: DOMAIN, dryRun: DRY,
    error: 'the pre-edit snapshot did not complete, so a regression found by slow-update could not be rolled back; no edit was applied',
    snapshot, selected: selected.length,
    gate: gatedClean.map(g => ({ target: g.edit.target, verdict: g.verdict && g.verdict.verdict })),
  }
}

// ===========================================================================
// PHASE 5 — promote / escalate / reject (dry-run-aware).
//   owned + PASS    -> apply to ~/.claude live corpus; mirror side -> draft MR (stage-mr) | report (dry)
//   commons + PASS  -> HUMAN SEAM: draft-MR proposal note (edit+gate), never self-apply
//   FAIL            -> append to rejection buffer (real) | report (dry)
// ===========================================================================
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
    if (DRY) return Promise.resolve({ target: g.edit.target, decision: 'escalate-human', applied: false, ownership: 'commons', paths_written: [], rationale: 'commons edit passed the gate (dry-run: would write a draft-MR proposal note; commons is NEVER self-promoted)' })
    return agent(
      `You are the ${DIRECTOR}. This COMMONS edit PASSED the gate, but per system-optimization-protocol governance you CANNOT self-promote a commons file. Write a DRAFT-MR PROPOSAL note to ${MEMORY}/skillopt-escalation-${DOMAIN}-${TS}.md — the same reviewable shape as an owned MR body: a ## title, a Summary of the pattern, an "Ownership: commons (proposal — the human decides the content)" line, the exact proposed edit (op/target/content), the gate verdict, and a one-line ask that the human commons-maintainer review and apply. Do NOT modify the commons file or the mirror. Return per schema (decision:'escalate-human', applied:true, ownership:'commons', paths_written:[the note path], rationale).
Edit: ${JSON.stringify(g.edit)}
Gate verdict: ${JSON.stringify(v)}`,
      { label: `escalate:${g.edit.target}`, phase: 'promote', schema: PROMOTE_SCHEMA })
  }
  if (DRY) return Promise.resolve({ target: g.edit.target, decision: 'promote', applied: false, ownership: 'owned', paths_written: [], rationale: `domain-owned + gate PASS (dry-run: would apply ${g.edit.op} to ${CLAUDE}/${g.edit.target} live; mirror side staged as a draft MR in the stage-mr phase)` })
  return agent(
    `You are the ${DIRECTOR}. This DOMAIN-OWNED edit PASSED the gate. Apply it to the LIVE working corpus ONLY — do NOT touch the mirror here; the mirror side is staged as a draft MR later (stage-mr phase):
1. Apply ${g.edit.op} to ${CLAUDE}/${g.edit.target}. For insert_after/replace/delete the target carries "::<exact anchor>" — match it EXACTLY (Edit). For append, append to file end. For a brand-new heading use insert_after on an existing anchor.
2. Read back the edited region to confirm.
Edit: ${JSON.stringify(g.edit)}
Return per schema (decision:'promote', applied:true, ownership:'owned', paths_written:[the ~/.claude file], rationale).`,
    { label: `promote:${g.edit.target}`, phase: 'promote', schema: PROMOTE_SCHEMA })
}))).filter(Boolean)
const nProm = promotions.filter(p => p.decision === 'promote').length
const nEsc = promotions.filter(p => p.decision === 'escalate-human').length
const nRej = promotions.filter(p => p.decision === 'reject').length
log(`promote: ${nProm} promote, ${nEsc} escalate-human, ${nRej} reject (dryRun=${DRY})`)

// ===========================================================================
// PHASE 5.2 — diff guard: prove this cycle wrote ONLY where it declared it would.
// Every step above states its targets, and every step above is an LLM that could
// touch a neighbouring file while it is in there. The golden gate judges the edit
// that was PROPOSED; nothing until now checked what actually landed on disk.
// HarnessOpt's loop enforces its editable surface with a git-diff allowlist for the
// same reason. Newly-touched = post-promote dirty MINUS the baseline captured before
// promote, so pre-existing in-flight work never reads as a violation.
// ===========================================================================
const declaredTargets = promotions
  .filter(p => p.applied)
  .flatMap(p => p.paths_written || [])
const allowedSideEffects = [BUFFER, LOG, META, SNAPSHOTS, `${MEMORY}/promotions`, `${MEMORY}/skillopt-escalation-`]
// Two DIFFERENT defaults, and the difference is the point. In dry-run nothing was written, so
// "clean" is a fact. In a real run a missing guard result is not evidence of cleanliness — the
// agent may simply have died — so it fails CLOSED. `|| diffGuard` with a clean:true default
// would otherwise hand a silent pass to exactly the runs that most need checking, and print
// "dry-run: nothing was written" into a live cycle's record.
let diffGuard = { ran: false, clean: true, newly_touched: [], violations: [], detail: 'dry-run: nothing was written, so there is nothing to guard' }
if (!DRY) {
  const guardFailedClosed = {
    ran: false, clean: false, newly_touched: [],
    violations: ['diff-guard did not report'],
    detail: 'the diff-guard agent returned nothing; treated as UNCLEAN because a missing check is not a passing check',
  }
  diffGuard = await agent(
    `You are running the DIFF GUARD for a ${DOMAIN} SkillOpt cycle. Mechanical, read-only (Bash), no judgement. Do NOT fix, revert or edit anything — report only. A false positive here is expensive (it triggers a full restore), so normalise both sides before comparing rather than eyeballing them.

1. Run \`git -C ${CLAUDE} status --porcelain\`. Its paths are REPO-RELATIVE with forward slashes.
2. Normalise the allowlist to the same shape: strip a leading "${CLAUDE}/" from any absolute path below and convert backslashes to forward slashes. Compare normalised-to-normalised.
3. newly_touched = every path git reports that is NOT in the pre-promote baseline: ${JSON.stringify(snapshot.baseline_dirty || [])}
   Note: git collapses an untracked DIRECTORY into a single \`?? dir/\` entry. Treat such an entry as covering everything beneath it.
4. A newly-touched path is ALLOWED if it equals a declared target, or is at-or-under one of the allowed side-effect paths. Everything else is a VIOLATION — this cycle wrote where it never declared it would.
   - declared targets (what promote actually reported writing): ${JSON.stringify(declaredTargets)}
   - allowed side-effect paths (prefixes): ${JSON.stringify(allowedSideEffects)}
5. If ${CLAUDE} is not a git work tree, set ran:false, clean:false, and say so in detail — do NOT guess a pass.

Return per schema: ran, clean (violations.length === 0), newly_touched[], violations[], detail.`,
    { label: 'diff-guard', phase: 'promote', schema: DIFFGUARD_SCHEMA }) || guardFailedClosed
}
log(`diff-guard: ran=${diffGuard.ran} clean=${diffGuard.clean} violations=${(diffGuard.violations || []).length}`)

// ===========================================================================
// PHASE 6 — slow-update (anti-forgetting). Re-read the golden set over the POST-edit
// corpus, 4-bucket; regressed>0 blocks and now rolls back.
//
// Runs after ANY owned promotion, not only high-blast ones. The blast tiering skips the
// PRE-check (a low-blast edit gets `skipVerdict()` and is never judged against the golden
// set), which is the intended anti-overhead trade. But this phase used to skip the POST-check
// on the same edits, and the two skips together meant a low-blast edit was applied to the
// corpus AND staged for the mirror without any scenario ever being read against it. Nothing
// stopped it adding an always-flag-X rule to a specialist and ratcheting the corpus toward
// suspicion, which is exactly the drift the false-positive floor exists to catch.
//
// Covering it here is nearly free: this is ONE agent call over the whole golden set per
// cycle, not one per edit, so the cheap tier stays cheap. It is also only safe now — a
// post-hoc check is worth having only if a failure can be undone, and the snapshot from
// phase 4.5 is what makes the rollback below real. Set forceGate to pre-check instead.
// ===========================================================================
phase('slow-update')
const appliedOwnedTargets = new Set(
  promotions.filter(p => p.applied && p.decision === 'promote').map(p => p.target))
const promotedOwned = gatedClean.filter(g =>
  g.verdict && g.verdict.verdict === 'pass' && g.edit.ownership === 'owned'
  && (DRY || appliedOwnedTargets.has(g.edit.target)))
const promotedHigh = promotedOwned.filter(g => g.edit.blast === 'high')
const ungated = promotedOwned.filter(g => g.skipped)
let slowUpdate = { ran: false, buckets: null, blocked: false, detail: 'no owned promotion this cycle — slow-update not required' }
if (promotedOwned.length) {
  if (DRY) {
    slowUpdate = { ran: false, buckets: null, blocked: false, detail: `${promotedOwned.length} owned promotion(s) present but dry-run — slow-update would re-read the golden set in a real cycle` }
  } else {
    const su = await agent(
      `You are the ${DIRECTOR} running SLOW-UPDATE (anti-forgetting) after ${promotedOwned.length} domain-owned promotion(s) in ${DOMAIN} (${promotedHigh.length} high-blast, ${ungated.length} that SKIPPED the pre-gate because they were classed low-blast). Re-read the golden set under ${GOLDEN}/ as a rubric read on the POST-edit corpus and compare to each scenario's "Expected behavior" baseline. Categorise EACH scenario: regressed (was-good->now-bad), persistent_fail (bad->bad), improved (bad->good), stable_success (good->good). regressed>0 BLOCKS the cycle and triggers a rollback.
${ungated.length ? `Pay particular attention to the ${ungated.length} edit(s) marked ungated below: no scenario has been read against them at any earlier point in this cycle, so this is their FIRST and ONLY check. The domain's non-rejection scenario matters most for them — a low-blast edit that teaches a specialist to always flag something is the cheap way this corpus drifts toward suspicion.\n` : ''}
Promoted edits: ${JSON.stringify(promotedOwned.map(g => ({ ...g.edit, ungated: !!g.skipped })))}
Return per schema: ran:true, buckets {regressed,persistent_fail,improved,stable_success}, blocked (regressed>0), detail.`,
      { label: 'slow-update', phase: 'slow-update', schema: SLOWUPDATE_SCHEMA })
    // Fail CLOSED, and with an honest detail line. The outer initialiser says "no owned
    // promotion — not required", which is false inside this branch: there ARE promotions, the
    // check just did not report. Reusing it would have skipped anti-forgetting and then
    // asserted in the run record that it was never needed.
    slowUpdate = su || {
      ran: false, buckets: null, blocked: true,
      detail: `slow-update agent returned nothing after ${promotedOwned.length} owned promotion(s) — treated as BLOCKED because an unrun anti-forgetting check is not a passed one`,
    }
  }
}
log(`slow-update: ran=${slowUpdate.ran} blocked=${slowUpdate.blocked} covered=${promotedOwned.length} (ungated=${ungated.length})`)

// ===========================================================================
// PHASE 6.5 — rollback. `blocked` used to be a field in the return value and
// nothing else: the regressing edit stayed on disk, and the MR was staged anyway.
// A block that does not block is worse than no block, because the buckets read as
// if something was enforced. Now a regression restores the snapshot, records the
// edit in the rejection buffer so it cannot be re-proposed, and stops the MR.
// A diff-guard violation triggers the same path — a cycle that wrote outside its
// declared targets has already broken the premise the gate judged under.
// ===========================================================================
// A PROVEN violation is different from a guard that could not report. The first means the
// cycle demonstrably wrote where it should not have, and earns a restore. The second proves
// nothing, so it does not roll a healthy cycle back — but it does stop publication, because
// an unverified cycle is not a reviewed one.
const guardViolation = diffGuard.ran === true && diffGuard.clean === false
const anythingApplied = promotions.some(p => p.applied && p.decision === 'promote')
const guardInconclusive = !DRY && anythingApplied && diffGuard.ran !== true
const regressedCount = (slowUpdate.buckets && slowUpdate.buckets.regressed) || 0
const mustRollback = (!DRY) && (slowUpdate.blocked || regressedCount > 0 || guardViolation)
let rollback = { ran: false, restored: [], detail: mustRollback ? 'rollback required' : 'no regression and no diff-guard violation — nothing to roll back' }
if (mustRollback) {
  // Restore EVERY edit this cycle applied, not just the high-blast ones. slow-update only
  // looks at high-blast promotions, but a diff-guard violation can fire on a cycle with none,
  // and a half-restored corpus is worse than either outcome.
  const rolledBackEdits = ownedGatePassed.map(g => g.edit)
  rollback = await agent(
    `You are the ${DIRECTOR} performing a ROLLBACK of this ${DOMAIN} SkillOpt cycle. Reason: ${slowUpdate.blocked || regressedCount > 0 ? `slow-update reported ${regressedCount || '>0'} REGRESSED golden scenario(s) (or failed to report, which is treated the same)` : 'the diff guard found writes outside the declared targets'}.

1. RESTORE: for each snapshot pair below, copy the snapshot copy back over ${CLAUDE}/<target>, byte for byte. Read back each restored file to confirm it matches the snapshot. If a snapshot copy is missing for a target you were asked to restore, say so explicitly in detail and leave that target OUT of restored[] — do not report a restore you did not perform.
   Snapshots: ${JSON.stringify(snapshot.files || [])}
2. BUFFER: append one entry per rolled-back edit to ${BUFFER} (append-only) per its schema — "## <summary> | target: <target> | domain: ${DOMAIN} | <YYYY-MM-DD from ${TS}>", "Tried:", "Reverted because: <the regressed scenario(s) by name, or the diff-guard violation>", "Status: RETRACTED". This is what stops the next cycle re-proposing it, so write one for EVERY edit below even when the regression was attributed to only one of them.
3. Do NOT touch ${MIRROR} — no MR was staged.
${guardViolation ? `4. The guard reported these unexpected writes; name them in detail but do NOT revert paths outside the declared targets — a human decides those: ${JSON.stringify(diffGuard.violations || [])}` : ''}

Rolled-back edits: ${JSON.stringify(rolledBackEdits)}
Slow-update buckets: ${JSON.stringify(slowUpdate.buckets)}

Return per schema: ran (true only if you actually restored files), restored[] (the ${CLAUDE} paths you restored), detail.`,
    { label: 'rollback', phase: 'slow-update', schema: ROLLBACK_SCHEMA }) || rollback
}
log(`rollback: required=${mustRollback} ran=${rollback.ran} restored=${(rollback.restored || []).length}`)

// The decision is what gates everything downstream, never the executor's self-report. If the
// rollback agent dies, `rollback.ran` is false and a `|| rollback`-style fallback would let the
// MR stage and the record write `resolved:` on an edit that is still live and still regressing.
// That is the "block that does not block" this phase exists to remove, so it hard-stops instead.
if (mustRollback && !rollback.ran) {
  log('ABORT: rollback was required and did not complete — corpus may still carry the regressing edit')
  return {
    ok: false, status: 'rollback-failed', domain: DOMAIN, dryRun: DRY,
    error: 'a rollback was required (golden regression or diff-guard violation) but did not complete; the live corpus may still hold the offending edit. Restore by hand from the snapshot dir before running another cycle.',
    snapshotDir: snapshot.dir, snapshot, slowUpdate, diffGuard, rollback,
    promotions, humanSeam: promotions.filter(p => p.decision === 'escalate-human'),
  }
}

// ===========================================================================
// PHASE 5.5 — stage-mr: reroute OWNED promotions from a silent mirror-main copy
// to a reviewable DRAFT MR (promotion branch on the mirror + MR body). NEVER
// merges or pushes — the human reviews `git diff main..<branch>` + the body
// and merges = the publish/ship decision. dry-run stages nothing. Skipped outright
// when the cycle rolled back: there is nothing left to publish.
// ===========================================================================
phase('stage-mr')
const publishBlocked = mustRollback || guardInconclusive
// Only edits that were ACTUALLY applied to the live corpus may reach the mirror. Selecting on
// gate-verdict alone let a promote agent die (agent() -> null, no write) while its edit still
// got staged onto the promotion branch: the mirror would then carry a change ~/.claude does
// not have, and the human would merge a delta with no working-tree twin.
const appliedTargets = new Set(
  promotions.filter(p => p.applied && p.decision === 'promote').map(p => p.target))
const ownedPassed = publishBlocked
  ? []
  : gatedClean.filter(g => g.verdict && g.verdict.verdict === 'pass'
      && g.edit.ownership === 'owned'
      && (DRY || appliedTargets.has(g.edit.target)))
let draftMR = {
  staged: false, branch: '', body_path: '', files: [],
  detail: mustRollback
    ? 'cycle rolled back (golden regression or diff-guard violation) — no MR staged'
    : guardInconclusive
      ? 'the diff guard could not confirm this cycle wrote only where it declared — no MR staged; a human reviews the working tree first'
      : 'no owned promotion applied this cycle — no MR staged',
}
if (ownedPassed.length) {
  const BR = `skillopt/${DOMAIN}-${TS}`
  const BODY = `${MEMORY}/promotions/${TS}-${DOMAIN}.md`
  if (DRY) {
    draftMR = { staged: false, branch: BR, body_path: BODY, files: ownedPassed.map(g => g.edit.target), detail: `dry-run: would stage ${ownedPassed.length} owned edit(s) as a draft MR (branch ${BR} on ${MIRROR} + MR body ${BODY}); no merge/push` }
  } else {
    draftMR = await agent(
      `You are the ${DIRECTOR} staging this cycle's DOMAIN-OWNED gate-passed edits as a DRAFT MR on the blessed mirror ${MIRROR} (a git repo). Do NOT merge, do NOT git-push — publication is the human's step. Your job: leave a reviewable branch + an MR body.
Run git via Bash (always with \`git -C ${MIRROR}\`):
1. \`git -C ${MIRROR} checkout -B ${BR}\` — promotion branch off current HEAD; main is left untouched.
2. For EACH edit below, apply the SAME op as a surgical delta to ${MIRROR}/<target> (match "::<exact anchor>" via Edit; append = file end). PRESERVE the mirror file's line-endings (CRLF vs LF); edit in place rather than copying the whole file over. If a mirror path is absent, note it and skip (create no stray files).
3. \`git -C ${MIRROR} add -A && git -C ${MIRROR} commit -m "skillopt(${DOMAIN}): draft ${TS}"\`, then \`git -C ${MIRROR} checkout main\` so main's working tree is clean (the delta lives on ${BR}).
4. Write the MR body to ${BODY} (create ${MEMORY}/promotions/ if absent) — the review note (reasoning attached): a ## title, a Summary of the batch pattern closed, the signals addressed, an "Ownership: owned" line, a Files+ops list, the per-edit golden-gate verdict, the slow-update buckets, a "Codex-authored / ${DIRECTOR}-judged" line, and a one-line merge-ask for the human.
5. Confirm with \`git -C ${MIRROR} log --oneline -1 ${BR}\`.
Owned edits: ${JSON.stringify(ownedPassed.map(g => ({ edit: g.edit, gate: g.verdict })))}
Slow-update buckets: ${JSON.stringify(slowUpdate.buckets)}
Return per schema: staged:true, branch:"${BR}", body_path:"${BODY}", files:[the mirror paths written], detail.`,
      { label: 'stage-mr', phase: 'stage-mr', schema: DRAFTMR_SCHEMA }) || draftMR
  }
}
log(`stage-mr: staged=${draftMR.staged} branch=${draftMR.branch || '(none)'}`)

// ===========================================================================
// PHASE 7 — record: close the signals this cycle actually addressed, and leave a
// cycle note. Until now a SUCCESSFUL skill cycle wrote nothing back to the log, so
// the cluster it had just closed stayed live and skillopt-ready.py re-fired it on
// the next session. A cycle that cannot close its own signals learns nothing between runs.
// ===========================================================================
phase('record')
let record = { ran: false, resolved_signals: [], cycle_note_path: null, detail: 'dry-run, rollback, or nothing promoted — no log writes' }
const promotedReal = promotions.filter(p => p.applied && p.decision === 'promote')
if (publishBlocked) {
  // Gate on the DECISION, not on whether the rollback executor reported success. Closing a
  // signal whose edit was reverted (or never verified) tells the next cycle a gap is fixed
  // when it is not, and skillopt-ready then stops surfacing it.
  record = {
    ran: false, resolved_signals: [], cycle_note_path: null,
    detail: mustRollback
      ? 'cycle rolled back — signals deliberately left open'
      : 'diff guard inconclusive — signals deliberately left open pending human review',
  }
} else if (!DRY && promotedReal.length) {
  record = await agent(
    `You are the ${DIRECTOR} RECORDING a ${DOMAIN} SkillOpt cycle in ${LOG}. Modify only ${LOG}.

1. For each signal the PROMOTED edits actually address, append under its signal block:
   \`resolved: <YYYY-MM-DD from ${TS}> — skillopt cycle ${TS}. <which edit closed it, and the gate evidence>\`
   Close ONLY signals a promoted edit genuinely addresses. A signal in the same cluster that no edit touched stays OPEN — silently closing it would hide a live gap and is the more expensive mistake here.
2. If a signal's trace is mixed (a skill half plus a script/engine half) and only the skill half was closed, write \`resolved (SKILL half):\` instead of a bare \`resolved:\`. Spell the marker exactly: skillopt-ready reads it as closed, harness-ready deliberately does not, so the still-open script half keeps counting toward its own cluster. A bare \`resolved:\` there would close both halves and lose the script one.
3. Append a short cycle note: the batch pattern closed, the edits promoted (with source_type — corrective vs reinforcement), the gate verdicts, the slow-update buckets, and the draft-MR branch if one was staged.

Promoted: ${JSON.stringify(promotedReal)}
Selected edits: ${JSON.stringify(selected.map(e => ({ target: e.target, source_type: e.source_type, pattern_class: e.pattern_class, support_count: e.support_count })))}
Signals in play: ${JSON.stringify(harvest.signals, null, 2)}
Slow-update: ${JSON.stringify(slowUpdate)}
Draft MR: ${JSON.stringify({ staged: draftMR.staged, branch: draftMR.branch })}

Return per schema: ran:true, resolved_signals[] (the signals you closed), cycle_note_path (${LOG}), detail.`,
    { label: 'record:director', phase: 'record', schema: RECORD_SCHEMA }) || record
}
log(`record: ran=${record.ran} resolved=${(record.resolved_signals || []).length}`)

// ===========================================================================
// PHASE 8 — meta: optimizer-side memory. Protocol step 6 has always specified a
// two-level meta file (shared process + per-domain content); the script declared
// its path and never read or wrote it, so every cycle started from zero and could
// repeat an editing mistake the last one had already paid for. This writes it, and
// the reflect/select steps above now read it.
//
// Deliberately narrow: it records how to EDIT better (what kind of edit helped,
// what was too vague or brittle, what to watch for), never target-facing rules —
// those belong in the corpus and go through the gate.
// ===========================================================================
phase('meta')
let metaUpdate = { ran: false, lessons: [], line_count: 0, detail: 'dry-run or nothing to learn from — meta untouched' }
// Gate failures count as material, and are in fact the richest kind: a cycle where every
// selected edit failed the golden gate is precisely the "edits phrased as X keep tripping the
// floor scenario" lesson the next cycle most needs. Keying only on promoted/dropped/rolled-back
// skipped exactly that case.
const gateFailures = gatedClean.filter(g => g.verdict && g.verdict.verdict === 'fail')
if (!DRY && (promotedReal.length || mustRollback || gateFailures.length || (dropped && dropped.length))) {
  metaUpdate = await agent(
    `You are the ${DIRECTOR} updating the OPTIMIZER-SIDE memory at ${META} after a ${DOMAIN} SkillOpt cycle. This memory is read by the NEXT cycle's reflect and select steps.

Read ${META} first (create it with a "## Shared process" and a "## ${DOMAIN}" section if absent). Then:
1. Judge the PREVIOUS lessons against what happened this cycle: which held, which misled, which were never relevant. Revise or delete what did not earn its place — this file is not append-only.
2. Add at most 2-3 new lessons, each grounded in THIS cycle's evidence (a gate verdict, a rollback, a dropped edit), never generic advice. Address the FUTURE OPTIMIZER, not the target: "edits phrased as X kept failing the floor scenario", not "validators should check X".
3. Keep the split: cross-domain lessons about HOW to optimise go under "## Shared process" (all three directors read it); ${DOMAIN}-specific editing heuristics go under "## ${DOMAIN}".
4. HARD CAP ~150 lines total. If the file would exceed it, prune the weakest lessons first and say which in detail. An unbounded meta file stops being read, which costs more than any single lesson in it.

This cycle: ${JSON.stringify({
      proposed: proposed.length,
      corrective: failureEdits.length,
      reinforcement: successEdits.length,
      selected: selected.map(e => ({ target: e.target, source_type: e.source_type, support_count: e.support_count })),
      dropped,
      ranking_note: (selection && selection.ranking_note) || '',
      gate: gatedClean.map(g => ({ target: g.edit.target, verdict: g.verdict && g.verdict.verdict, rationale: g.verdict && g.verdict.rationale })),
      slow_update: slowUpdate,
      diff_guard: { ran: diffGuard.ran, clean: diffGuard.clean, violations: diffGuard.violations },
      rolled_back: mustRollback,
    }, null, 2)}

Return per schema: ran:true, lessons[] (the lesson lines you wrote), line_count (of the file after your write), detail.`,
    { label: 'meta:director', phase: 'meta', schema: META_SCHEMA }) || metaUpdate
}
log(`meta: ran=${metaUpdate.ran} lessons=${(metaUpdate.lessons || []).length} lines=${metaUpdate.line_count}`)

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
  success_codex_ran: !!(successReflect && successReflect.codex_ran),
  due: harvest.due,
  successDue: harvest.success_due || [],
  proposed: proposed.length,
  proposedByChannel: { corrective: failureEdits.length, reinforcement: successEdits.length },
  selected: selected.length,
  selectedByChannel: {
    corrective: selected.filter(e => e.source_type !== 'success').length,
    reinforcement: selected.filter(e => e.source_type === 'success').length,
  },
  dropped,
  rankingNote: (selection && selection.ranking_note) || '',
  gate: gatedClean.map(g => ({ target: g.edit.target, blast: g.edit.blast, ownership: g.edit.ownership, source_type: g.edit.source_type, skipped: !!g.skipped, gate_codex_ran: g.proposal ? g.proposal.codex_ran : null, verdict: g.verdict && g.verdict.verdict, regression_risk: g.verdict && g.verdict.regression_risk, targeted_failure_closed: g.verdict && g.verdict.targeted_failure_closed })),
  snapshot,
  promotions,
  diffGuard,
  slowUpdate,
  rollback: { ...rollback, required: mustRollback },
  publishBlocked,
  draftMR,
  record,
  meta: metaUpdate,
  humanSeam: promotions.filter(p => p.decision === 'escalate-human'),
}
