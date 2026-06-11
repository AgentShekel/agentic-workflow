---
name: acceptance-protocol
domain: meta
triggers:
  - "loaded by every *-manager agent via skills frontmatter"
  - "writing acceptance verdict (ACCEPT / REJECT / DIRECTED)"
  - "adjudicating producer vs adversary findings (consilium SUSTAINED / OVERRULED / FALSE_POSITIVE)"
  - "appending per-engagement reflection on M/L"
  - "deciding whether to escalate at round 3"
description: |
  [PROTOCOL] Tier-aware per-engagement acceptance methodology shared by all agency
  managers (marketing / dev / design). Defines per-tier (S/M/L) protocols: S has no
  manager phase, M adds Opus adversary, L adds cross-family consilium. Managers are JUDGES
  between producer and adversary, not re-runners. Reference-only — loaded by
  `*-manager` agents via skills frontmatter, not triggered by keywords.
---

# Acceptance protocol (tier-aware)

> **Naming note:** throughout this protocol, **"director"** denotes the per-engagement
> **acceptor** role — implemented by the `*-manager` agents (`dev-manager`,
> `design-manager`, `marketing-manager`). The senior `*-director` agents are a *separate*
> role: the system-optimizers that improve the skill/agent corpus (see
> `system-optimization-protocol`); they never accept engagements. Read every "director"
> below as "manager / acceptor". (Script names like `director-verdict-check.py` are
> unchanged — they check the verdict artefact, not the agent name.)

Acceptance scales with engagement tier. The same engagement at tier S, M, and L receives different rigour:

| Tier | Director phase? | Adversary | Validator coverage |
|---|---|---|---|
| S | No (producer self-attest + mechanical + human glance) | None | Per domain + ux_heavy, minimal set |
| M | Yes, lightweight (judge between producer + 1 adversary) | Opus adversary in fresh subprocess | Per domain + ux_heavy, typical 1-3 |
| L | Yes, full (judge between producer + consilium of 5) | Opus + 2× Codex + Sonnet + Haiku consilium | All applicable validators |

Tier is read from `engagement/criteria.md` frontmatter `size: S|M|L`. The acceptance phase **dispatches to the matching per-tier reference below**.

## Where this skill ends and per-domain manager starts

This skill defines GENERIC acceptor behavior shared by all 3 domain managers (`dev-manager`, `design-manager`, `marketing-manager`). The agent files contain only domain-specific contracts:

- **Required validators per domain** (e.g., security-auditor for dev; critique + accessibility for design; reality-checker + skeptic for marketing)
- **Domain red flags that force REJECT** (e.g., migration without rollback for dev; brand-token-propagation failure for design; ranking-without-source-date for marketing)
- **Domain-specific anti-patterns** (e.g., "don't edit source files" for dev; "don't open Figma" for design; "don't rewrite copy" for marketing)
- **Common scope-sync questions** (domain-flavored)
- **Tool-unavailability special cases** (Playwright/Figma for design; Yandex APIs for marketing)

Tier dispatch, verdict template, mechanical post-check, scope-sync protocol, escalation, iteration loop — **all live in this skill** (this hub routes to the per-tier and cross-tier references). If you're modifying generic acceptor behavior, edit this skill (one place, three managers benefit).

## Role boundary

Directors do not plan, do not dispatch executors, do not write deliverables, **do not re-run validators independently**. They judge the lead's handoff against criteria, informed by adversary findings (M/L) or producer self-attestation (S).

| Action | Lead | Director |
|---|---|---|
| Capture intake | ✗ | ✗ (secretary does) |
| Plan engagement | ✓ | ✗ |
| Dispatch executors | ✓ | ✗ |
| Run validators (security / accessibility / code-reviewer / etc.) | ✓ (required before handoff) | ✗ (judges results) |
| Run adversary (M/L only) | ✗ (script invocation, not lead authoring) | Triggers via `adversary_lg.py` |
| Judge against criteria | ✗ | ✓ |
| Write verdict | ✗ | ✓ (M/L only) |
| Return to user | Lead on S; director on M/L | ✓ |

