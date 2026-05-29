# Cross-domain handoff (engagement-protocol reference)

> Loaded on demand by leads when an engagement crosses two domains
> (design → marketing, dev → design, etc.). Carved out of the main
> engagement-protocol body to the references/ split to keep the hot-path
> skill ≤500 lines per loader invocation.

Two-domain engagements only. Secretary classifies the primary domain and declares secondary as a downstream dependency in `criteria.md`. Three-domain engagements are rejected at intake — user must split them.

## State location (collision-free)

Primary engagement uses `engagement/` (the canonical path). Secondary engagement uses `engagement-secondary/{domain}/` to avoid overwriting primary state.

```
project-root/
├── engagement/                      # primary (e.g. design)
│   ├── criteria.md
│   ├── handoff.md
│   └── ...
└── engagement-secondary/
    └── marketing/                   # secondary (e.g. marketing)
        ├── criteria.md              # derived from primary's accepted output
        ├── handoff.md
        └── ...
```

`handoff-precheck.py engagement-secondary/{domain}` works on the secondary the same way as on primary. All scripts (preflight, paths-check, danger-scan, archive) accept any directory — they don't hardcode `engagement/`.

## Workflow

1. Secretary writes `engagement/criteria.md` with primary domain + `cross-domain.secondary: <domain>` note.
2. Primary lead completes phases.
3. Primary director ACCEPTs.
4. Primary lead (NOT director) initiates secondary manually:

   - Create `engagement-secondary/{domain}/` with subdirs `executor-reports/` and `validation-outputs/`.
   - Write `engagement-secondary/{domain}/criteria.md` with frontmatter inheriting primary's `engagement` name and project metadata, but fresh `domain: {domain}`, `parent_engagement: ../engagement/`, fresh `size`, `ux_heavy`, `tools_required` defaults.
   - Add a `<!-- inherits from ../engagement/ -->` audit comment at the top of the new `criteria.md`.
   - Initialise the iteration counter at 1 (write `1` to `engagement-secondary/{domain}/iteration`).

5. Primary lead dispatches secondary lead via Task tool with the new `engagement-secondary/{domain}/criteria.md` path.
6. Secondary lead runs its own full engagement cycle in `engagement-secondary/{domain}/`.
7. Secondary director ACCEPTs (or REJECTs into secondary's own iter loop — primary is already done).
8. After secondary ACCEPT, primary director composes unified user message referencing both engagements.

## Archival

On final user delivery (after both ACCEPT'ed):

```bash
python ~/.claude/scripts/engagement-archive.py             # archives primary
python ~/.claude/scripts/engagement-archive.py --root . --secondary marketing   # archives secondary
```

Both end up under one dated archive folder:

```
engagement-archived/
└── 2026-05-06-acme-launch/
    ├── primary/             # mv of engagement/
    └── secondary-marketing/ # mv of engagement-secondary/marketing/
```

## Anti-patterns

- Don't write secondary state into `engagement/` — collision with primary, irrecoverable.
- Don't dispatch secondary lead before primary director ACCEPTs — the secondary depends on primary's accepted output, not work-in-progress.
- Don't archive primary while secondary is still iterating — final unified message comes after both ACCEPT.
