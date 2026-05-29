---
name: semantic-drift-methodology
domain: marketing
description: |
  [METHODOLOGY] Semantic drift analysis process (topical deviation,
  underlinked content, misaligned queries, junk drift) using Yandex data,
  producing interactive HTML report with radial visualization. Preloaded by
  marketing-web-analyst agent.
---

# semantic-drift

Procedural skill — semantic drift analysis using Yandex Webmaster + Metrika data.

Analyze semantic drift of a website using Yandex Webmaster + Metrika data.
Identifies pages drifting from the site's topical center and generates an interactive HTML report.

## Prerequisites

- **yandex-webmaster** skill configured (required — search queries per page)
- **yandex-metrika** skill configured (recommended — traffic + behavior metrics)
- Python 3.10+ with numpy, scikit-learn
- Optional: sentence-transformers for embedding-based mode (`pip install sentence-transformers`)

## Concepts

### Semantic Centroid
The weighted average vector representing the site's "topical center".
Weighted by internal links + clicks to prioritize authoritative pages.

### Structural Drift Index (SDI)
`SDI = Internal Authority × Semantic Distance`
High SDI = page has strong internal linking but is semantically far from the site's core topic.
These are the most impactful pages to fix — high authority but misaligned.

### NavBoost Categories
| Category | Internal Authority | Semantic Distance | Action |
|----------|-------------------|-------------------|--------|
| **Healthy Core** | Any | Low | Keep as is |
| **Misaligned Core** | High | High | Fix content alignment or restructure links |
| **Underlinked Core** | Low | Low | Add more internal links — hidden gems |
| **Junk Drift** | Low | High | Consider removing, noindexing, or redirecting |

### KPIs
- **Topical Cohesion** (0-1): Average similarity to centroid. Higher = more focused site.
- **Focus-Drift Ratio**: Share of pages in the "focused" half. Higher = better.
- **Average NDI**: Navigation Drift Index — cross-metric signal strength.

## Modes

### Mode 1: Query-based (default, no external APIs)
Uses TF-IDF vectors from Yandex Webmaster search queries associated with each page.
Best for: SEO-focused analysis, understanding how Yandex "sees" your pages.

### Mode 2: Embedding-based (local, no API keys)
Uses sentence-transformers (all-MiniLM-L6-v2) to generate embeddings locally.
Best for: deep semantic analysis, content strategy. Runs offline, free.

## Workflow

### Phase 1: Data Collection

1. **ASK user:**
   ```
   Для какого сайта делаем анализ семантического дрейфа?
   URL сайта?
   ```

2. **Collect Webmaster data:**
   ```bash
   # Resolve skills root (default ~/.claude/skills, override via SKILLS_ROOT env)
   SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/skills}"

   # Get all search queries with page URLs
   bash "$SKILLS_ROOT"/yandex-webmaster/scripts/search_queries.sh \
     --host $SITE --limit 500 --order TOTAL_CLICKS \
     --csv /tmp/drift_queries.csv
   ```

3. **Collect Metrika data:**
   ```bash
   # Get page metrics
   bash "$SKILLS_ROOT"/yandex-metrika/scripts/pages.sh --limit 200 \
     > /tmp/drift_pages.json
   ```

### Phase 2: Analysis

```bash
# Install deps (first time only)
pip install numpy scikit-learn --quiet

# Run analysis (query-based mode)
python "$SKILLS_ROOT"/semantic-drift/scripts/analyze.py \
  --queries /tmp/drift_queries.csv \
  --pages /tmp/drift_pages.json \
  --output /tmp/drift_report.html

# Or with sentence-transformers embeddings (local, free)
pip install sentence-transformers --quiet
python "$SKILLS_ROOT"/semantic-drift/scripts/analyze.py \
  --queries /tmp/drift_queries.csv \
  --pages /tmp/drift_pages.json \
  --output /tmp/drift_report.html \
  --mode embeddings
```

### Phase 3: Report

