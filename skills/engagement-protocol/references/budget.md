# Token budget guard + size auto-promote — full rules

Loaded by `engagement-protocol` when the lead reaches Phase 4 (costly
subagent waves begin) or any heartbeat thereafter. Hot-path summary
lives in `engagement-protocol/SKILL.md §"Token budget guard"` — it
points here for the full budget table, exit-code semantics, auto-promote
retroactive consequences, and `handoff-precheck.py` interactions.

## Token budget guard (Tier 14)

Each tier has an empirical token envelope (lead + director combined per iteration):

| size | budget per iter | trigger |
|---|---|---|
| S | 100,000 | one-shot, abnormal if more than 1 iter |
| M | 500,000 | M baseline; 500k×2 = 1M is the realistic cap before user-touch |
| L | 1,500,000 | L baseline; rare engagement should exceed cumulative 4-5M before scope-sync escalation |

Lead runs after every heartbeat from Phase 4 onward (when costly subagent waves happen):

```bash
python ~/.claude/scripts/token-budget.py engagement/ --json
```

Exit codes:
- `0`: usage ≤ 80% × cumulative_budget — on track.
- `0` with `status: warn`: 80% < usage ≤ 100% — finishing strategy, no panic.
- `1` with `status: fail`: usage > 100% — over budget. Lead chooses one:
  1. **Auto-promote tier** (S→M, M→L) via `size-detect.py --auto-promote` if scope grew naturally.
  2. **Scope-sync escalation** with the user via director (per criteria.md mutability rules) — propose deferrals.
  3. **Accept partial**: ship completed atoms, list rest in handoff §11 Known deferrals.

The guard reads `~/.claude/projects/{project}/metrics.jsonl` for `tokens_used` per iteration. When that field is absent (older director runs), the script falls back to `duration_s × 800` token proxy. Director must start including `tokens_used` field per the per-iter metric line.

The guard is a budget signal, not a hard kill switch. Lead can override one iteration with explicit user-touch authorisation in `scope-sync.md`. Demoting tier or under-reporting tokens to dodge the guard = protocol violation; director rejects on next sweep.

## Size auto-promote check (every heartbeat after Phase 2)

After Phase 2 (`plan.md` frozen) and on every heartbeat thereafter, lead runs:

```bash
python ~/.claude/scripts/size-detect.py engagement/ --mode runtime --auto-promote --json
```

The script measures the engagement against tier thresholds (executor-reports count, tasks count, ui_surfaces, diff files/LOC, deploy crossed) and:

- **Exit 0:** observed ≤ current tier. No action — heartbeat as usual.
- **Exit 1:** observed > current tier. With `--auto-promote`, the script:
  1. Rewrites `criteria.md` frontmatter `size:` to the new tier (S→M, M→L; demotion forbidden).
  2. Appends a `## Auto-promote — size X → Y — {ts}` block to `scope-sync.md` documenting the trigger measurements.

Lead acks the promote in the same heartbeat: `next phase: {name}; auto-promoted: {old}→{new}` and adjusts subsequent rigour to match the new tier (e.g. tasks/ now mandatory if promoted to L, §11 now required if promoted to M).

The check is cheap (~50ms, no subprocess fork-out beyond directory scan + handoff.md grep). Skipping it once is fine; never running it across an engagement is the failure mode where lead silently treats an L engagement as M and gets REJECTed by director's `handoff-precheck.py --mode ready`.

`handoff-precheck.py` re-runs the same check at acceptance time (sub-check `size-drift`) — if it sees current still S/M but observations are clearly L, the handoff REJECTs with reason "size drift, lead failed to promote".

### Retroactive consequences of auto-promote

Promotion shifts the **acceptance protocol** to the new tier retroactively. Specifically:

1. **Iteration budget bumps +1** on the promoted engagement (S→M makes M-budget 3 instead of 2; M→L makes L-budget 4 instead of 3). One extra round absorbs the adversary findings on work that was produced under lighter-tier mode.
2. **Adversary pass is required** at handoff regardless of when promotion occurred. S engagements that auto-promote to M will receive Opus adversary review; M engagements promoted to L will receive full consilium. Producer cannot skip adversary by claiming "the work was done under S/M mode".
3. **`scope-sync.md` documents the budget revision**:
   ```markdown
   ## Auto-promote S → M @ 2026-05-09T14:23:00Z
   Trigger metrics: 3 specialists invoked, 8 diff_files, ux_surfaces=2
   New acceptance protocol: M-tier (Opus adversary required at handoff)
   Iteration budget revised: 2 → 3 (one extra round budgeted for adversary findings)
   ```
4. **Validators applicable to the new tier must run** before handoff — if M-tier requires accessibility-validator on ux_heavy and the engagement was produced as S without it, lead must run validator now and fix gaps before submitting.

Lead must address gaps that the new tier requires **before handoff**, not at acceptance. Auto-promote should not surprise the director at acceptance time — heartbeat-driven detection means there is always at least one phase between promote and handoff for the lead to catch up. If lead submits an auto-promoted engagement without addressing the new tier's requirements, `handoff-precheck.py` for the new tier will FAIL on missing artefacts (e.g. `tasks-decomposition` check fails on M→L without `tasks/INDEX.md`).
