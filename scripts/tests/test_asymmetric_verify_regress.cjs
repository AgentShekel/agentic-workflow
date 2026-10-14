#!/usr/bin/env node
/**
 * Regression guard: the engine's adversarial verify is asymmetric.
 *
 * Before: the verifier was told "default is_real=false if it is noise/non-issue/unsupported",
 * the writer kept only is_real==true and DROPPED the rest, and a verifier that died (null) also
 * dropped its finding. A lazy or failed refutation could erase a true finding before the
 * consilium ever saw it.
 *
 * Now (decided in engine JS, not left to the writer agent):
 *   confirmed   is_real == true                                   -> kept (FINAL list)
 *   refuted     is_real == false AND confidence >= 0.8            -> moved to refuted_advisory,
 *                                                                    kept with its rationale
 *   uncertain   anything else: low-confidence refutation, missing -> kept (FINAL list); a doubt is
 *               confidence, a verifier that returned nothing        not a refutation
 *
 * Run: node test_asymmetric_verify_regress.cjs
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ENGINE = path.resolve(__dirname, '..', '..', 'workflows', 'engagement-workflow.js')
const src = fs.readFileSync(ENGINE, 'utf8')
let failures = 0
let total = 0
function check(label, ok, detail) {
  total += 1
  if (!ok) failures += 1
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${ok ? '' : ' -- ' + (detail || '')}`)
}

const START = '// ---- asymmetric adversarial verify'
const END = '// ---- end asymmetric verify ----'
const a = src.indexOf(START)
const b = src.indexOf(END)
check('A the decision function is present between its markers', a >= 0 && b > a)
let verifyDecision = null
let MIN = null
if (a >= 0 && b > a) {
  const body = src.slice(a, b)
  ;({ verifyDecision, REFUTE_MIN_CONFIDENCE: MIN } = new Function(body + '\nreturn { verifyDecision, REFUTE_MIN_CONFIDENCE }')())
}
if (verifyDecision) {
  const cases = [
    [null, 'uncertain', 'a verifier that returned nothing does not refute'],
    [{ is_real: true, confidence: 0.1 }, 'confirmed', 'is_real=true is confirmed whatever the confidence'],
    [{ is_real: false, confidence: 0.9 }, 'refuted', 'a confident refutation refutes'],
    [{ is_real: false, confidence: 0.8 }, 'refuted', 'the threshold itself refutes'],
    [{ is_real: false, confidence: 0.79 }, 'uncertain', 'a doubtful refutation keeps the finding'],
    [{ is_real: false }, 'uncertain', 'a refutation without confidence keeps the finding'],
    [{ is_real: false, confidence: 'high' }, 'uncertain', 'a non-numeric confidence keeps the finding'],
    [{ is_real: false, confidence: '0.95' }, 'refuted', 'a numeric string is read as a number'],
  ]
  for (const [v, want, why] of cases) check(`B ${why}`, verifyDecision(v) === want, `got ${verifyDecision(v)} for ${JSON.stringify(v)}`)
  check('B the refutation threshold is 0.8', MIN === 0.8, String(MIN))
}

const verifyCall = src.slice(src.indexOf('adversarially verify ONE validator finding') - 200, src.indexOf("label: `verify:${v}#${i}`"))
check('C the verifier is no longer told to default to is_real=false', !/default is_real=false/.test(verifyCall), verifyCall.slice(0, 300))
check('C the verifier is told the 0.8 bar and that doubt keeps the finding',
  /0\.8/.test(verifyCall) && /uncertain|cannot (?:demonstrate|locate|confirm)/i.test(verifyCall), verifyCall.slice(0, 400))
const schema = src.slice(src.indexOf('const VERDICT_SCHEMA'), src.indexOf('const WRITER_SCHEMA'))
check('C the verdict schema requires a numeric confidence', /required:[^\]]*'confidence'/.test(schema) && /confidence:\s*\{\s*type:\s*'number'/.test(schema), schema)

const w0 = src.indexOf('Write validator proof-of-run files')
const writer = src.slice(w0, src.indexOf("label: 'validation-writer'", w0))
check('D the writer no longer drops refuted findings', !/DROP refuted/.test(writer), writer.slice(0, 300))
check('D the writer keeps confirmed AND uncertain in the FINAL list', /decision[^\n]*(confirmed|uncertain)[^\n]*(confirmed|uncertain)/.test(writer), writer.slice(0, 400))
check('D refuted findings are written to refuted_advisory with their rationale', /refuted_advisory/.test(writer) && /rationale/.test(writer), writer.slice(0, 400))
check('D the writer payload counts uncertain', /"uncertain"/.test(writer), writer.slice(0, 400))
const trim = src.slice(src.indexOf('function trimForWriter'), src.indexOf('// ---- S8c'))
check('D trimForWriter hands the writer the engine-computed decision', /decision:\s*verifyDecision\(/.test(trim), trim)

console.log(`${total - failures}/${total} passed`)
process.exit(failures ? 1 : 0)
