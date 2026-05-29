# Engagement archival (engagement-protocol reference)

> Loaded on demand by the manager (acceptor) when writing ACCEPT verdict
> on an engagement, OR by any session that needs to retry a previously-
> failed archival. Carved out of the main engagement-protocol body in
> the references/ split.

After the manager writes ACCEPT in `acceptance-log.md`, the engagement directory is archived to free the slot for the next engagement. Without archival, leftover artefacts pollute whitelist scans and create cross-engagement confusion (old screens look like current ones, stale plan.md misleads new lead).

Manager performs archival via the canonical script — never by hand-rolling `mv`. Script handles name extraction, collision-suffix, sanity checks (criteria.md exists + ACCEPT verdict present):

```bash
python ~/.claude/scripts/engagement-archive.py
```

Order matters: the verdict and user-facing summary go FIRST, archival LAST. If archival fails (permissions, collision unresolvable), it never affects the user-delivery message — they already got the verdict. Manager retries archival or surfaces the failure as an internal note.

For aborted / rejected engagements (rare — only when user closes engagement without ACCEPT), use `--force`. Default refuses to archive without an ACCEPT verdict to prevent accidental loss of in-progress state.

## Order of operations on ACCEPT (and what to do if archival fails)

Strictly: **verdict → user-facing summary → archival**. Archival is the LAST action, not the first. If archival fails, the user has already received the verdict and the deliverables — no rollback needed; the engagement is logically closed.

1. Manager writes ACCEPT verdict in `engagement/acceptance-log.md` with criteria trace.
2. Manager runs `python ~/.claude/scripts/handoff-paths-check.py engagement/acceptance-log.md` — if any phantom path in evidence column, fix verdict before proceeding.
3. Manager composes user-facing summary (Russian, lists deliverables verbatim).
4. Manager runs `python ~/.claude/scripts/engagement-archive.py`.
5. If archival succeeds: print archived-to path, done.
6. If archival fails (collision unresolvable, permissions, disk full):
   - **Do NOT undo the verdict.** The user has the deliverables; engagement is closed.
   - Log the archival error in a new section `## Archival pending — {timestamp}` at the end of `acceptance-log.md`.
   - User is notified once: "Engagement принят, артефакты доставлены. Архивация не сработала: {error}. Повторю после {fix}."
   - Manager (or any later session) retries `engagement-archive.py` once the blocker is cleared. Script is idempotent — re-running on already-archived state is a no-op.

## Archival never blocks user delivery

The user-facing message goes BEFORE archival. If you swap the order, an archival hiccup becomes a perceived failure of the engagement itself. The agency-model contract is: deliverables + verdict are user-visible artefacts; archive is internal bookkeeping.

Archive directory:
- `engagement-archived/` lives in the project working directory.
- One subdirectory per completed engagement: `{YYYY-MM-DD}-{engagement-name}/`.
- Contents preserved as-is (criteria.md, handoff.md, acceptance-log.md, executor-reports/, validation-log.md, screens/, traces/) — kept for audit-trail and future cross-reference.
- Never delete archives without user instruction.

If a new engagement starts in the same project: `agency-intake` creates a fresh `engagement/` directory; archival happened on the previous one already, so there are no collisions.

Pre-archival sanity check (manager runs before mv):
- `criteria.md` exists (we're archiving a real engagement, not random folder).
- `acceptance-log.md` exists with at least one ACCEPT verdict (don't archive engagements that never reached accept).
- No new engagement is mid-flight in this directory (no `engagement/` already exists at target archive path).

If the user asks to re-open / reference an archived engagement: read `engagement-archived/{date}-{name}/` directly. Do not unarchive (move back) — that would make the new engagement collide with the old.
