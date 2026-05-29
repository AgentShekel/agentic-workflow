---
name: benchmark-research
domain: marketing
description: |
  [METHODOLOGY] Industry benchmark research — reverse-engineer how the
  fastest-growing companies in a given industry actually scaled (source
  harvest → company synthesis → cross-company meta-synthesis → private
  application layer). Evidence-disciplined, primary-source-first.
  Standalone capability — not wired into the agency cascade; has its
  own entry-point trigger.

  Use when: "мне надо провести исследование", "мне надо ресёрч",
  "ресёрч индустрии", "индустриальный ресёрч", "конкурентный анализ
  методология", "benchmark research", "industry benchmark",
  "reverse-engineer GTM", "competitive intelligence".
---

# benchmark-research

Reverse-engineer how selected companies in [INDUSTRY] actually grew, sold,
priced, implemented, expanded, and defended their position — then extract
reusable patterns. **NOT** generic company summaries.

Works best for questions like:
- How did the fastest-growing companies in this industry actually scale?
- What sales motion / pricing model / initial wedge worked?
- What implementation / deployment model made customers successful?
- What expansion mechanics created retention and NRR?
- What recurring laws or archetypes appear across the best companies?

## Entry-point flow (on trigger)

When the trigger phrase fires, run a short intake **before** any research:

1. **Industry / scope.** What industry? Why this one? What counts as
   "fast growth"? What benchmark questions matter? (Phase 0)
2. **Mode.** Full programme (15–25 companies, weeks of work) or **MVV**
   (8 companies, lighter — see below)?
3. **Target company for the private application layer.** Is there a
   "our company" perspective for private recommendations? If yes →
   public layer + private memo. If no → public benchmark only.
4. **Project location.** Where does `research-project/` live? It is
   **NOT** inside agency `engagement/` — it has its own artefact tree
   (see "Folder structure" below) and outlives any single session.

Capture these in `research-project/README.md` and proceed by phase.

## Core principle

Strict separation into four layers — do not mix them:

1. **Source harvest** — structured primary-source archive
2. **Company synthesis** — one reverse-engineering memo per company
3. **Meta-synthesis** — cross-company laws, archetypes, patterns
4. **Application** — private recommendations (what to copy / adapt /
   reject / sequence)

Public benchmark can discuss lessons and boundary conditions. The
private application layer says what THIS company should do. Keep them
separate if the benchmark will be shared.

## Folder structure

```
research-project/
├── README.md                      # scope, decisions, current phase
├── source-harvest-phase/
│   └── <company>/
│       ├── company.md
│       ├── TODO-sources.md
│       ├── people/<person>.md
│       └── sources/<source>.md
├── synthesis-phase/
│   ├── <company>/
│   │   ├── research-brief-<company>-playbook.md
│   │   ├── <company>-playbook-analysis.md
│   │   └── <company>-playbook-slides-outline.md
│   ├── meta-synthesis/
│   │   ├── meta-synthesis-industry-benchmark.md
│   │   ├── growth-laws.md
│   │   ├── sales-laws.md
│   │   ├── archetypes.md
│   │   ├── pattern-matrix.md
│   │   ├── company-comparison-table.md
│   │   └── cross-insights.md
│   └── application/
│       ├── application-memo.md
│       ├── priority-matrix.md
│       ├── do-copy-dont-copy.md
│       └── sequencing-roadmap.md
└── publishing-layer/              # optional
```

This is **not** an agency `engagement/` directory — it lives outside
the agency whitelist. A benchmark programme spans many sessions; each
session advances one or more phases.

## Evidence labels (use everywhere)

| Label | Meaning |
|---|---|
| `[E]` | Directly sourced evidence |
| `[I]` | Inference from sourced facts |
| `[UV]` | Unverified estimate |
| `[OQ]` | Open question |
| `[H]` | Hypothesis to test |

If a claim matters, label it. Do not let elegant writing blur evidence
quality. This is the same discipline `reality-checker` / `skeptic`
enforce on agency artefacts.

## Source priority

Prefer primary / operator sources. Order:

