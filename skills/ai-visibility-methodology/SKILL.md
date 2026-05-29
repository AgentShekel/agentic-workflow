---
name: ai-visibility-methodology
domain: marketing
description: |
  [METHODOLOGY] AI platform visibility audit process (ChatGPT,
  Perplexity, Gemini, Claude, DeepSeek, Copilot, Yandex Neyro) with persistent
  projects, brand/competitor/segment management, intent-based prompt generation,
  source analysis, history tracking, trend comparison. Preloaded by
  marketing-ai-visibility-specialist agent.
---

# AI Search Visibility Audit

Procedural skill — 8 phases executed sequentially. Supports persistent projects, intent-based prompt generation, source analysis, history tracking, and trend comparison.

## Config

Set `OPENROUTER_API_KEY` in `config/.env` for single-key access to all platforms.
Fallback: individual platform keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).
Last resort: Playwright browser automation (no keys needed).

Setup details and key registration links in [config/README.md](config/README.md).

OpenRouter models used: `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`,
`google/gemini-2.0-flash-001`, `deepseek/deepseek-chat`, `perplexity/sonar`.

## Data Structure

```
data/
├── projects/{slug}/project.json   — persistent brand/competitor/segment data
├── history/{slug}/{date}/         — historical check results (auto-saved)
└── intents.json                   — predefined prompt templates by niche
```

## Workflow

### Phase 1: Project Setup

Create or load a persistent project. Projects store brand, URL, competitors, services, segments.

```bash
# Functions available in scripts/common.sh after sourcing:
init_project "my-brand"
save_project_field "my-brand" "brand-methodology" "Ботек"
save_project_field "my-brand" "url" "botek.ru"
save_project_field "my-brand" "location" "Самара"
save_project_field "my-brand" "niche" "фитнес-клубы"
save_project_array "my-brand" "services" '["тренажерный зал","бассейн","групповые занятия"]'
save_project_array "my-brand" "competitors" '["Alex Fitness","Физкульт","World Class"]'
save_project_array "my-brand" "segments" '["фитнес","бассейн","spa"]'

# List existing projects:
list_projects
```

For one-off audits, skip this phase and use `--brand`/`--url` flags directly.

**Checkpoint:** Project created with brand, URL, location, niche, services.

### Phase 2: Site Analysis

Analyze the target site to understand niche, services, location, brand name.

1. `WebFetch` the target site
2. Extract: brand name, location, services/products, target audience, competitors
3. If project exists, update it with discovered data

**Checkpoint:** You have brand name, location, niche, and 3+ services/features listed.

### Phase 3: Prompt Generation

Generate prompts using intent templates + custom queries. Save to a prompts file (one per line).

#### Using intent templates (recommended):

Load from `data/intents.json` — predefined templates by niche with `{brand}`, `{location}`, `{niche}`, `{service}`, `{feature}` placeholders.

Available niches: `fitness`, `restaurant`, `clinic`, `education`, `ecommerce`, `saas`, `realestate`, `auto`, `beauty`, `legal`. Universal templates apply to all niches.

1. Select matching niche from intents.json (or use `universal`)
2. Fill placeholders with project data
3. Add custom prompts for unique features/services
4. Save to prompts file

#### Prompt categories:

**A) Brand queries** (does the AI know about the brand?):
- "What is {Brand} in {Location}?"
- "Tell me about {Brand} {niche}"
- "{brand-domain} — what is it?"

**B) Category queries** (is the brand mentioned among competitors?):
- "Best {niche} in {Location}"
- "{niche} with {feature} in {Location}"
- "Affordable {niche} in {Location}"

**C) Decision queries** (does the AI recommend the brand?):
- "Which {niche} to choose in {Location} for a beginner?"
- "Where to go for {service} in {Location}?"
- "Compare {niche} in {Location} by value for money"

**Rules:**
- Minimum 12 prompts (4 per category)
- Use both Russian and English where applicable
- Include long-tail queries and comparison queries
- If project has segments, generate prompts per segment

**Checkpoint:** Prompts file saved with 12+ prompts across all 3 categories.

### Phase 4: Run Checks

Two modes available:

#### Mode A: API-based (fast, reliable, requires API key)

