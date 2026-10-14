#!/usr/bin/env node
/**
 * Regression guard — the safety gates of both self-improvement loops.
 *
 * skillopt-workflow.js and harnessopt-workflow.js edit this corpus. Their gates (golden gate,
 * slow-update, diff guard, snapshot, rollback) are the only thing between a bad proposal and
 * the blessed mirror, and every one of them is driven by an `agent()` call that can return
 * null when a subagent dies. A gate that fails OPEN on that path is indistinguishable, in the
 * run record, from a gate that passed — which is the worst possible failure shape here.
 *
 * Nothing else can catch this. The scripts are agent bodies, so there is no unit under test;
 * the only way to exercise the control flow is to run the body with stubbed globals and
 * scripted agent responses, which is what this does.
 *
 * Pinned:
 *   1  ROLLBACK IS NOT OPTIONAL    a required rollback that does not complete hard-stops
 *                                  instead of letting the MR and the `resolved:` lines through.
 *   2  MISSING CHECK != PASS       a null diff-guard / slow-update result blocks publication
 *                                  rather than reading as clean.
 *   3  NO SNAPSHOT, NO APPLY       without a restore point the cycle refuses to edit at all.
 *   4  LOW-BLAST IS COVERED        an edit that skipped the pre-gate is still post-checked by
 *                                  slow-update (it used to skip both and reach the mirror).
 *   5  CHANNEL POSITIONS HOLD      if the corrective reflect returns null, the reinforcement
 *                                  result must not slide into its slot and be relabelled.
 *   6  MIRROR FOLLOWS THE CORPUS   only edits actually applied can be staged.
 *   7  DRY RUN WRITES NOTHING      no promote / guard / stage / record / meta agent runs.
 *   8  HARNESS PARITY              the harness loop rolls back on a proven violation too.
 *
 * Run: node test_loop_gating_regress.cjs
 */

'use strict'

const fs = require('fs')
const path = require('path')

const CLAUDE = path.resolve(__dirname, '..', '..')
const WORKFLOWS = path.join(CLAUDE, 'workflows')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor

function compile(file) {
  const src = fs.readFileSync(path.join(WORKFLOWS, file), 'utf8')
    .replace(/^export\s+const\s+meta\s*=/m, 'const meta =')
  return new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', 'workflow', src)
}

/** Run a workflow body with scripted agent responses. `responses` maps a label PREFIX to a
 *  value, or to a function (label) => value. `null` simulates the documented agent-died path. */
async function run(file, argsObj, responses) {
  const calls = []
  const agent = async (prompt, opts) => {
    const label = (opts && opts.label) || '(unlabelled)'
    calls.push(label)
    const key = Object.keys(responses)
      .filter(k => label === k || label.startsWith(k))
      .sort((a, b) => b.length - a.length)[0]
    if (key === undefined) throw new Error(`no scripted response for agent label ${label!==undefined?label:''}`)
    const v = responses[key]
    return typeof v === 'function' ? v(label) : v
  }
  const parallel = async (thunks) => {
    const out = []
    for (const t of thunks) {
      try { out.push(await t()) } catch { out.push(null) }
    }
    return out
  }
  const pipeline = async (items, ...stages) => {
    const out = []
    for (let i = 0; i < items.length; i++) {
      let acc = items[i]
      try {
        for (const s of stages) acc = await s(acc, items[i], i)
        out.push(acc)
      } catch { out.push(null) }
    }
    return out
  }
  const fn = compile(file)
  const result = await fn(argsObj, agent, parallel, pipeline, () => {}, () => {}, { total: null, spent: () => 0, remaining: () => Infinity }, async () => {})
  return { result, calls }
}

// ---- fixtures -------------------------------------------------------------

const ARGS = { domain: 'dev', claudeDir: 'C:/x/.claude', memoryDir: 'C:/x/mem', ts: '20260905T000000Z' }
const HARGS = { claudeDir: 'C:/x/.claude', memoryDir: 'C:/x/mem', ts: '20260905T000000Z' }