1. Founder / CEO / executive interviews
2. Podcasts, talks, conference appearances
3. Company-written material — product docs, launch posts, customer
   stories, trust docs, pricing pages
4. Operator posts from people who built the motion
5. Job descriptions, org charts
6. Customer case studies / quotes
7. Partner pages / ecosystem announcements
8. Investor memos / analyst reports (clearly labelled)
9. News articles only if they contain original facts, quotes, or data

Avoid overweighting: recycled funding news · SEO summaries · unsourced
listicles · vague market maps · press with no operator detail.

## Company selection

Score each candidate on:

- **Growth velocity** — scaled unusually fast?
- **Relevance** — in or near the target industry?
- **Evidence availability** — enough sources to reverse-engineer the
  motion?
- **Distinctiveness** — adds a unique mechanism, not just another copy?
- **Transferability** — others can learn from it, even if not copy
  directly?

Tiers:

- **Tier 1** — Core benchmark. Directly relevant, strong evidence,
  clear motion.
- **Tier 2** — Boundary case. Not perfectly comparable but teaches a
  mechanism.
- **Tier 3** — Context only. For contrast, not a core example.

Do not include a company just because it is famous. Include it because
it teaches a mechanism.

## Phase 1 — Source harvest

Goal: structured evidence archive, not a giant narrative report.

Per company, populate `source-harvest-phase/<company>/`:

- `company.md` answers: what the company does · initial wedge · why it
  matters for this benchmark · known milestones · major open questions.
- `TODO-sources.md` lists: missing high-value interviews · gated pages
  worth revisiting · missing transcripts · ambiguous claims needing
  verification · important-but-unsourced claims.
- `sources/<source>.md` per source: title · source type · date · URL ·
  who is speaking · why this source matters · key facts · direct quotes
  · what it reveals about growth/GTM/pricing/product/adoption · caveats.
- `people/<person>.md` per person: role · relevance to growth story ·
  notable claims/quotes · source references · career pattern if
  relevant to GTM credibility.

**Extract from each source:** growth milestones · wedge & initial use
case · buyer persona · sales motion · founder-led sales clues ·
pilot/POC structure · design partner details · pricing & packaging ·
contract size hints · implementation/deployment model · trust /
compliance / security / integration details · customer success motion ·
expansion / retention mechanics · org buildout & key hires · partner /
channel motion · moat & defensibility · non-transferable advantages.

**Done criteria:** `company.md` + `TODO-sources.md` exist · multiple
strong source notes exist · key people notes where relevant · major
GTM / product / pricing / trust questions have at least partial
evidence · remaining gaps explicitly listed.

The reusable harvest prompt: [`references/source-harvest-prompt.md`](references/source-harvest-prompt.md).

## Phase 2 — Company synthesis

Goal: strategy-grade reverse-engineering memo per company.

For each company, produce in `synthesis-phase/<company>/`:

- `research-brief-<company>-playbook.md` (use template:
  [`references/company-launch-template.md`](references/company-launch-template.md))
- `<company>-playbook-analysis.md`
- `<company>-playbook-slides-outline.md`

### Memo structure (11 sections)

1. **Executive summary** — what is the company · why in benchmark ·
   core growth interpretation · sourced vs inferred
2. **Core motion** — initial wedge · target buyer/user · why urgent ·
   category framing
3. **Growth system decomposition** — acquisition channels · conversion
   mechanisms · trust mechanisms · implementation/activation path ·
   expansion loop
4. **Unit economics & commercial logic** — pricing model · budget
   replaced/captured · ACV / contract size estimates · gross
   margin/COGS logic · payback · expansion logic
5. **Sales cycle reverse engineering** — who bought · who used · who
   blocked · who championed · pilot/POC structure · proof points ·
   procurement/security path · founder-led vs sales-led vs partner-led
6. **Implementation / deployment model** — onboarding sequence ·
   integration requirements · services / forward-deployed / solutions
   role · customer success model · time to value · scale-up path
7. **Why the company won** — timing · wedge strength · product
   advantage · distribution advantage · credibility/trust advantage ·
   ecosystem/partner advantage