Open `/tmp/drift_report.html` in browser. The report includes:

1. **KPI Dashboard** — Topical Cohesion, Focus-Drift Ratio, Avg NDI
2. **Radial Map** — interactive scatter plot:
   - Position (radius) = semantic distance from center
   - Color = SDI score
   - Size = clicks
   - Opacity = internal authority
3. **Category Table** — pages grouped by NavBoost category with actionable recommendations
4. **Top Drifters** — pages with highest SDI (fix first)
5. **Hidden Gems** — underlinked core pages (quick wins for internal linking)

## Scripts

### analyze.py
Main analysis script. Reads collected data, computes vectors, centroid, SDI, categories.

```bash
python scripts/analyze.py \
  --queries QUERIES_CSV \     # Webmaster search queries export
  --pages PAGES_JSON \        # Metrika pages data (optional)
  --output REPORT_HTML \      # Output HTML report path
  --mode query|embeddings \   # Analysis mode (default: query)
  --model MODEL \             # sentence-transformers model (default: all-MiniLM-L6-v2)
  --alpha 0.6 \               # Weight: content similarity
  --beta 0.3 \                # Weight: internal links
  --gamma 0.1                 # Weight: clicks
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--queries` | yes | - | CSV with search queries from Webmaster |
| `--pages` | no | - | JSON with page metrics from Metrika |
| `--output` | no | drift_report.html | Output HTML report |
| `--mode` | no | query | `query` (TF-IDF) or `embeddings` (sentence-transformers) |
| `--model` | no | all-MiniLM-L6-v2 | Model name for embeddings mode |
| `--alpha` | no | 0.6 | Content weight for centroid |
| `--beta` | no | 0.3 | Inlinks weight for centroid |
| `--gamma` | no | 0.1 | Clicks weight for centroid |

## Interpreting Results

### Radial Map
- **Center** = site's topical core
- **Orbits** (concentric circles):
  - Core (0-0.25): Tightly aligned pages
  - Focus (0.25-0.5): Related but broader content
  - Expansion (0.5-0.75): Tangential topics
  - Peripheral (0.75-1.0): Potential drift candidates
- **Color** (green → yellow → red): SDI score. Red = high-authority drifters
- **Size**: Click volume. Big + red = urgent fix needed
- **Opacity**: Internal link authority. Dim = underlinked

### Action Matrix

| Signal | Meaning | Action |
|--------|---------|--------|
| Big red dot near edge | High-traffic page drifting | Align content to core topic |
| Small dim dot at center | Topical but invisible | Add internal links |
| Big bright dot at center | Strong core page | Flagship content, protect it |
| Small red dot at edge | Low-value drift | Consider noindex/redirect/remove |

## Example Session

```
User: Проанализируй семантический дрейф для example.com

Claude: [Собирает данные из Webmaster и Metrika]
        [Запускает analyze.py]

        === Semantic Drift Report: example.com ===

        KPIs:
        • Topical Cohesion: 0.72 (хорошо — сайт тематически сфокусирован)
        • Focus-Drift Ratio: 0.65 (65% страниц в фокусе)
        • Avg NDI: 0.15

        🔴 Misaligned Core (3 страницы):
        - /blog/travel-tips/ — SDI 0.89 — 340 кликов, 45 inlinks
          → Туристический контент на строительном сайте. Рекомендация: перенести или удалить.

        🟡 Hidden Gems (7 страниц):
        - /catalog/sandwich-panels/ — SDI 0.05 — 12 кликов, 2 inlinks
          → Целевая страница без внутренних ссылок. Рекомендация: добавить ссылки из категории.

        📊 HTML-отчёт сохранён: /tmp/drift_report.html
```

## Limitations

- Query-based mode depends on Webmaster data availability (needs 30+ days of data)
- Pages without search queries in Webmaster won't be analyzed
- Embeddings mode downloads model (~90MB) on first run, then works offline
- Best results with 50+ pages in the analysis
