---
name: agency-intake
domain: meta
triggers:
  - 'user says "мне надо агенси задачу" / "агенси задача" / "задача для агенси"'
  - 'user says "agency task" / "agency work" / "route agency"'
  - "starting any new agency engagement (criteria not yet locked)"
description: |
  [PROTOCOL] Single intake point for any agency task (marketing / dev / design).
  Classifies the domain, captures acceptance criteria, hands off to the
  matching domain lead. Does not plan, dispatch, or execute work.

  Use when: "мне надо агенси задачу", "агенси задача", "задача для агенси",
  "agency task", "agency work", "route agency".
---

# agency-intake

Intake layer. Captures the brief, pins acceptance criteria, hands the engagement to one domain lead. Directors and leads never touch the user at this stage.

## Inputs

- `$ARGUMENTS` — the task description (may be empty).

## Steps

### 0. Engagement collision check (run FIRST, before any classification)

Before doing anything else, check if an active engagement already exists in CWD:

```bash
[ -d engagement ] && [ -f engagement/criteria.md ] && echo "EXISTS"
```

If `engagement/` exists with `criteria.md`:
- Read `engagement/acceptance-log.md` if it exists.
- If latest verdict is ACCEPT but archival hasn't run → run `python ~/.claude/scripts/engagement-archive.py` autonomously to free the slot, then proceed to step 1 with a fresh `engagement/`.
- If latest verdict is REJECT or no verdict yet → ask user ONE question:
  ```
  Активный engagement обнаружен: {name}, текущий статус: {iteration N, last verdict}.
  Это:
  1) Продолжение того же engagement (приму твою новую задачу как поправку scope)
  2) Новый engagement (тогда архивирую активный как `engagement-aborted/...`)
  ```
  Wait for choice before proceeding.

If `engagement/` does not exist or is empty → proceed normally to step 1.

This step prevents the silent collision class where intake overwrites in-progress `criteria.md`, breaking the active engagement without anyone noticing.

### 1. Read the task

If `$ARGUMENTS` is empty, ask one question:

> Что делаем? Коротко опиши задачу.

Wait for reply. Do not classify until you have a concrete task.

### 2. Classify the domain

Pick one of three:

| Domain | Signals |
|---|---|
| `marketing` | SEO, PPC, Yandex Direct/Metrika/Wordstat, копирайт, AI visibility, кампании, баннеры, трафик, семантика |
| `dev` | фичи, баги, архитектура, рефакторинг, деплой, CI/CD, тесты, тех-спеки, инфраструктура |
| `design` | бренд, лого, дизайн-система, UI, UX, иллюстрации, презентации, CIP, иконки |

If signals cross two domains — proceed as **cross-domain**: a primary engagement and a sequenced secondary engagement. Rules in step 8.

If still unclear after one read — ask ONE targeted question. Never dump a menu of three.

### 3. Classify ux_heavy flag

Before writing criteria, decide whether the engagement is `ux_heavy: true`. This flag is the single biggest determinant of validation rigour downstream — it triggers mandatory `screens/`, `traces/`, §6 Exercised, and `ux-review` validator.

Mark `ux_heavy: true` if ANY signal:

- Task touches visual hierarchy, layout, typography, color, spacing, or motion.
- Deliverables include "looks like / feels like / matches mockup".
- Brief contains screenshots OR words of taste ("clean", "professional", "modern", "minimal", "тонкий", "вкусный", "удобный").
- Domain is `design` AND output is a UI surface (not a brand voice doc).
- Domain is `dev` AND task is "frontend / UI redesign / dashboard / landing".
- Domain is `marketing` AND task is "live landing / campaign creative going to a URL".

Mark `ux_heavy: false` if engagement is purely backend / infra / data / SEO / analytics / brand strategy text — anything where artefact correctness is objectively testable without a browser.

Edge case: brand-only design work (voice guidelines, logo SVG) → `ux_heavy: false`. Logo+CIP+landing → `ux_heavy: true`.

Borderline call → default to `ux_heavy: true`. The cost of unnecessary screens is one extra Playwright capture; the cost of missing them is the loop that broke Wave 2.

### 4. Identify required tools

List every tool the validation pipeline will need to verify acceptance. This goes into `tools_required` frontmatter:

| Engagement type | Tools usually required |
|---|---|
| Frontend / UI / dashboard | `docker`, `playwright`, frontend dev server (e.g. `bun`, `npm`) |
| Backend API | `docker`, `postgres` (or project DB), `python` / `node` runtime |
| Full-stack feature | `docker`, `playwright`, DB, runtime |
| Marketing landing live to URL | `playwright`, browser-preview |
| SEO audit | Yandex API tokens (in env) |
| PPC campaigns | Yandex Direct API token, OAuth refresh |
| Brand voice doc | none |

