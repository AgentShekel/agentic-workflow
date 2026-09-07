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

### 0b. Voice

Everything this skill says to the user is Russian a person reads. Write it under the rules in
`~/.claude/skills/human-voice/SKILL.md`, chat surface: claim only what you can show, invent no
specifics, no padding, no em dashes. The quoted templates below already follow them; keep any
question you improvise on the same footing.

### 1. Read the task

If `$ARGUMENTS` is empty, ask one question:

> Что делаем? Коротко опиши задачу.

Wait for reply. Do not classify until you have a concrete task.

### 1b. Route class (blocking — runs before any domain work)

Not every request deserves a cascade. Classify the request into one of three route classes and
say the class out loud in one line, so the user can override it before anything else happens.

| Class | Test | What runs |
|---|---|---|
| `direct` | The exact result is already specified and no material decision is left: a named value substitution, a rename with unchanged behaviour, copy supplied verbatim, a read-only check. | No `engagement/`. Do the work here, show the result, stop. |
| `bounded` | One deliverable, one owner, and the flow being changed **already exists in this project** so it can be opened and read before editing. | `criteria.md` with `size: S`. No consilium, no manager phase. |
| `full` | Anything else: a new surface, an unresolved decision that changes observable behaviour, a public contract, security or data lifecycle, more than one specialist. | Normal cascade — step 2 onward; `size-detect.py --mode intake` picks S/M/L. |

**Risk veto (checked FIRST, overrides the table above).** Effort and risk come apart constantly: a
one-line edit to a payment path is the most mechanical and the most dangerous thing in the queue.
Before applying the table, check the `risk: high` signal list from §"Risk class" below:

> auth or authorization, payments or billing, personal data, secrets or keys, a DB migration,
> deletion of anything, a public-facing publish, a production config.

If **any** signal is present, the class is `full` regardless of how specified the result is. No
exceptions, and "но это же одна строка" is the argument the veto exists to defeat. The lighter
classes exist to save ceremony on cheap mistakes, not on expensive ones.

**The veto fires on the action the request asks for, not on a word that appears in it.** Editing
the README description of `API_TOKEN` touches no secret; rotating that token does. Adding a flag
to a publishing endpoint is not publishing; calling it is. Read what the task would actually DO,
then check the list against that. A keyword-matching veto sends half the queue through the full
cascade and gets switched off within a month, which is the same as not having one. This cuts one
way only: when the action is genuinely ambiguous, the ratchet applies and the class is `full`.

The veto is the reason `risk:` cannot wait until step 6: `direct` never writes a `criteria.md`, so
a risk class assigned at step 6 would never be assigned at all for the very tasks that bypass it.

Consequence for `bounded`: it is `size: S`, and the standing rule that `risk: high` forces the
human gate even at S-tier still applies. In practice a `bounded` engagement is never `risk: high`,
because the veto already sent that case to `full`. If you somehow reach step 6 with `bounded` and
`risk: high` in the same engagement, the classification was wrong — upgrade to `full` and say so.

Rules:

- **The ratchet is one-way.** In doubt between two classes, take the heavier one. Complexity
  discovered mid-work upgrades the class: stop, say so, step up. Nothing downgrades mid-work.
- **Familiarity is not boundedness.** `bounded` measures this repository, not your confidence in
  the domain. If there is no existing flow to open and read, the class is `full`.
- **What scales is artefact volume, never the acceptance gate.** A `direct` task still ends with
  the result shown to the user. Skipping the cascade is not skipping their approval.
- Reaching for a lighter class in order to skip work IS the doubt. Take the heavier one.
- Route class is not the size tier. `bounded` is exactly `size: S`; `full` still runs size detection.
- **`direct` is cascade-free, not proof-free.** Show what changed and the output that proves it:
  the changed lines, the command result, the number of occurrences replaced against the number
  asked for. One line of evidence, not a validator run. The rule is the same one specialists
  follow inside an engagement (`engagement-contract` §"Evidence before claims"); only the volume
  scales down.