```bash
# With project (auto-fills brand/url, saves to history)
bash ~/.claude/skills/ai-visibility-methodology/scripts/check.sh --all --project my-brand --prompts prompts.txt --output results.json

# With segment tag
bash ~/.claude/skills/ai-visibility-methodology/scripts/check.sh --all --project my-brand --prompts prompts-spa.txt --segment "spa" --output results.json

# Without project (one-off)
bash ~/.claude/skills/ai-visibility-methodology/scripts/check.sh --platform chatgpt --prompts prompts.txt --brand "Brand" --url "domain.com"
bash ~/.claude/skills/ai-visibility-methodology/scripts/check.sh --all --prompts prompts.txt --brand "Brand" --output results.json
```

Supported platforms: `chatgpt`, `claude`, `gemini`, `deepseek`, `perplexity`

Each platform check outputs JSON with metrics including `mention_rate`, `citation_rate`, `top1_rate`.

When `--project` is used, results are automatically saved to `data/history/{slug}/{date}/`.

#### Mode B: Playwright-based (no API keys, uses browser)

Use Claude Code's Playwright tools to navigate AI platforms:

**Perplexity (no login required):**
1. `browser_navigate` → `https://www.perplexity.ai/`
2. `browser_type` → enter prompt into search box
3. `browser_snapshot` → capture response

**Yandex Neyro (no login required):**
1. `browser_navigate` → `https://ya.ru/`
2. Click "Нейро" tab, enter prompt, capture response

**ChatGPT, Gemini, Copilot (login may be required):**
Navigate, submit prompt, capture response.

**Checkpoint:** JSON results collected for 2+ platforms.

### Phase 5: Source Analysis

Extract and analyze domains/URLs that AI platforms cite in their responses.

```bash
bash ~/.claude/skills/ai-visibility-methodology/scripts/sources.sh --results-dir ./results/ --brand "Brand" --output sources.json
```

Output: JSON with per-domain citation counts, platform breakdown, and sample prompts that triggered citations.

**Checkpoint:** Source analysis complete. Top cited domains identified.

### Phase 6: Scoring

Calculate metrics per platform and overall:

| Metric | Formula |
|--------|---------|
| **Mention Rate** | (prompts where brand mentioned / total prompts) x 100% |
| **Citation Rate** | (prompts with link to site / total prompts) x 100% |
| **Top-1 Rate** | (prompts where brand mentioned first / total prompts) x 100% |
| **Sentiment Score** | (positive - negative) / total mentioned, scale -1 to +1 |
| **Competitor Gap** | brands mentioned more often than you (ranked list) |

**Scoring thresholds:**

| Score | Mention Rate | Citation Rate | Verdict |
|-------|-------------|---------------|---------|
| Excellent | >70% | >50% | Strong AI presence |
| Good | 40-70% | 20-50% | Visible but room to grow |
| Weak | 10-40% | 5-20% | Minimal presence |
| Invisible | <10% | <5% | AI platforms don't know you |

**Checkpoint:** Metrics calculated per platform and overall. Score assigned.

### Phase 7: Report Generation

```bash
# With project (includes trend comparison if history exists)
bash ~/.claude/skills/ai-visibility-methodology/scripts/report.sh \
  --results-dir ./results/ \
  --project my-brand \
  --output report.md

# Without project
bash ~/.claude/skills/ai-visibility-methodology/scripts/report.sh \
  --results-dir ./results/ \
  --brand "Brand" \
  --url "https://example.com" \
  --output report.md
```

Report includes:
1. **Executive Summary** — overall AI visibility score
2. **Platform Breakdown** — metrics per platform (with Top-1 Rate and segment columns)
3. **Competitor Map** — who AI recommends instead of you (with cross-platform frequency)
4. **Source Analysis** — domains AI cites in responses (your domain marked with ★)
5. **Trends** — comparison with previous audit (if project history exists)
6. **GEO Recommendations** — actionable steps to improve visibility
7. **Monitoring Plan** — suggested re-check schedule

### Phase 8: Trend Analysis & GEO Optimization

#### Trends (requires project with 2+ audits)

```bash
bash ~/.claude/skills/ai-visibility-methodology/scripts/trends.sh --project my-brand [--output trends.json]
```

Shows delta for Mention Rate and Citation Rate per platform vs previous audit.

#### GEO Optimization

