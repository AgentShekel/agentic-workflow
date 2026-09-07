---
name: engagement-contract
domain: meta
triggers:
  - "loaded by every specialist agent (engineer, designer, copywriter, analyst) via skills frontmatter"
  - "specialist dispatched into an engagement/ directory (criteria.md present in scope)"
  - "writing executor-reports/{name}.md"
description: |
  [PROTOCOL] Minimal contract every dispatched specialist (engineer, designer,
  copywriter, analyst, etc.) follows when running inside an agency engagement.
  Carve-out from engagement-protocol — the specialist subset only, without
  lifecycle / cross-domain / archival detail: the 6 output bullets, evidence
  before claims, no self-spawned subagents, rule-do-not-stall and the
  NEEDS_CONTEXT convention. Preloaded by specialist agents via skills
  frontmatter. Pure reference — no triggers.
---

# engagement-contract

When you are dispatched as a specialist **inside an agency engagement** (your Task-tool invocation cites an `engagement/criteria.md` or a parent lead routed you with engagement context), follow this contract. It keeps engagement state predictable across the dispatch tree without forcing you to load the full 1200-line engagement-protocol.

If you are NOT inside an engagement (the user invoked you directly, no `engagement/` directory, no criteria.md), this contract does not apply — work normally in your domain.

## The contract (6 bullets, non-negotiable)

1. **Read `engagement/criteria.md` first.** Respect frontmatter (`size`, `ux_heavy`, `tools_required`). Acknowledge each `crit-N` you are addressing.

2. **Write only to `engagement/executor-reports/{your-agent-name}.md`** — single output channel, append-only across iterations. Open each iteration with `## Iteration N` heading. **Per-task contract (S2):** if your dispatch includes a contract step, you propose your assertions **IN-BAND** (in your returned result) — you do NOT write `tasks/{id}.md` yourself; the engine/reviewer writes the co-signed file. Proposing in-band is not writing an engagement file, so this bullet (and bullet 3) stay intact.

3. **Source / project files in their normal paths.** Never create rogue files inside `engagement/`. The directory has a closed whitelist (defined in `engagement-protocol` §"Engagement = a directory"); anything outside is a protocol violation and gets REJECTed.

4. **Open your report with Criteria acknowledgement** — bullets citing `crit-N` verbatim (not paraphrased). This is the structural gate that lets validators and the manager trace your output back to scope.

5. **Disclose anti-patterns explicitly.** Skipped tests, hidden UI elements, mocks substituted for real functions, try-except swallow, partial implementations — call them out in your report. Silent shortcuts are caught by validators or the manager later and become REJECT reasons. Self-disclosure does not.

6. **State cross-contract claims verbatim.** If your output depends on another specialist's deliverable ("I assume the auth service returns 401 on expired token"), write that claim verbatim. The top-lead reconciles cross-contract claims in handoff §4 / §4a.

## Evidence before claims

A completion claim in your report is worth exactly the command output behind it. Before you write
that something passes, works, is fixed, renders or is done, run the thing that proves it **in this
iteration** and put the result in the report.

| Claim in your report | What must be behind it | Not enough |
|---|---|---|
| tests pass | that test command's own output, with the counts | a green from a previous iteration, "should pass" |
| lint / typecheck clean | that tool's output and exit code | tests passing |
| build succeeds | the build command, exit 0 | lint passing |
| the bug is fixed | the original symptom reproduced, then gone | the code changed |
| the regression test works | red before the fix, green after | it passes once |
| the artefact is correct | the rendered check (`screens/`, render-eval) | the file exists at the path |

- **A previous iteration's green does not carry forward.** Rework invalidates it. Re-run.
- Partial checks prove the part, not the whole. Name which part you ran.
- If you could not run the proof (tool missing, environment down), write that plainly instead of
  softening the claim. A named blocker is cheaper than a claim the manager has to disprove.
- "Should", "probably", "судя по всему" in front of a completion claim means the proof was not
  run. Run it, or drop the claim.

`hooks/verification-gate.sh` already gates the commit path. This rule covers everything that never
reaches a commit: reports, artefacts, config edits, design and marketing deliverables.

*(Adapted from `verification-before-completion` in obra/superpowers, MIT.)*

## You are a leaf — do not spawn subagents

Inside an engagement you are the executing leaf of the dispatch tree. Do not dispatch subagents of
your own: not helpers to split your task, and never a reviewer of your own work.