const edit = (over = {}) => ({
  op: 'append', target: 'skills/foo/SKILL.md', content: 'x',
  blast: 'high', ownership: 'owned', source_type: 'failure', support_count: 3,
  pattern_class: 'c', rationale: 'r', ...over,
})

function skilloptBase(over = {}) {
  const sel = over.selected || [edit()]
  return {
    harvest: { ready: true, domain: 'dev', due: [{ class: 'c', count: 3, kind: 'log' }], signals: [{ engagement: 'e', failure_class: 'c', class_key: 'c', traced_to: 'skills/foo/SKILL.md', evidence: 'x', target_kind: 'skill_agent' }], success_due: [], success_signals: [], raw_tail: '' },
    'reflect:codex:failure': { codex_ran: true, reasoning: 'r', edits: [{ op: 'append', target: 'skills/foo/SKILL.md', content: 'x', pattern_class: 'c', source_type: 'failure', support_count: 3, cross_check: 'g' }] },
    'reflect:codex:success': { codex_ran: true, reasoning: 'r', edits: [] },
    'select:director': { selected: sel, dropped: [], edit_budget: 4, ranking_note: 'n' },
    'gate:codex': { codex_ran: true, proposed_verdict: 'pass', per_scenario: [], reasoning: 'r' },
    'gate:judge': { target: 'skills/foo/SKILL.md', verdict: 'pass', regression_risk: 'none', targeted_failure_closed: true, rationale: 'r' },
    snapshot: { taken: true, dir: 'C:/x/mem/snap', files: [{ target: 'skills/foo/SKILL.md', copy: 'C:/x/mem/snap/a' }], baseline_dirty: [], detail: 'd' },
    'promote:': { target: 'skills/foo/SKILL.md', decision: 'promote', applied: true, ownership: 'owned', paths_written: ['skills/foo/SKILL.md'], rationale: 'r' },
    'diff-guard': { ran: true, clean: true, newly_touched: ['skills/foo/SKILL.md'], violations: [], detail: 'd' },
    'slow-update': { ran: true, buckets: { regressed: 0, persistent_fail: 0, improved: 1, stable_success: 3 }, blocked: false, detail: 'd' },
    rollback: { ran: true, restored: ['skills/foo/SKILL.md'], detail: 'd' },
    'stage-mr': { staged: true, branch: 'b', body_path: 'p', files: ['skills/foo/SKILL.md'], detail: 'd' },
    'record:director': { ran: true, resolved_signals: ['e'], cycle_note_path: 'l', detail: 'd' },
    'meta:director': { ran: true, lessons: ['l'], line_count: 20, detail: 'd' },
    'adjudicate:director': { ran: true, resolved_signals: [], cycle_note_path: null, detail: 'd' },
    ...(over.responses || {}),
  }
}

const hpatch = { cluster: 'c', target: 'scripts/x.py', zone: 'zone1', is_new_flag: false, test_patch: 't', fix_patch: 'f', files_touched: ['scripts/x.py'], new_regression_command: 'c', live_subprocess_command: null, expected_pre_failure: 'a', expected_post_success: 'b', rationale: 'r' }

