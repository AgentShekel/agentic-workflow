# Optional scripts

Scripts that are part of protocol but were never invoked in real engagement traffic. They work — but their value-add wasn't validated under real load. Kept here as opt-in, not auto-invoked.

| Script | Trigger to use it |
|---|---|
| `engagement-doctor.py` | Manual diagnose when engagement state looks corrupted; `--check stalled` if heartbeats absent for >threshold |
| `engagement-migrate.py` | One-shot migration of legacy engagement (no protocol_version, missing iteration counter, etc.); `--include-archived` for archived ones |
| `token-budget.py` | Tier-budget guard (S=100k / M=500k / L=1.5M) |

Promote back to `scripts/` when one of these gets used in ≥2 real engagements with measurable value.

## History (2026-05-28)

The following optional scripts were removed in an earlier cleanup:

- `cross-val-template.py` — never invoked in live skills; cross-val table is now written inline by the lead in handoff §4.
- `director-sweep.py` — orphaned after the manager/director split; managers don't re-run validator sweeps (same brain = no new info).
- `validator-retry.py` — logic absorbed into `validator_lg.py`'s retry edge.
- `secondary-init.py` — was never wired into any cross-domain handoff flow.
- `metrics-summary.py` — no live caller; retrospective metrics deferred to a future LangSmith dashboard.

`size-detect.py` was promoted from `optional/` to `scripts/` root — it's actively invoked by `handoff-precheck.py` and three protocol skills (`agency-intake`, `engagement-protocol`, `acceptance-protocol`), so the `optional/` categorisation was wrong.