Review arrives from the orchestration layer after your report, and it is already scheduled. Every
reviewer a specialist spawns duplicates a review the workflow dispatches anyway — a full extra
seat per task, paid twice, with two verdicts that then have to be reconciled by someone who never
asked for the second one.

If your task is too large for one seat, that is not something you fix by spawning: say so in your
report (see the ruling rules below) so the lead can split it on the next iteration.

## Rule, do not stall

Ambiguity in your brief is work, not a stop condition. When the brief is unclear, incomplete, or
mildly at odds with `criteria.md`, decide the smallest defensible route yourself, **record the
ruling in your report**, and keep going. A recorded ruling the manager can overturn later is
cheaper than a stalled seat.

Record it in one line: what was ambiguous, what you decided, and what evidence you decided on.
That line is what makes the ruling reviewable instead of silent.

Stop and escalate only when the next step is one of:

- destructive or irreversible (data deletion, migration on real data, force-push, release);
- an external action per `CLAUDE.md`: deploy, push to main or production, sending anything
  outward. Deployment is CI/CD only, never manual, and never your call;
- blocked on a credential, account or access you cannot obtain;
- a hard contradiction between `criteria.md` and the brief where either reading changes the
  deliverable materially. That one belongs to the lead, not to you.

Everything else — a missing fixture, an unfamiliar code path, a failing local check, a wording
choice, an ordering choice, a test-shape choice — you decide and record.

**When you genuinely lack context** the engine's status vocabulary is only `done | blocked`, so
signal the difference in `notes`: return `blocked` with `notes` starting `NEEDS_CONTEXT:` followed
by the exact fact you are missing and where you looked for it. A plain `blocked` reads as "cannot
be done"; `NEEDS_CONTEXT:` reads as "re-dispatch me with this one thing" and is far cheaper to
resolve. Never return `done` on partial work to avoid the word blocked — that is the failure the
manager catches later as a REJECT.

## No invented specifics

A number, date, name, title, version or unit that was not in your sources does not appear in
your report. This is a refusal, not a preference: a plausible invented figure passes review
precisely because it is plausible, and it reaches the human carrying the same confidence as a
measured one. When a figure is needed and you do not have it, write that it is missing and name
what would produce it. Full rules for text a person reads: `human-voice`.

## Per-task contract (when A.contracts is on — M/L only, S2)

If your dispatch includes a co-signed contract (`tasks/{id}.md` → `## Contract (co-signed)`): satisfy each assertion's `check_how`, acknowledge the contract in your executor-report, and note any contested assertion ids (those are judged against `criteria.md` directly). The contract is the agreed per-task review rubric; it never replaces `criteria.md` — your work must still satisfy every cited `crit-N`, contract or not. As the owner you PROPOSE assertions in-band (bullet 2); the reviewer co-signs and writes the file. Full schema: `engagement-protocol` §"`tasks/{id}.md` → `## Contract (co-signed)`".

## Event emission (one line, best-effort)

After you finish writing your `executor-reports/{name}.md`, emit one ledger event so the engagement's `events.jsonl` records your completion (observability — leads and sub-engines emit too; without this the orchestration layer is invisible in the ledger). It **never blocks**: if `python` or the ledger is unavailable the command prints a stderr warning and exits 0.

```bash
python ~/.claude/scripts/ledger-emit.py engagement/ --agent {your-agent-name} \
    --type specialist_completed --report executor-reports/{your-agent-name}.md
```

This is the only ledger event a specialist emits — you do not heartbeat (you have no phases). One emit, after the report is written.

## What this contract is NOT

- It is not a substitute for `engagement-protocol`. Leads and managers still load the full protocol; specialists need only this carve-out.
- It does not duplicate domain methodology (`code-writing`, `brand-methodology`, etc.) — those remain your primary workflow skill. This contract overlays engagement-mode requirements on top.
- It does not cover lifecycle (size dispatch, phase transitions, archival), cross-domain handoff, dangerous-op gates, resume policy — those are top-lead / manager / director responsibilities. If you find yourself reasoning about them, you are out of scope for a specialist role.

## Cross-references

- Full lifecycle and whitelist: `engagement-protocol` (loaded by leads/managers).
- Manager's acceptance checks: `acceptance-protocol`.
- Validator routing and pipelines: `validation-pipeline`.
- Authority precedence when this contract conflicts with another source: `engagement-protocol` §"Authority and conflict resolution".