Add to `tools_required` frontmatter array. Director will use this list during pre-flight check.

### 5. Pre-flight tools check (BLOCKING, run via script — never inline)

Before writing criteria.md and handing off, verify every tool in `tools_required` is reachable. Pre-flight failure ≠ skip the tool — it means BLOCK the engagement until user resolves.

**Do not improvise the check inline.** Use the canonical script — it is deterministic, machine-readable, and exit-coded so the result cannot be hand-waved:

```bash
# MANDATORY --auto-fix flag: script tries safe auto-recovery for failing tools
# (docker compose up, npm install playwright, compose up redis/postgres/db service).
# Auto-fix is whitelisted to non-destructive ops only — never starts Docker Desktop GUI,
# never touches production secrets, never installs runtimes.
#
# Running without --auto-fix is a protocol violation: it skips the cheap recovery
# path and pushes user-touch when not needed.
python ~/.claude/scripts/preflight.py --criteria engagement/criteria.md --json --auto-fix
```

If `--auto-fix` resolves it: tool comes back as `pass` with `auto_fixed: true`. Engagement proceeds; user is informed via the handoff line ("Pre-flight: docker auto-started via compose").

If `--auto-fix` cannot resolve it: tool stays `fail`. THEN escalate user with the script's `fix` message. User-touch is the **last resort**, not the first — Wave-2-style "user starts Docker manually every session" cycle is exactly what we are eliminating.

