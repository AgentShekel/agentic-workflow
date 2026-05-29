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
  Carve-out from engagement-protocol — the 6-bullet specialist subset only,
  without lifecycle / cross-domain / archival detail. Preloaded by specialist
  agents via skills frontmatter. Pure reference — no triggers.
---

# engagement-contract

When you are dispatched as a specialist **inside an agency engagement** (your Task-tool invocation cites an `engagement/criteria.md` or a parent lead routed you with engagement context), follow this contract. It keeps engagement state predictable across the dispatch tree without forcing you to load the full 1200-line engagement-protocol.

If you are NOT inside an engagement (the user invoked you directly, no `engagement/` directory, no criteria.md), this contract does not apply — work normally in your domain.

## The contract (6 bullets, non-negotiable)

1. **Read `engagement/criteria.md` first.** Respect frontmatter (`size`, `ux_heavy`, `tools_required`). Acknowledge each `crit-N` you are addressing.

2. **Write only to `engagement/executor-reports/{your-agent-name}.md`** — single output channel, append-only across iterations. Open each iteration with `## Iteration N` heading.

3. **Source / project files in their normal paths.** Never create rogue files inside `engagement/`. The directory has a closed whitelist (defined in `engagement-protocol` §"Engagement = a directory"); anything outside is a protocol violation and gets REJECTed.

4. **Open your report with Criteria acknowledgement** — bullets citing `crit-N` verbatim (not paraphrased). This is the structural gate that lets validators and the manager trace your output back to scope.

5. **Disclose anti-patterns explicitly.** Skipped tests, hidden UI elements, mocks substituted for real functions, try-except swallow, partial implementations — call them out in your report. Silent shortcuts are caught by validators or the manager later and become REJECT reasons. Self-disclosure does not.

6. **State cross-contract claims verbatim.** If your output depends on another specialist's deliverable ("I assume the auth service returns 401 on expired token"), write that claim verbatim. The top-lead reconciles cross-contract claims in handoff §4 / §4a.

## What this contract is NOT

- It is not a substitute for `engagement-protocol`. Leads and managers still load the full protocol; specialists need only this carve-out.
- It does not duplicate domain methodology (`code-writing`, `brand-methodology`, etc.) — those remain your primary workflow skill. This contract overlays engagement-mode requirements on top.
- It does not cover lifecycle (size dispatch, phase transitions, archival), cross-domain handoff, dangerous-op gates, resume policy — those are top-lead / manager / director responsibilities. If you find yourself reasoning about them, you are out of scope for a specialist role.

## Cross-references

- Full lifecycle and whitelist: `engagement-protocol` (loaded by leads/managers).
- Manager's acceptance checks: `acceptance-protocol`.
- Validator routing and pipelines: `validation-pipeline`.
- Authority precedence when this contract conflicts with another source: `engagement-protocol` §"Authority and conflict resolution".
