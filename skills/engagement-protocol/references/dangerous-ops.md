# Dangerous operations registry (engagement-protocol reference)

> Loaded on demand by leads/managers when `danger-scan.py` produces a
> non-empty finding OR when the engagement diff touches schema /
> migrations / production deploy / secrets. Carved out of the main
> engagement-protocol body in the references/ split.

Some operations have heavy / irreversible consequences (data loss, history rewrite, production damage, infra teardown). Validators check correctness, not authorisation. Authorisation is a separate axis: the user must explicitly OK these ops, even if they are technically clean.

## Operations requiring explicit user OK (always)

| Class | Examples | Why user-OK required |
|---|---|---|
| Schema destruction | `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, lossy `ALTER COLUMN TYPE` | Data lost cannot be reconstituted from code. |
| Bulk row deletion | `DELETE FROM x` without `WHERE`, deletes affecting >25 files | Reversal needs backup recovery. |
| History rewrite | `git push --force`, `git reset --hard origin/...` | Teammates' work / audit trail destroyed. |
| Filesystem recursive delete | `rm -rf` on parents, `~`, `$HOME`, root paths | Path mistakes are catastrophic. |
| Migration without rollback | `down()` empty / `raise NotImplementedError` | ACCEPT becomes irreversible. |
| Production deploy | `vercel --prod`, `fly deploy`, `gh release create`, manual `kubectl apply -f prod` | Live impact, customer-visible. |
| Infrastructure teardown | `terraform destroy`, `kubectl delete -n prod` | State loss + customer impact. |
| Secret rotation/deletion | `rotate-secret`, `delete-secret`, `gh secret remove` | Downstream consumers may break silently. |
| Public publish | `npm publish`, `pip upload` (real index, not test) | Cannot fully unpublish. |

## Detection

Lead runs `~/.claude/scripts/danger-scan.py --engagement engagement/` (or `--diff-file ...`) before handoff. The script covers the patterns above plus bulk-delete heuristic. JSON output lists every match with severity (critical/high) and rationale.

`handoff-precheck.py` calls `danger-scan.py` automatically as one of its sub-checks. Non-empty findings → handoff blocked until either (a) each finding has a paired user-OK entry in `scope-sync.md`, OR (b) the operation is removed from the diff.

## User-OK protocol

When `danger-scan` finds a dangerous op, the lead surfaces it to the user via manager-mediated escalation BEFORE merging / applying:

```
Опасная операция в этом engagement:
- {operation kind}: {snippet}
- Последствия: {msg from danger-scan}

Подтверждаешь? (y / n / разъяснить)
```

Lead waits for explicit "y" / "да" / "ок" — silence is NOT consent. On "y": lead writes a confirmation entry in `scope-sync.md`:

```
## Dangerous-op user OK — {YYYY-MM-DD HH:MM}
- {operation id}: {snippet} — user OK on {timestamp} via {user-message reference}
- Backup verified before apply: {yes/no/N-A — backup not applicable for this op}
```

Without this entry, manager rejects with `dangerous operation submitted without user-OK in scope-sync.md`.

## Backups

For schema destruction and bulk delete: lead must verify a recent backup exists BEFORE applying. Mechanical check goes in `scope-sync.md` "Backup verified" line: timestamp + backup location. No backup → operation cannot proceed even with user OK; lead asks user to create backup first.

## What does NOT count as dangerous

- Adding columns / tables / indexes (forward-compatible).
- Test fixture changes.
- Editing source files in any quantity (revertible by git).
- Local `rm` of build artefacts inside project dir (`dist/`, `node_modules/`).
- Deploys to staging / preview environments.
- Engagement archival (`mv engagement engagement-archived/...`).

These do not require user touch and stay autonomous.