Supported tool names (extend the script if you need a new one — don't fake a check inline): `docker`, `playwright`, `postgres`, `redis`, `node`, `python`, `bun`, `git`, `gh`, `yandex-tokens`, `openai-key`, `anthropic-key`.

**Capture the script's output in your handoff line to the user** — the user sees the verdict, not your interpretation. If exit code is non-zero (`status: "fail"` in JSON), STOP and print:

```
Pre-flight: следующие инструменты недоступны:
- {tool}: {fix message from script output}

Скажи когда готово — я перезапущу проверку.
```

Wait for user. Re-run the script when they confirm. Do NOT hand off to a lead until the script returns `status: "pass"`. Skipping pre-flight is the root cause of CONDITIONAL accepts that never resolved.

Pre-flight pass: copy the JSON output into `criteria.md` under a `<!-- preflight: ... -->` HTML comment for audit-trail, write `tools_required` in frontmatter, proceed to step 6.

### 5b. Initialise iteration counter

Create `engagement/iteration` with content `1` (the engagement starts at iter-1 — lead's first handoff will increment to 2 for next round only on REJECT).

```bash
echo "1" > engagement/iteration
```

This file is the source of truth for current iteration. Lead reads it before submitting handoff. Director reads + increments on REJECT (engagement/iteration → N+1, ready for lead's next submission). handoff-precheck verifies counter agrees with `## Iteration N` headings in acceptance-log.md.

Without `engagement/iteration` at intake, handoff-precheck will treat the first handoff as "no counter required yet" (skip), but every subsequent iteration will need the file.

### 6. Capture acceptance criteria

Canonical schema lives in `engagement-protocol`. Inline version below is a working copy for secretary convenience — if the two diverge, `engagement-protocol` wins.

Before handoff, write `engagement/criteria.md` in the working directory:

```markdown
---
engagement: {engagement-name}
created: {YYYY-MM-DD}
domain: marketing | dev | design
ux_heavy: true | false
tools_required: [docker, playwright, postgres]
---

# Acceptance criteria — {engagement-name} — {YYYY-MM-DD}

## Scope
(one paragraph from user's task)

## Deliverables expected
- deliverable 1 with measurable bar
- deliverable 2 with measurable bar

## Done when
- bullet-list of observable conditions ("landing live at URL", "report committed", "tests green")

## Explicitly out of scope
- list of things user mentioned but excluded from this engagement

## Review mode
`lean` | `full` | `solo`  (default `lean`)

## Iteration budget
Guidance: 2 rework cycles, then user escalation. Counter informational. Hard cap 4. Escalate immediately on repeating critique.
```

If the user did not state acceptance bars, propose them based on the task and confirm. Director cannot accept against vague criteria.

#### Brief quality gut-check (lightweight)

Before locking criteria, run a quick gut-check on each "Done when" / "Deliverables" bullet:

- Does this bullet name a SPECIFIC observable thing (path, URL, file, visible UI element, numeric threshold)? Or is it vibes ("dashboard looks clean")?
- If the user is asking for a list ("5-6 metrics"), is each list item independently justifiable, or is the list size a placeholder for "I haven't thought through which metrics matter"?

If a bullet is vague → propose a sharper version inline ("Я понял так: {sharp version}. Ок?"). Don't dump 5 questions on the user — propose, confirm.

Note: deeper brief audit (4-question gate per bullet) happens INSIDE the lead at Phase 1a — not here. Secretary does the gut-check; lead does the deep audit. This split keeps intake-time friction low.

### 6b. Size detector advisory (run AFTER drafting criteria.md, BEFORE handoff)

After writing `criteria.md` with your `size:` choice, run the heuristic detector. It compares your choice against keyword/structure signals in the brief and surfaces disagreement before lead picks up the engagement:

```bash
python ~/.claude/scripts/size-detect.py engagement/ --mode intake --json
```

Output is advisory (always exit 0). Read the JSON: if `agreement: false`, reconcile:

- If detector suggests larger (e.g. you wrote `size: S` but it suggests `M` because the brief mentions "редизайн дашборда" + 7 deliverables) — reconsider. Edit `criteria.md` frontmatter to the larger size; `tasks/` decomposition + extra rigour will catch issues that S-tier would have missed.
- If detector suggests smaller — only downsize if you're sure (e.g. brief says "rebrand" but actually means "swap one logo file"). Otherwise keep your call; brief signals trumped a literal keyword.
- If you keep the disagreement, append a one-line note in `<!-- size-detect: disagreement reason -->` HTML comment in criteria.md so the lead's Phase 1 can see why you chose differently.

This is a sanity check, not a hard gate. Lead's Phase 2 has authority to promote (S→M, M→L) at runtime via `size-detect.py --mode runtime --auto-promote` when reality outgrows the intake guess. Demotion is forbidden either way.

### 7. Handoff — run the engagement-workflow Workflow (all domains)

Every engagement (dev / design / marketing) runs through the `engagement-workflow` **Workflow** as the **default pre-gate path**. Each `{domain}-lead` is the Workflow's `lead:plan` planning step (leads PLAN, they do not Task-dispatch). You (the main loop) conduct the cascade. Invoking the Workflow here IS the opt-in — a skill instructing the Workflow call is a valid opt-in path, so no `ultracode` keyword is needed.

**Operating limitation (honest — do not paper over it):** the Workflow tool is **harness-only** — it runs from the interactive main loop, NOT headless (`claude -p`) or cron. Agency work is interactive today, so this is the live path with no current gap. But there is **no warm automated non-Workflow fallback**: if the Workflow tool is unavailable (headless/cron context, or a tool outage), **fail closed** — tell the user the cascade needs an interactive session; do NOT improvise a degraded hand-dispatch (the leads are plan-only by design; an ad-hoc second orchestration would carry weaker guarantees than the gated path). A real headless fallback would mean finishing the archived `scripts/_archive/engagement_lg.py` skeleton (it never shipped — `--real` raises `NotImplementedError`; Waves B–F unbuilt) — future work, not a wired path.

1. **Resolve args** (the script cannot call Date.now, so you stamp the time):
   - `repoDir` = the project root holding `engagement/`. dev (code mode): the git root — `git -C <cwd> rev-parse --show-toplevel`. design/marketing (artefact mode): the project dir / CWD (a git repo is not required).
   - `scriptsDir` = absolute `~/.claude/scripts`.
   - `ts` = `(Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")` (bash: `date -u +%Y%m%dT%H%M%SZ`).
2. **Invoke the Workflow** with the classified domain:
   ```
   Workflow{ name: 'engagement-workflow', args: { repoDir, scriptsDir, ts, domain: '<dev|design|marketing>' } }
   ```
   The `lead:plan` step runs as `{domain}-lead` and sets `deliverable_mode` (dev → code: worktree + octopus + repo tests; design/marketing → artefact: files written to engagement/ paths + manifest-verify). It runs discovery → decompose → deliver → validate → handoff → gate, then **STOPS at the handoff seam**, returning `{ readyForAcceptance, gate, engagementDir }`. It never touches the human-gate.
3. **Gate failed / engine hard-stop** (`readyForAcceptance:false`): read **`error` first, then `gate.failures`** — a PRE-gate hard-stop (malformed plan, or a blocked / crashed / review-failed task in a wave) returns a human-readable `error` plus a stub `gate.failures` and performs NO consolidation; the handoff gate (when reached) returns `gate.failures`. Surface to the user. If the return carries `cleanupCommands`, run them ONLY on a fresh rerun (a `resumeFromRunId` resume reuses the worktrees, so don't clean before resuming). After the fix, re-invoke with `resumeFromRunId` so only changed steps re-run. Tooling-down is the one allowed user-touch — never push validation onto the user otherwise.
4. **Gate passed** (`readyForAcceptance:true`): drive the **post-seam human-gate** — this STAYS LangGraph, the active acceptance path (NOT a fallback). Per `acceptance-protocol`:
   - **S-tier:** no manager phase. Producer self-attest + the gate's mechanical pass + a human glance suffice → archive (step 5).
   - **M/L-tier** — consilium → human gate → acceptor:
     1. One pass — fan out the consilium, auto-synthesize the summary, and pause at the human supreme-judge gate (prints a thread id; writes `consilium-summary.md`). `--interrupt` requires `--consilium`, so they are ONE command — do NOT split them (a second bare `--interrupt` call re-runs the whole consilium and re-spends it):
        ```bash
        python ~/.claude/scripts/adversary_lg.py engagement/ --consilium {M|L} --interrupt
        ```
     2. The human reads `consilium-summary.md`, then resumes with the decision (the resume path writes `human-directive.md`):
        ```bash
        python ~/.claude/scripts/adversary_lg.py engagement/ --resume-interrupt <thread> --decision PROCEED|REJECT|DIRECTED [--reasons '...' on REJECT] [--note ...]
        ```
     3. Dispatch the acceptor via Task: **`{domain}-manager`** (`dev-manager` / `design-manager` / `marketing-manager`) with the `engagement/` path + iteration N. It reads handoff + consilium-summary + human-directive and writes the verdict in `acceptance-log.md` (does NOT sweep-rerun validators).
5. **Resolve verdict:** ACCEPT → free the slot by archiving. `engagement-archive.py`'s positional arg is the PROJECT ROOT (default CWD) — it appends `/engagement` itself, so run it BARE from the project root; passing `engagement/` makes it a silent exit-0 no-op:
   ```bash
   python ~/.claude/scripts/engagement-archive.py
   ```
   REJECT (within budget S=1 / M=2 / L=3) → re-invoke the Workflow with `args.iterN = N+1` for the rework round; escalate to the user before the final allowed round.

Print one handoff line before invoking:

> → Запускаю {domain}-движок (engagement-workflow): {reason}. Критерии: {criteria path}. UX-heavy: {true/false}. Pre-flight: {tools list} ✓.

### 8. Cross-domain handoff

If the task needs two domains (e.g. "сделай лендинг и запусти кампанию" = design + marketing), follow the canonical topology in `engagement-protocol` §Cross-domain — primary in `engagement/`, secondary COEXISTING in `engagement-secondary/{domain}/`, both archived together at the end (the protocol is the single source of truth; if this section ever diverges, the protocol wins):

1. Declare the primary domain (owns final delivery and scheduling) and the secondary (consumes the primary's artefact).
2. Run the **primary** domain's `engagement-workflow` (step 7) to ACCEPT — but do NOT archive it yet (the secondary will read its artefacts).
3. Run the **secondary** domain's `engagement-workflow` into the secondary slot by passing `args.engDir = <repoDir>/engagement-secondary/{secondary-domain}` (the engine already honours `engDir`). Its `criteria.md` lives there and cites the primary's `engagement/` artefacts as inputs. Keep BOTH live — never write secondary state into `engagement/`, never archive the primary while the secondary is still iterating.
4. After BOTH ACCEPT, archive them together into one dated folder: `python ~/.claude/scripts/engagement-archive.py` (primary) + `python ~/.claude/scripts/engagement-archive.py --secondary {secondary-domain}` (secondary). Produce the unified user message only after both ACCEPT.

Three-domain engagements are rejected — split into two engagements and ask user to sequence.

## Anti-patterns

- **Do not plan work yourself.** Planning happens inside the `engagement-workflow` `lead:plan` step (= the `{domain}-lead` agent). Secretary only captures intake and classifies.
- **Do not dispatch specialists directly.** Specialists are reachable only through the Workflow — never from intake.
- **Conducting is intake's job (all domains).** Invoking the `engagement-workflow` Workflow and driving the post-seam human-gate (§7) is routing/conducting — NOT planning or executing yourself (the Workflow does that internally). Do not hand any domain off via `Task({domain}-lead)` expecting it to dispatch — the leads are **plan-only** (the Workflow's `lead:plan` step); they do not orchestrate specialists. The Workflow is the default interactive pre-gate path; there is no warm non-Workflow fallback today (see §7a's operating-limitation note).
- **Do not invoke methodology skills** (seo-audit, code-writing, ui-styling-guide, etc.). Methodologies are reference-only; leads pull them by name as needed.
- **Do not skip criteria.md.** Without it, director has nothing measurable to accept against.
- **Do not skip pre-flight tools check.** Engagement starting with broken validation environment guarantees CONDITIONAL-loop later. Block at intake, save the rework.
- **Do not skip ux_heavy classification.** Default to `true` if uncertain. The cost of an extra Playwright capture is trivial; the cost of missing UI screens is the loop.
- **Do not run the full 4-question brief audit at intake.** That's the lead's Phase 1a. Secretary does only a lightweight gut-check (sharp / vague). Deep audit at intake = user friction wall.