8. **Benchmark relevance & transferability boundaries** — what this
   case demonstrates · what is broadly transferable · what should not
   be copied blindly · what depends on unique market structure
9. **Factor analysis** — McKinsey-style table: factor · evidence ·
   strength · transferability · caveats
10. **Risks & fragilities** — what could break the model · competitive
    threats · margin/pricing risks · channel risks · customer
    concentration · regulatory/trust risks
11. **Final benchmark assessment** — tier recommendation · why
    included/excluded · what future research should verify

Reusable synthesis prompt:
[`references/synthesis-prompt.md`](references/synthesis-prompt.md).

## Phase 3 — Cross-company meta-synthesis

After enough company memos exist (recommended: ≥6), create:

- `meta-synthesis-industry-benchmark.md`
- `growth-laws.md` (or `.yaml`)
- `sales-laws.md`
- `archetypes.md`
- `pattern-matrix.md`
- `company-comparison-table.md`
- `cross-insights.md`

Answer: what patterns repeated · what was rare vs common · what
commercial logic appeared repeatedly · what sales tactics repeated ·
what archetypes emerged · what mechanisms were true exceptions · what
changed by subcategory / buyer / market maturity.

### Growth laws

Structural patterns in how companies scaled. Per law: `id` · `name` ·
`short_description` · `body` · `prevalence` · `key_examples` ·
`anti_pattern` · `caveats`.

Categories to consider: wedge clarity · prestige-first adoption ·
domain-expert GTM · proof before scale · labor-budget or revenue-budget
pricing · expansion flywheel · high-touch implementation as moat ·
trust architecture · platform expansion after wedge · ICP discovery
filter · auditability as GTM mechanism.

### Sales laws

Patterns in commercial-motion execution. Same structure as growth laws.

Categories to consider: founders sell first · demo against the
customer's own work/data · willingness-to-pay as qualification · paid
pilot structure · objector-to-champion conversion · practitioner pull ·
reference hierarchy · multi-year contracts as switching cost · economic
buyer pre-close.

### Pattern matrix

Company × pattern table. Cells: `confirmed / partial / absent /
unknown` — **do not force binary labels where evidence is mixed**. Use
`partial` and `unknown` liberally.

Example fields: company · tier · wedge_clarity · prestige_first ·
domain_expert_gtm · proof_before_scale · labor_budget_pricing ·
expansion_flywheel · founder_sells_first · demo_against_own_work ·
paid_pilot · practitioner_pull · trust_architecture ·
implementation_moat · evidence_quality (high/medium/low) · notes.

### Archetypes

Clusters of companies with similar growth/commercial logic. Per
archetype: name · definition · member companies · common wedge · buyer
· pricing model · sales motion · implementation model · expansion
mechanism · risks · what this archetype teaches.

Do not create a new archetype for every one-off exception. If only one
company fits, mark it as a boundary case unless the pattern is
strategically important enough to preserve as a future hook.

### Cross-insights

Important patterns that may not be universal laws. Per insight: title ·
summary · evidence · companies involved · confidence level ·
implications · caveats.

Good cross-insights sound like:
- "Consumption-metered expansion may be a third NRR mechanism."
- "Prestige logos work differently in developer tools than in
  executive-procured software."
- "Compliance is not a back-office requirement; it is part of GTM."
- "Services-heavy deployment can be a moat when it creates workflow
  depth."

## Phase 4 — Application layer (private)

ONLY after company synthesis and meta-synthesis are complete.

Answers: what should WE copy? · what adapt? · what NOT copy? · what
sequence first? · what preconditions must be true before copying? ·
what would be dangerous cargo-culting?

Deliverables:

- `application-memo.md`
- `priority-matrix.md` (Pattern · Source companies · Why it worked
  there · Applicability · Preconditions · Risk if copied blindly ·
  Recommended action)
- `do-copy-dont-copy.md`
- `sequencing-roadmap.md`

**Keep application recommendations strictly separate from the public
benchmark** if the benchmark will be shared. Public pages must not leak
private company-specific advice.