Apply recommendations from [geo-checklist.md](references/geo-checklist.md):
- Technical accessibility (AI crawlers, SSR, sitemap)
- Content structure and authority
- Schema.org structured data
- Brand presence across platforms

**Checkpoint:** Report delivered. Trends analyzed. GEO recommendations prioritized.

## Project Management

### Creating a project

During Phase 1, create a persistent project to track a brand across audits:

```bash
# In common.sh (sourced by all scripts):
init_project "my-brand"
save_project_field "my-brand" "brand-methodology" "My Brand"
save_project_field "my-brand" "url" "mybrand.com"
save_project_array "my-brand" "competitors" '["Comp A","Comp B"]'
save_project_array "my-brand" "segments" '["product-a","product-b"]'
```

### Using intents

`data/intents.json` contains prompt templates organized by niche. Each template has:
- `category`: brand / category / decision
- `template`: prompt text with placeholders
- `lang`: ru / en

Available niches: fitness, restaurant, clinic, education, ecommerce, saas, realestate, auto, beauty, legal.

### History

When `--project` is used with check.sh, results are auto-saved to `data/history/{slug}/{date}/`. This enables:
- Trend comparison between audits
- Historical metric tracking
- Month-over-month progress reports

## Integration with Yandex Analytics

| Combined audit | ai-visibility-methodology + yandex skill |
|----------------|------------------------------|
| AI vs organic comparison | ai-visibility-methodology + yandex-search-guide (SERP positions) |
| Content gap analysis | ai-visibility-methodology (what AI recommends) + yandex-wordstat-guide (search demand) |
| Traffic attribution | ai-visibility-methodology + yandex-metrika-guide (referral from AI platforms) |
| Full SEO + AI audit | seo-auditing orchestrator + ai-visibility-methodology |

**AI referral tracking (Metrika/GA):**
- `chat.openai.com`, `chatgpt.com`
- `perplexity.ai`
- `gemini.google.com`
- `copilot.microsoft.com`
- `ya.ru` (Yandex Neyro)

## Common Use Cases

### Quick brand check
→ Phase 2 + Phase 3 (brand queries only) + Phase 4 + Phase 6

### Full visibility audit
→ All phases (1-8)

### Competitor intelligence
→ Phase 3 (category queries) + Phase 4 + focus on Competitor Gap metric

### Monthly monitoring
→ Phase 4-7 monthly with `--project` flag, compare trends

### Segmented audit
→ Run Phase 4 per segment with `--segment` flag, compare in report

### Source analysis
→ Phase 4 + Phase 5 → understand which domains AI trusts in your niche

## Bundled Resources

- `scripts/check.sh` — unified platform check (OpenRouter or direct API, `--platform` or `--all`, `--project`, `--segment`)
- `scripts/report.sh` — aggregate results into report (with sources, trends, segments)
- `scripts/sources.sh` — extract and analyze cited domains from results
- `scripts/trends.sh` — compare current vs previous audit metrics
- `scripts/quota.sh` — verify API connections
- `scripts/common.sh` — shared functions (mention detection, sentiment, JSON, projects, history, sources)
- `data/intents.json` — predefined prompt templates by niche (10 niches + universal)
- `data/projects/` — persistent project data (brand, competitors, segments)
- `data/history/` — historical check results (auto-saved per project)
- `references/geo-checklist.md` — GEO optimization checklist
- `config/.env` — API key configuration

## Limits

- AI responses are non-deterministic — run each prompt 2-3 times for reliability
- Playwright checks take ~30 sec per prompt per platform
- Monthly re-audits recommended; AI knowledge updates frequently
- Rate limits: OpenAI 3-60+ RPM, Perplexity 50 RPM, Gemini 60 RPM (varies by tier)

## Verification

After completing a full audit, confirm:
- [ ] Project created/updated with brand, URL, competitors
- [ ] 3+ platforms checked (at least one API-based, one Playwright-based)
- [ ] 12+ prompts used across brand/category/decision types
- [ ] Mention Rate, Citation Rate, and Top-1 Rate calculated per platform
- [ ] Competitor list extracted from responses
- [ ] Source analysis completed (cited domains identified)
- [ ] Report generated with all sections (sources, competitors, recommendations)
- [ ] Results saved to history (if using --project)
- [ ] GEO checklist reviewed if score is Weak or Invisible