function harnessBase(over = {}) {
  return {
    harvest: { ready: true, due: [{ target: 'scripts/x.py', class: 'c', count: 2 }], signals: [{ engagement: 'e', failure_class: 'c', class_key: 'c', traced_to: 'scripts/x.py', evidence: 'x', zone: 'zone1' }], raw_tail: '' },
    'reflect:codex': { codex_ran: true, reasoning: 'r', patches: [hpatch] },
    'select:director': { selected: [{ target: 'scripts/x.py', zone: 'zone1', ownership: 'owned', rationale: 'r', patch: hpatch }], dropped: [], edit_budget: 2 },
    'gate:run': { target: 'scripts/x.py', red_green_proven: true, regressions_green: true, static_clean: true, live_repro_pass: null, byteid_off_pass: null, captured: 'c', proposed_verdict: 'pass' },
    'gate:judge': { target: 'scripts/x.py', verdict: 'pass', rationale: 'r' },
    snapshot: { taken: true, dir: 'C:/x/mem/snap', files: [{ target: 'scripts/x.py', copy: 'C:/x/mem/snap/a' }], baseline_dirty: [], detail: 'd' },
    'promote:': { target: 'scripts/x.py', decision: 'promote', applied: true, ownership: 'owned', paths_written: ['scripts/x.py'], rationale: 'r' },
    'diff-guard': { ran: true, clean: true, newly_touched: ['scripts/x.py'], violations: [], detail: 'd' },
    rollback: { ran: true, restored: ['scripts/x.py'], detail: 'd' },
    'stage-mr': { staged: true, branch: 'b', body_path: 'p', files: ['scripts/x.py'], detail: 'd' },
    'record:director': { ran: true, resolved_signals: ['e'], cycle_note_path: 'l', detail: 'd' },
    'adjudicate:director': { ran: true, resolved_signals: [], cycle_note_path: null, detail: 'd' },
    ...(over.responses || {}),
  }
}

// ---- assertions -----------------------------------------------------------

