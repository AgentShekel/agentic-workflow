# S-tier acceptance

> Loaded from `acceptance-protocol` SKILL.md when `criteria.md` frontmatter `size: S`.

**No director phase.** Producer (Sonnet typically) self-attests, mechanical checks gate, human accepts.

## Steps

1. **Producer writes `handoff.md`** (1 page max), including a self-attestation block: `## Self-attestation` with **1 honest concern** (not "all good" — a real reservation).
2. **Lead runs mechanical pre-check:**
   ```bash
   python ~/.claude/scripts/handoff-precheck.py engagement/
   ```
   Tier=S → 6 critical checks (criteria-frontmatter, whitelist, preflight, handoff-paths, danger-scan, verdict-canonical). Exit 0 = green.
3. **Human reads handoff.md** (it's short, actually read it, not skim).
4. **Human writes verdict** in `engagement/acceptance-log.md`:
   ```markdown
   ### Verdict: ACCEPT
   {1-line rationale}

   ## Iteration 1 — {YYYY-MM-DD HH:MM}
   ### Criteria check
   {brief — bulletpoint per done-when, ✓ / ✗}
   ### Notes
   {if any}
   ```
   Or `### Verdict: REJECT` with directive ("rework X" or "abandon — not worth fixing").

   The canonical S-tier verdict template lives in [verdict-format.md](verdict-format.md) §"S-tier verdict template".

## S-tier iteration

**1 iteration max.** REJECT → human gives directive (rework / abandon), not auto-loop. If S-engagement needs more than 1 round, criteria are wrong (route to `agency-intake` for re-spec) or scope was understated (auto-promote to M, see [process-rules.md](process-rules.md) §"Auto-promote handling").

## When NOT to use S-tier acceptance

- `ux_heavy: true` AND the change touches accessibility-sensitive surfaces → run accessibility-validator before accepting (tier-independent rule)
- `danger-scan` flagged ops without user-OK → REJECT regardless of tier