**Re-running a validator is allowed only on L-tier and only when adversary findings explicitly identify a validator-coverage gap.** Maximum 1 re-run per validator per iteration. Sweep-style "re-run everything" is forbidden — same brain produces same verdict, no new information.

## Tier dispatch (read criteria.md frontmatter, follow your tier's protocol)

```yaml
# engagement/criteria.md frontmatter
---
engagement: ...
domain: ...
size: S | M | L      # ← dispatch by this field
ux_heavy: ...
tools_required: ...
---
```

If `size` is missing or invalid → treat as M (safe default). Verify via `python ~/.claude/scripts/handoff-precheck.py engagement/` (it reports tier in TL;DR).

**Follow the protocol for the dispatched tier — that IS the act of accepting:**

- **S** → follow [s-tier.md](references/s-tier.md) — producer self-attest + mechanical + human glance; 1 iteration; no manager phase.
- **M** → follow [m-tier.md](references/m-tier.md) — lightweight manager, 1 Opus adversary, two-pass consilium, human-as-judge flow, 2 iterations.
- **L** → follow [l-tier.md](references/l-tier.md) — full 5-reviewer cross-family consilium, cross-family obligations, 3 iterations.

**Every tier also applies, in addition to its per-tier steps:**

- the cross-tier rules in [cross-tier-rules.md](references/cross-tier-rules.md) — consilium fidelity/provenance cross-check (M/L), ux_heavy gradient, validator selection, danger-scan, per-engagement reflection + SkillOpt readiness, engagement-directory layout.
- the process rules in [process-rules.md](references/process-rules.md) — iteration loop + escalation triggers, scope sync (M/L), auto-promote handling, observability.
- the verdict format in [verdict-format.md](references/verdict-format.md) — binary ACCEPT/REJECT (no conditional), canonical templates per tier, adjudication marker reference, path verification.

## Anti-patterns

- **Don't issue `ACCEPT CONDITIONAL` or any non-binary verdict.** Tool unavailability = REJECT with `validation incomplete`.
- **Don't accept "user will verify"-style claims.** Agency exists to remove that burden.
- **Don't plan or redirect lead's approach.** Reject with evidence, let lead rework.
- **Don't fix artefacts yourself.** Even one-line fix belongs to the lead. Acceptor, not co-author.
- **Don't accept with "LGTM".** Every accept references the criteria trace.
- **Don't reject on style / taste alone.** Only on criteria mismatch, validator failures, contradictions, unsupported claims, out-of-whitelist files.
- **Don't re-run validators in sweep style.** That's the old protocol. M/L use adversary for second opinion. Validator re-run only when adversary findings identify specific coverage gap (max 1 per validator per iter, L only).
- **Don't run director phase on S-tier.** S has no director. Producer self-attest + mechanical + human glance.
- **Don't skip adversary on M.** That's the whole point of M acceptance — adversary breaks framing contamination.
- **Don't skip consilium on L.** Single Opus adversary on L misses cross-family blind spots.
- **Don't skip the consilium because it "looks unavailable."** It runs in-session via subprocess `claude -p` (self-bootstrapping venv, off-PATH binary discovery, read-tool grant — see Runbook in [m-tier.md](references/m-tier.md) §step 4). A permission/PATH/venv error is a bug to fix or escalate ONCE, never grounds to accept M/L without it. Substituting independent-validator coverage for the mandatory consilium is a silent skip (the dispatch-gap that forced this, and the reviewer empty-timeout hang, have both been fixed and field-confirmed — "adversary_lg hangs" is no longer a valid waiver).
- **Don't loop silently.** Escalate immediately on repeating critique. Counter-based escalation is the floor.
- **Don't write "slot N/M" anywhere.** Slot language banned across all agency artefacts.
- **Don't demote tier mid-engagement.** Auto-promote is one-way; if scope shrinks, acceptance still uses higher tier.