## Quality gates

**Before calling a company memo complete:**

- Does it explain the growth machine, not just describe the company?
- Are evidence and inference clearly separated?
- Are pricing and economics addressed?
- Is sales cycle reverse-engineered?
- Is implementation / deployment model addressed?
- Is expansion logic explicit?
- Are non-transferable advantages identified?
- Are open questions listed?

**Before calling meta-synthesis complete:**

- Are laws based on multiple companies, not one anecdote?
- Are exceptions labelled as exceptions?
- Are boundary cases separated from core patterns?
- Are prevalence estimates honest?
- Do archetypes group mechanisms, not vibes?
- Does the pattern matrix reflect evidence quality?

**Before publishing:**

- Are public and private layers separated?
- Are source references preserved?
- Are unverified estimates labelled?
- Are generated pages checked for private leakage?
- Are stale claims removed after refactors?

## Anti-patterns

1. **Generic company summaries.** Bad: "Company X is a leading platform
   that helps teams…" Good: "Company X won by starting with workflow Y,
   proving metric Z in pilot, then expanding via mechanism A."
2. **Funding-news overweighting.** Funding is not a growth machine.
   Only use funding news if it includes original metrics, customer
   facts, or operator quotes.
3. **Unlabeled inference.** If inferred, say it is inference.
4. **Overfitting one company into a law.** One company creates an
   emerging insight, not a universal law.
5. **Confusing public pricing with actual economics.** Public tiers may
   be entry points; real revenue may come from usage, enterprise
   contracts, services, volume, or expansion.
6. **Mixing product adoption with revenue mechanism.** "Users like it"
   ≠ "this is how the business scales."
7. **Treating implementation as boring.** In many enterprise
   categories, implementation IS the moat.
8. **Cargo-culting prestige customers.** Prestige-first works when peer
   trust matters; not in all markets.
9. **Publishing private recommendations.** Public = benchmark lessons;
   private = company-specific advice.
10. **Not updating cross-synthesis after new company research.** Every
    strong new memo should trigger a review of laws, matrix,
    archetypes, cross-insights.

## Suggested sequence

| Phase | What |
|---|---|
| 0 | Define scope — target industry · why · what counts as fast growth · benchmark questions |
| 1 | Candidate map — list 30–50 companies · score · choose first 10–20 |
| 2 | Source harvest — one company at a time · primary/operator sources · structured archive · explicit gaps |
| 3 | Company synthesis — full reverse-engineering memo per company · slide outline · evidence-tagged |
| 4 | Meta-synthesis — growth/sales laws · archetypes · pattern matrix · comparison table · cross-insights |
| 5 | Application — what to copy/adapt/reject · sequence · preconditions · risk of blind copying |
| 6 | Publishing (optional) — public benchmark layer · private application layer · keep private out of public |

## Minimum Viable Version

Lightweight starter:

1. Pick **8 companies**.
2. For each, collect **5–10 strong sources**.
3. Write one memo per company using the standard structure.
4. Build one pattern matrix.
5. Extract 5 growth laws + 5 sales laws.
6. Write a 5-page application memo.

Enough to be useful. Full version expands to 15–25 companies and a
publishable site.

## Agent activation prompt

Use as the system / task instruction for an agent doing the research:

> You are building a benchmark research corpus for [INDUSTRY]. Your job
> is to reverse-engineer how selected companies actually scaled. Do not
> write generic company summaries. Always separate evidence from
> inference. Prefer primary/operator sources. Maintain the project
> folder structure. For each company, first build a source archive,
> then a synthesis memo. After multiple company memos exist, extract
> cross-company laws, archetypes, and comparison matrices. Keep private
> application recommendations separate from public benchmark research.
> When uncertain, write TODO / open question instead of inventing
> certainty.

Per-phase reusable prompts live in `references/`:

- [`references/source-harvest-prompt.md`](references/source-harvest-prompt.md)
- [`references/synthesis-prompt.md`](references/synthesis-prompt.md)
- [`references/company-launch-template.md`](references/company-launch-template.md)
