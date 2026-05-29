---
name: seo-auditing
domain: marketing
description: |
  [METHODOLOGY] Comprehensive SEO audit process orchestrating Yandex
  data sources (Webmaster, Metrika, Wordstat, Search) into a unified report
  with recommendations. Preloaded by marketing-seo-specialist agent.
---

# seo-audit

Procedural skill — comprehensive SEO audit orchestrating all Yandex analytics skills into a unified report.

## Prerequisites

At least some of these skills must be configured:
- **yandex-webmaster** — indexing, crawl errors, search queries, SQI
- **yandex-metrika** — traffic, behavior, conversions
- **yandex-wordstat** — search demand, semantics
- **yandex-search** — SERP positions, competitors

## Path resolution

Orchestrator calls scripts from dependency skills. Paths resolve via `$SKILLS_ROOT` (default: `~/.claude/skills`). Override with:
```bash
export SKILLS_ROOT="/custom/path/to/skills"
```
Makes the skill portable across plugin layouts, custom install locations, and future restructuring.

## Workflow

### Phase 1: Discovery

1. **ASK user:**
   ```
   Для какого сайта делаем SEO-аудит?
   URL сайта и основная тематика/что продаёт?
   ```

2. **ASK about scope:**
   ```
   Какие направления аудита нужны?
   - Полный аудит (все направления)
   - Только техническое SEO (индексация, ошибки)
   - Только поисковая видимость (запросы, позиции)
   - Только трафик и поведение
   ```

3. **ASK about competitors (if relevant):**
   ```
   Есть конкуренты для сравнения? (URL или названия)
   ```

### Phase 2: Data Collection

Run skills in parallel where possible. Check which skills are configured before attempting.

```bash
# Set once at the start of Phase 2 — all subsequent calls use $SKILLS_ROOT
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/skills}"
```

#### 2.1 Technical SEO (yandex-webmaster)
```bash
# Connection check
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/quota.sh

# Site summary
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/indexing.sh --host $SITE --type summary

# Crawl diagnostics
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/diagnostics.sh --host $SITE

# Sitemaps status
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/sitemaps.sh --host $SITE

# Broken internal links
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/links.sh --host $SITE --type internal-broken

# External links
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/links.sh --host $SITE --type external

# SQI history
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/sqi.sh --host $SITE --from $THREE_MONTHS_AGO

# Indexing history
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/indexing.sh --host $SITE --type history --from $THREE_MONTHS_AGO
```

#### 2.2 Search Visibility (yandex-webmaster + yandex-search)
```bash
# Top search queries from Webmaster
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/search_queries.sh --host $SITE --limit 50 --order TOTAL_CLICKS

# Check positions for top queries
bash "$SKILLS_ROOT"/yandex-search/scripts/positions.sh --domain $DOMAIN --queries top_queries.txt --region $REGION --csv positions.csv

# Competitor analysis for key queries
bash "$SKILLS_ROOT"/yandex-search/scripts/competitors.sh --query "$KEY_QUERY" --region $REGION
```

#### 2.3 Traffic & Behavior (yandex-metrika)
```bash
# Traffic overview (last 30 days vs previous 30 days)
bash "$SKILLS_ROOT"/yandex-metrika/scripts/overview.sh --from $CURRENT_START --to $CURRENT_END
bash "$SKILLS_ROOT"/yandex-metrika/scripts/overview.sh --from $PREV_START --to $PREV_END

# Traffic sources
bash "$SKILLS_ROOT"/yandex-metrika/scripts/sources.sh --from $CURRENT_START --to $CURRENT_END

# Top pages
bash "$SKILLS_ROOT"/yandex-metrika/scripts/pages.sh --limit 30

# Devices
bash "$SKILLS_ROOT"/yandex-metrika/scripts/devices.sh --type device

# Goals/conversions
bash "$SKILLS_ROOT"/yandex-metrika/scripts/goals.sh
```

#### 2.4 Search Demand (yandex-wordstat)
```bash
# Core queries demand
bash "$SKILLS_ROOT"/yandex-wordstat/scripts/top_requests.sh --phrase "$CORE_QUERY" --regions $REGION --limit 100

# Demand dynamics (seasonality)
bash "$SKILLS_ROOT"/yandex-wordstat/scripts/dynamics.sh --phrase "$CORE_QUERY" --period monthly --from-date $YEAR_AGO
```

### Phase 3: Analysis & Report

Structure the report as follows:

```markdown
# SEO-аудит: [site.ru]
Дата: [date]
Период анализа: [period]

## Резюме
[3-5 ключевых выводов с приоритетами: критично / важно / рекомендация]

## 1. Техническое SEO
### Индексация
- Страниц в индексе: X
- Динамика: рост/падение за 3 мес
- SQI: текущий и тренд

### Ошибки краулинга
- [список проблем с приоритетами]

### Сайтмапы
- Статус сайтмапов

### Внутренние ссылки
- Битые ссылки: количество, примеры

### Внешние ссылки
- Количество, динамика

## 2. Поисковая видимость
### Топ запросов (по кликам)
| Запрос | Показы | Клики | Позиция |
|--------|--------|-------|---------|
| ...    | ...    | ...   | ...     |

### Позиции по ключевым запросам
| Запрос | Позиция | URL | Конкуренты в топ-3 |
|--------|---------|-----|---------------------|
| ...    | ...     | ... | ...                 |

## 3. Трафик и поведение
### Общие метрики
| Метрика | Текущий период | Предыдущий | Изменение |
|---------|---------------|------------|-----------|
| Визиты  | ...           | ...        | +/-X%     |

### Источники трафика
### Топ страниц
### Устройства
### Конверсии

## 4. Поисковый спрос
### Объём спроса по ядру
### Сезонность
### Упущенные запросы

## 5. Рекомендации
### Критично (исправить немедленно)
1. ...

### Важно (исправить в ближайший месяц)
1. ...

### Рекомендации (улучшения)
1. ...
```

## Error Handling

- If a skill is not configured (missing token), skip that section and note it in the report
- If API returns errors, log them and continue with available data
- Always produce a report even if some data sources are unavailable

## Tips

- Run data collection scripts in parallel using Agent tool where possible
- Compare metrics period-over-period for trend analysis
- Cross-reference data: Webmaster queries vs Metrika landing pages vs Wordstat demand
- Look for gaps: high-demand queries (Wordstat) where site has no positions (Search)
- Check if top Metrika pages are properly indexed (Webmaster)

## Example Session

```
User: Сделай SEO-аудит для example.com

Claude: Для какого региона и что продаёт сайт?

User: Москва, продаём строительные материалы

Claude: [Запускает сбор данных из всех доступных скиллов]
        [Параллельно: Webmaster + Metrika + Wordstat + Search]

        === SEO-аудит: example.com ===

        Резюме:
        🔴 КРИТИЧНО: 340 страниц выпало из индекса за последний месяц
        🟡 ВАЖНО: Bounce rate 78% на мобильных (desktop: 45%)
        🟢 РЕКОМЕНДАЦИЯ: Не покрыты запросы "купить кирпич оптом" (2400 показов/мес)

        [Полный отчёт по разделам...]
```