- **Record every upgrade.** When work started as `direct` or `bounded` and turned out heavier,
  write one line under Scope in the resulting `criteria.md`: `route: upgraded direct → full,
  because {what was discovered}`. That line is the only evidence the classifier ever misfires, and
  it is what later grows `evals/route-evals.json`. An upgrade that leaves no trace teaches nothing.

Say it as one line before continuing, under the `human-voice` rules from step 0b:

> Класс: direct. Здесь заменить одно значение, каскад не нужен, сделаю и покажу результат.

Regression set for this classification: `evals/route-evals.json` (see its `_meta.how_to_run`).

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

Supported tool names (extend the script if you need a new one — don't fake a check inline): `docker`, `playwright`, `postgres`, `redis`, `node`, `python`, `bun`, `git`, `gh`, `yandex-tokens`, `openai-key`, `anthropic-key`, `claude-cli`.

**Run M and L from a terminal-hosted `claude` session, not from the desktop app.** Established
2026-08-31: a nested `claude -p` answers from a terminal session and stays silent from a session
inside the Claude Desktop app. Same binary, same credentials, same argv; version, token and the
inherited `CLAUDE_CODE_*_AUTH_REFRESH` vars were each checked and each refuted. The consilium is
not broken, it is host-constrained. S / `bounded` / `direct` work is unaffected because none of it
touches the headless path. You do not have to remember this: the check below catches it either way.

**`claude-cli` is mandatory in `tools_required` on every M and L engagement.** The consilium is not optional at those tiers and it rides entirely on headless `claude -p`. When that path is down it does not error, it goes silent: `adversary_lg.py` spends the full role timeout on every role and returns empty output, which reads as "the reviewers found nothing" rather than "the headless path is dead". One blocked intake is the cheap outcome; the expensive one is a whole M/L cascade whose consilium was never real. The check costs one trivial model call (about 5s). Do not substitute `claude auth status` for it: on 2026-08-31 that reported `loggedIn: true, subscriptionType: max` while every headless call was already failing.

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
risk: low | medium | high        # reversibility × blast radius — see "Risk class" below
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

## Outcome hypothesis
- metric: {what should change — conversion, p95 latency, indexed pages, time-to-first-report}
- baseline: {its value today, measured, with where it was read}
- target: {the value that would make this engagement worth having done}
- check on: {YYYY-MM-DD — 7 / 14 / 28 days after deploy, matched to the metric's own rhythm}
- if not confirmed: {rollback | retrospective | new hypothesis — decided NOW, not later}

## Explicitly out of scope
- list of things user mentioned but excluded from this engagement

## Open questions
- [ ] q-1: {the question, in the user's terms} — needed to: {what it unblocks} — status: open | answered | waived
      {if answered: the answer, verbatim. if waived: one line on what the engagement will assume instead.}

## Review mode
`lean` | `full` | `solo`  (default `lean`)

## Iteration budget
Guidance: 2 rework cycles, then user escalation. Counter informational. Hard cap 4. Escalate immediately on repeating critique.
```

If the user did not state acceptance bars, propose them based on the task and confirm. Director cannot accept against vague criteria.

### Open questions — write down what you could not close

You ask one clarifying question at intake. Everything still ambiguous after that has to land in
`## Open questions`, not in your head. Ambiguity that lives nowhere does not disappear; it turns
into a specialist guessing, and the guess only becomes visible when the manager rejects the result.

Rules:

- **An open question blocks the handoff.** It leaves that state one of two ways: the user answers
  it (`status: answered`, answer recorded verbatim), or the user explicitly waives it
  (`status: waived`, with one line on what the engagement will assume instead).
- **A waived question travels.** It stays in `criteria.md` and reaches the manager as an
  acknowledged warning, so a verdict is made knowing what was decided without an answer. Waiving
  is a decision someone made and left a trace of. Silence is not a decision.
- **Do not interrogate.** This is not a second questionnaire on top of the gut-check. Write down
  what you genuinely could not resolve, ask the highest-impact one, and offer to waive the rest.
- Empty is a valid and common state. An empty section means nothing was left hanging, which is
  different from having no section at all.

Ask them one at a time, never as a list:

> По q-1 я не уверен: {вопрос}. Могу пойти по варианту {X}, тогда запишу это допущением. Или скажи как надо.

`handoff-precheck.py`'s `open-questions` check warns when a question reaches handoff with no
status or still `open`. It warns rather than fails because the blocking half belongs here, at
intake, where the question is still cheap to answer.

### Risk class (`risk:` frontmatter) — separate axis from `size:`

`size:` answers "how much work is this" and drives tier, waves and specialist count. It does NOT
answer "what happens if this goes wrong", and those two come apart constantly: a one-line change
to a payment path is `size: S` and the most dangerous thing in the queue.

Set `risk:` from **reversibility × blast radius**, not from effort:

| risk | Signals |
|---|---|
| `high` | touches auth/authorization, payments or billing, personal data, secrets/keys, a DB migration, deletion of anything, a public-facing publish, or a production config |
| `medium` | changes a contract other code depends on (API shape, DB schema read by another service, shared component API), or is hard to roll back cleanly |
| `low` | additive, self-contained, revertible by one `git revert` with no data consequence |

Rules that hang off it:

- `risk: high` **forces the human gate regardless of tier**, including `size: S` which otherwise
  has no manager phase. A small irreversible change must not slip through the cheap path.
- `risk: high` also forces an explicit rollback line in "Done when" ("revert = `git revert <sha>`
  plus `alembic downgrade -1`, verified on staging"). Not a promise to be able to roll back — the
  actual command.
- `risk: low` is the default. Do not inflate it; the point of the axis is that `high` stays rare
  enough to mean something.

Borderline → the higher class, and say why in one line under Scope.

### Outcome hypothesis — why it is mandatory

Every engagement to date could answer "was it delivered" and none could answer "did it help":
acceptance criteria record the deliverable, nothing records the effect. That is why
`outcome_validation_rate` in `scripts/metrics.py` reads `no data` rather than a number.

Fill all five lines at intake, while the reason for doing the work is still fresh. Two rules:

- **Falsifiability test**: ask "what would we do if the target is missed?" If the answer is "keep
  it anyway, it is obviously good", the hypothesis is decoration — either find the real metric or
  write `metric: none (infrastructure work, no user-visible effect claimed)` honestly.
- **The check date belongs to the metric, not to impatience.** 7 days for a click-through, 28 for
  a retention or a support-load number. A quarterly metric checked at 7 days always reads "no
  change" and teaches the team the hypothesis was noise.

On the check date, record the result with
`python ~/.claude/scripts/ledger-emit.py <engagement> --agent human --type outcome_check
--payload-json '{"metric":"...","baseline":X,"target":Y,"observed":Z,"result":"confirmed|not_confirmed|unknown"}'`.

`scripts/outcome-due.py --hook` surfaces a hypothesis whose check date has passed and that has
no `outcome_check` event yet, so the closing half does not depend on anyone remembering.

### The other half: a defect in already-accepted work

`post_accept_defect_rate` reads `no data` across 7 accepted engagements. That is an empty feed,
not a clean record: nothing in the corpus ever told anyone to emit the event, so the one number
that would say whether acceptance means anything has never had a single input.

The moment to emit it is this one. When the incoming task is a fix to something a previous
engagement shipped and accepted, that previous engagement had a defect its acceptance missed.
Before writing the new `criteria.md`, record it against the OLD engagement:

```bash
python ~/.claude/scripts/ledger-emit.py <path-to-the-old-engagement> --agent agency-intake \
  --type post_accept_defect \
  --payload-json '{"found_in":"<new-engagement-name>","what":"<one line: what shipped broken>"}'
```

Emit it for a defect in the delivered work, not for a new requirement or a scope extension. If
the old engagement directory is already archived, point at the archived path; the ledger stays
with it. Skip silently when the old engagement predates the ledger and has no `events.jsonl`.

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

**Operating limitation (honest — do not paper over it):** the Workflow tool is **harness-only** — it runs from the interactive main loop, NOT headless (`claude -p`) or cron. Agency work is interactive today, so this is the live path with no current gap. But there is **no warm automated non-Workflow fallback**: if the Workflow tool is unavailable (headless/cron context, or a tool outage), **fail closed** — tell the user the cascade needs an interactive session; do NOT improvise a degraded hand-dispatch (the leads are plan-only by design; an ad-hoc second orchestration would carry weaker guarantees than the gated path). A real headless fallback would be NEW work — no skeleton exists today (the prior headless-engine skeleton was deleted; nothing wired) — future work, not a wired path.

1. **Resolve args** (the script cannot call Date.now, so you stamp the time):
   - `repoDir` = the project root holding `engagement/`. dev (code mode): the git root — `git -C <cwd> rev-parse --show-toplevel`. design/marketing (artefact mode): the project dir / CWD (a git repo is not required).
   - `scriptsDir` = absolute `~/.claude/scripts`.
   - `ts` = `(Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")` (bash: `date -u +%Y%m%dT%H%M%SZ`).
2. **Invoke the Workflow** with the classified domain:
   ```
   Workflow{ name: 'engagement-workflow', args: { repoDir, scriptsDir, ts, domain: '<dev|design|marketing>' } }
   ```
   The `lead:plan` step runs as `{domain}-lead` and sets `deliverable_mode` (dev → code: worktree + octopus + repo tests; design/marketing → artefact: files written to engagement/ paths + manifest-verify). It runs discovery → decompose → deliver → validate → handoff → gate, then **STOPS at the handoff seam**, returning `{ readyForAcceptance, gate, engagementDir, waves, adversarial_verify, validation_files, ... }`. It never touches the human-gate.
2a. **Emit ledger events (observability — best-effort, AFTER the seam returns).** The Workflow engine writes NO `events.jsonl` entries for the pre-gate cascade, so the S6 consolidation session would otherwise read a near-empty ledger for engagement #1. Emit one `phase_completed` per phase the return covers, deriving the payload from the RETURNED object ONLY (never fabricate). Best-effort by design — `ledger-emit.py` exits 0 on any failure, so a failed emit NEVER blocks the cascade:
   **Do not hand-assemble the payloads.** Write the Workflow's return object to a file verbatim and let the script derive them. Hand-typed JSON across a stream of engagements is how a field nobody returned ends up in the ledger, and a fabricated ledger is worse than an empty one because `metrics.py` and `skillopt-ready.py` read it as fact:
   ```bash
   # <result.json> = the Workflow return object, written out verbatim, nothing edited
   python ~/.claude/scripts/ledger-emit-phases.py <engagement> --result <result.json>
   ```
   It maps `r.waves` → deliver, `r.adversarial_verify` + `r.validation_files` → validate, `r.gate.failures` + `r.readyForAcceptance` → gate, and collapses a PRE-gate hard stop (an `error` with no `waves`) into the single deliver event that contract calls for. A key absent from the return is absent from the payload; nothing is defaulted. `--tier` is read from `r.tier` when present. Add `--dry-run` to see the mapping without writing.

   Best-effort like `ledger-emit.py`: every failure warns and exits 0, so observability can never block the cascade. `ledger-emit.py` stays the right tool for one-off single events; this one exists for the three-event post-seam batch.
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
- **Do not use the route class to skip the user.** `direct` skips the cascade, never the moment where the user sees the result and can say it is wrong. Artefact volume scales; approval does not.
- **Do not downgrade a class mid-work.** The ratchet is one-way. If it looked `full` and now feels small, finish it as `full`; the cost of the extra ceremony is bounded, the cost of a wrong downgrade is not.
- **Do not let a risk signal be argued down by effort.** "Одна строка" and "тут нечего ломать" are the two sentences that precede the veto being skipped. The list in step 1b is closed: any hit means `full`.
- **Do not upgrade silently.** An upgrade without the `route: upgraded ...` line under Scope loses the only signal that says the classifier needs work.
