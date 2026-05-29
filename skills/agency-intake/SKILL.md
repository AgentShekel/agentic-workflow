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

If signals cross two domains — proceed as **cross-domain**: primary lead + secondary lead. Rules in step 5.

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

### 7. Handoff to the domain lead

Dispatch the matching lead via the Task tool:

| Domain | Lead agent |
|---|---|
| marketing | `marketing-lead` |
| dev | `dev-lead` |
| design | `design-lead` |

Pass the lead a **minimum-viable prompt** (per `engagement-protocol` §"Task-tool prompts: minimum viable content"):

```
Engagement: {engagement-name}
Iteration: 1
Criteria: {absolute path to engagement/criteria.md}
Review mode: {lean | full | solo}

Read criteria.md first. Engagement context, source paths, and constraints
are inside it — do not re-paste here.

Begin Phase 1. Heartbeat per phase per protocol.

Return summary on completion (or escalation).
```

5-8 lines. Do NOT verbose-paste the user brief, source paths, or protocol reminders — the lead's skills (`engagement-protocol`, domain methodology) already contain those. Verbose prompts cause first-action delay that operators misread as "stalled".

Then stop — do not follow, do not synthesize, do not touch the lead's artefacts.

Print one handoff line to the user:

> → Передаю {lead}: {reason}. Критерии: {criteria path}. UX-heavy: {true/false}. Pre-flight: {tools list} ✓.

### 8. Cross-domain handoff

If the task needs two domains (e.g. "сделай лендинг и запусти кампанию" = design + marketing):

1. Declare the primary domain (owns final delivery and scheduling).
2. Declare the secondary domain (consumed artefact from primary).
3. Hand off ONLY to the primary lead. Pass secondary domain as a downstream dependency in `criteria.md`.
4. Primary lead will invoke secondary lead at the correct stage.

Three-domain engagements are rejected — split into two engagements and ask user to sequence.

## Anti-patterns

- **Do not plan work.** Leads plan. Secretary only captures intake and classifies.
- **Do not dispatch specialists directly.** Specialists are only reachable through leads.
- **Do not invoke methodology skills** (seo-audit, code-writing, ui-styling-guide, etc.). Methodologies are reference-only; leads pull them by name as needed.
- **Do not skip criteria.md.** Without it, director has nothing measurable to accept against.
- **Do not skip pre-flight tools check.** Engagement starting with broken validation environment guarantees CONDITIONAL-loop later. Block at intake, save the rework.
- **Do not skip ux_heavy classification.** Default to `true` if uncertain. The cost of an extra Playwright capture is trivial; the cost of missing UI screens is the loop.
- **Do not run the full 4-question brief audit at intake.** That's the lead's Phase 1a. Secretary does only a lightweight gut-check (sharp / vague). Deep audit at intake = user friction wall.
