# Engagement abort — full protocol

Loaded by `engagement-protocol` when the user issues an explicit abort
directive mid-engagement. Hot-path summary lives in
`engagement-protocol/SKILL.md §"Engagement abort"` — it points here for
the full archival flow and the not-an-abort cases.

## When user pulls the plug mid-engagement

When the user says "стоп / забей / закрой" mid-engagement (any iteration, even before iter 1 handoff):

1. The role currently holding the floor (lead, secretary, or director) writes a stub `acceptance-log.md`:

   ```markdown
   ## Iteration {current} — {YYYY-MM-DD HH:MM}

   ### Verdict: ABORTED

   Reason: user requested abort.
   User message reference: "{verbatim quote of user's stop directive}"

   State at abort:
   - Iteration: {N}
   - Last director verdict (if any): {ACCEPT / REJECT / none}
   - Specialists dispatched: {list}
   - Artefacts produced: {list}
   ```

2. Run archival with abort flag:

   ```bash
   python ~/.claude/scripts/engagement-archive.py --reason aborted
   ```

   This moves `engagement/` → `engagement-archived/{date}-{name}-aborted/primary/`. Sanity checks (criteria.md exists, ACCEPT verdict present) are skipped under `--reason aborted`.

3. Print one user-facing line confirming archive:

   ```
   Engagement {name} прерван и заархивирован: engagement-archived/{date}-{name}-aborted/
   ```

4. No further iteration/handoff/director action. Engagement is closed.

## When NOT to abort

If user says "не уверен / подожди / давай по-другому" — that is NOT an abort. That's a scope clarification, route to:
- secretary if criteria are wrong (loop-to-intake protocol)
- lead if approach is wrong (request fresh dispatch with new constraints)

Abort is reserved for explicit termination: "стоп", "забей", "закрой engagement", "не делай это", "отменяю".
