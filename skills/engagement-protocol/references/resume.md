# Resume policy — interrupted iterations

Loaded by `engagement-protocol` when a lead is resuming an iteration that
was interrupted (Task tool cancelled, context compaction, manual user
stop). Hot-path summary lives in `engagement-protocol/SKILL.md §"Resume
policy"` — it points here for the full per-artefact reuse rules.

## Resume protocol

If a lead's previous session was interrupted mid-iteration (Task tool cancelled, context compaction, manual user stop) and a new dispatch resumes the same iteration N:

1. **Inspect existing engagement state first.** Files from prior session may include partial executor-reports, traces, screens, partial hybrid build, etc. They are not invalid by virtue of being from an interrupted session — but they are not automatically valid either.

2. **Decide per-artefact: reuse or regenerate.** Heartbeat at the resume point MUST list which artefacts you reuse vs regenerate:

   ```markdown
   ## Heartbeat — Phase Resume — completed {ts}
   - iteration: {N} (resumed)
   - artefacts reused-from-prior-session: traces/iter-N/nav-anchor-click.json (validated still represents current code), executor-reports/X.md (Phase 3 work intact)
   - artefacts regenerated: screens/iter-N/light/*.png (re-captured against latest code), validation-outputs/* (validators re-run on resume)
   - artefacts deleted: scope-sync.md (legacy from prior intent that was superseded)
   - next phase: {name}
   ```

3. **Reuse criteria:**
   - Trace JSON is reusable IFF its `captured_at` is newer than the most recent code change AND the artefact under test is unchanged.
   - Screens are reusable IFF the surface they capture is unchanged since they were taken.
   - Validator outputs are reusable IFF the artefact they validated is unchanged.
   - Executor reports are reusable IFF the specialist's work isn't being redone.

4. **Stale = regenerate, no shortcut.** Reusing a trace or screen that doesn't represent current state is the silent-failure mode this rule prevents. If unsure → regenerate.

5. **Trace `captured_at`:** validators (ux-review) and `trace-schema-check.py` warn if `captured_at` is older than the file mtime of any artefact the trace references. Lead must regenerate or update the trace.