const results = []
function check(label, ok, detail) {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}`)
  if (!ok && detail) console.log(`         ${detail}`)
  results.push(ok)
}
const ran = (calls, prefix) => calls.some(c => c === prefix || c.startsWith(prefix))

async function main() {
  console.log('1. a required rollback that does not complete hard-stops')
  {
    const { result, calls } = await run('skillopt-workflow.js', ARGS, skilloptBase({
      responses: {
        'slow-update': { ran: true, buckets: { regressed: 2, persistent_fail: 0, improved: 0, stable_success: 2 }, blocked: true, detail: 'd' },
        rollback: null,
      },
    }))
    check('ok:false, status rollback-failed', result.ok === false && result.status === 'rollback-failed', JSON.stringify(result).slice(0, 220))
    check('no MR staged', !ran(calls, 'stage-mr'), calls.join(','))
    check('no `resolved:` written', !ran(calls, 'record:director'), calls.join(','))
  }

  console.log('\n2. a missing check is not a passing check')
  {
    const { result, calls } = await run('skillopt-workflow.js', ARGS, skilloptBase({ responses: { 'diff-guard': null } }))
    check('null diff-guard blocks publication', result.publishBlocked === true, JSON.stringify(result.diffGuard))
    check('  and does not roll a healthy cycle back', result.rollback.required === false, JSON.stringify(result.rollback))
    check('  and stages no MR', !ran(calls, 'stage-mr'), calls.join(','))
    check('  and records nothing', !ran(calls, 'record:director'), calls.join(','))
  }
  {
    const { result } = await run('skillopt-workflow.js', ARGS, skilloptBase({ responses: { 'slow-update': null } }))
    check('null slow-update is treated as BLOCKED', result.slowUpdate.blocked === true, JSON.stringify(result.slowUpdate))
    check('  and its detail does not claim it was unnecessary',
      /treated as BLOCKED/.test(result.slowUpdate.detail), result.slowUpdate.detail)
  }

  console.log('\n3. no snapshot, no apply')
  {
    const { result, calls } = await run('skillopt-workflow.js', ARGS, skilloptBase({
      responses: { snapshot: { taken: false, dir: 'd', files: [], baseline_dirty: [], detail: 'failed' } },
    }))
    check('ok:false, status snapshot-failed', result.ok === false && result.status === 'snapshot-failed', JSON.stringify(result).slice(0, 200))
    check('no edit was applied', !ran(calls, 'promote:'), calls.join(','))
  }

  console.log('\n4. a low-blast edit skips the pre-gate but is still post-checked')
  {
    const low = [edit({ blast: 'low' })]
    const { result, calls } = await run('skillopt-workflow.js', ARGS, skilloptBase({ selected: low }))
    check('pre-gate skipped (that is the tier)', !ran(calls, 'gate:codex'), calls.join(','))
    check('slow-update still ran over it', ran(calls, 'slow-update'), calls.join(','))
    check('  and the run records it as covered', result.slowUpdate.ran === true, JSON.stringify(result.slowUpdate))
  }

  console.log('\n5. channel positions survive a dead corrective reflect')
  {
    const { result } = await run('skillopt-workflow.js', ARGS, skilloptBase({
      responses: {
        harvest: { ready: true, domain: 'dev', due: [{ class: 'c', count: 3, kind: 'log' }], signals: [], success_due: [{ target: 't', class: 'c', count: 2 }], success_signals: [{ engagement: 'e', pattern_class: 'c', primary_target: 't' }], raw_tail: '' },
        'reflect:codex:failure': null,
        'reflect:codex:success': { codex_ran: true, reasoning: 'r', edits: [{ op: 'append', target: 'skills/foo/SKILL.md', content: 'x', pattern_class: 'c', source_type: 'success', support_count: 2, cross_check: 'g' }] },
      },
    }))
    check('the surviving edit stays on the reinforcement channel',
      result.proposedByChannel && result.proposedByChannel.corrective === 0 && result.proposedByChannel.reinforcement === 1,
      JSON.stringify(result.proposedByChannel))
  }

  console.log('\n6. only edits actually applied can reach the mirror')
  {
    const { result, calls } = await run('skillopt-workflow.js', ARGS, skilloptBase({
      responses: { 'promote:': null },
    }))
    check('a dead promote agent stages no MR', !ran(calls, 'stage-mr') && result.draftMR.staged === false,
      JSON.stringify(result.draftMR))
  }

  console.log('\n7. a dry run writes nothing')
  {
    const { calls } = await run('skillopt-workflow.js', { ...ARGS, dryRun: true }, skilloptBase())
    for (const forbidden of ['promote:', 'diff-guard', 'slow-update', 'rollback', 'stage-mr', 'record:director', 'meta:director']) {
      check(`no ${forbidden} agent ran`, !ran(calls, forbidden), calls.join(','))
    }
  }

  console.log('\n8. the harness loop has the same restore point')
  {
    const { result, calls } = await run('harnessopt-workflow.js', HARGS, harnessBase({
      responses: { 'diff-guard': { ran: true, clean: false, newly_touched: ['scripts/zzz.py'], violations: ['scripts/zzz.py'], detail: 'd' } },
    }))
    check('a proven violation rolls back', ran(calls, 'rollback') && result.rollback.ran === true, calls.join(','))
    check('  and stages no MR', !ran(calls, 'stage-mr'), calls.join(','))
    check('  and records nothing', !ran(calls, 'record:director'), calls.join(','))
  }
  {
    const { result, calls } = await run('harnessopt-workflow.js', HARGS, harnessBase({
      responses: {
        'diff-guard': { ran: true, clean: false, newly_touched: ['scripts/zzz.py'], violations: ['scripts/zzz.py'], detail: 'd' },
        rollback: null,
      },
    }))
    check('a failed rollback hard-stops', result.ok === false && result.status === 'rollback-failed', JSON.stringify(result).slice(0, 200))
    check('  and stages no MR', !ran(calls, 'stage-mr'), calls.join(','))
  }
  {
    const { result, calls } = await run('harnessopt-workflow.js', HARGS, harnessBase({
      responses: { snapshot: { taken: false, dir: 'd', files: [], baseline_dirty: [], detail: 'failed' } },
    }))
    check('no snapshot, no apply', result.ok === false && result.status === 'snapshot-failed', JSON.stringify(result).slice(0, 200))
    check('  and no patch was applied', !ran(calls, 'promote:'), calls.join(','))
  }

  const failed = results.filter(r => !r).length
  console.log(`\n${results.length - failed}/${results.length} checks passed`)
  return failed ? 1 : 0
}

main().then(c => process.exit(c)).catch(e => { console.error(e); process.exit(1) })
