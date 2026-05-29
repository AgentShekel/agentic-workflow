---
name: yandex-wordstat-guide
domain: marketing
description: |
  [TOOL] Yandex Wordstat API client (top queries up to 2000,
  associations, dynamics, regional stats, CSV export, missed-demand analysis
  from Yandex Direct XLSX). Preloaded by marketing-keyword-researcher and
  marketing-seo-specialist agents.
---

# yandex-wordstat

Informational skill — search demand analysis via Yandex Wordstat API.

## Config

Requires `YANDEX_WORDSTAT_TOKEN` in `config/.env`.
Token is synced automatically from unified `yandex-analytics/config/.env` via `sync-config.sh`.

OAuth token with Wordstat scope alone is not enough. Register the app via Yandex Direct support (API returns 403 without this step):
1. Copy **ClientId** from the OAuth app settings page
2. Contact **Yandex Direct support** — provide your username and ClientId
3. Wait for approval (usually 1-2 business days)

Without this step, the API returns 403 Forbidden even with a valid OAuth token.
This is the same registration process as for Yandex Direct API.

## Principles

1. High numbers don't mean quality traffic — verify intent for each query
2. Think like a customer — creative semantic expansion
3. Clarify region before analysis — ask user and wait for answer
4. Show Wordstat operators in reports for verification
5. Verify intent via WebSearch before marking query as "target". Reason: "каолиновая вата для дымохода" looks like a chimney buyer, but they're buying insulation material — not your product

## Intent Verification

Before marking a query as "target", run WebSearch to check what people actually buy from that search. Apply red flags from [intent-verification.md](references/intent-verification.md) — examples, red flags, verification process.

## Workflow

1. Ask user about target region (wait for answer before continuing — wrong region = wrong data):
   ```
   "Для какого региона анализировать спрос? Вся Россия / Москва / конкретный город?"
   ```

2. Ask what the user sells/advertises (needed to filter non-target queries)

3. Check connection: `bash scripts/quota.sh`
4. Run analysis using appropriate script
5. Verify intent via WebSearch for each promising query following [intent-verification.md](references/intent-verification.md)
6. Present results with target/non-target separation and reasoning

## Scripts

### quota.sh
Check API connection.
```bash
bash scripts/quota.sh
```

### top_requests.sh
Get top search phrases. Supports up to 2000 results and CSV export.
```bash
bash scripts/top_requests.sh \
  --phrase "юрист дтп" \
  --regions "213" \
  --devices "all"

# Extended: 500 results exported to CSV
bash scripts/top_requests.sh \
  --phrase "юрист дтп" \
  --limit 500 \
  --csv report.csv

# Max results with comma separator
bash scripts/top_requests.sh \
  --phrase "юрист дтп" \
  --limit 2000 \
  --csv full_report.csv \
  --sep ","
```

| Param | Required | Default | Values |
|-------|----------|---------|--------|
| `--phrase` | yes | - | text with operators |
| `--regions` | no | all | comma-separated IDs |
| `--devices` | no | all | all, desktop, phone, tablet |
| `--limit` | no | API default (50) | 1-2000 (maps to API numPhrases) |
| `--csv` | no | - | path to output CSV file |
| `--sep` | no | ; | CSV separator (; for RU Excel) |

#### Result types: Top Requests vs Associations

The output contains two sections (both in stdout and CSV):

- **top** (`topRequests`) — queries that **contain the words** from your phrase, sorted by frequency. These are direct variations of the search query. Example: phrase "юрист дтп" → "юрист по дтп", "консультация юриста по дтп".
- **assoc** (`associations`) — queries **similar by meaning** but not necessarily containing the same words, sorted by similarity. These are semantically related searches. Example: phrase "юрист дтп" → "юридическая ответственность", "адвокат аварии".

**For analysis:** `top` results are your primary keyword pool. `assoc` results are useful for semantic expansion but often contain noise — always verify intent before including them.

#### CSV export details

CSV format: UTF-8 with BOM, columns: `n;phrase;impressions;type`.
When `--csv` is set, stdout shows first 20 rows per section; full data goes to file.

#### Working with large CSV exports

When `--limit` is set to a high value (e.g. 500-2000), use CSV export and read the file in chunks:
```bash
# Export 2000 results
bash scripts/top_requests.sh --phrase "query" --limit 2000 --csv data.csv

# Read first 50 rows (header + data)
head -n 51 data.csv

# Read rows 51-100
tail -n +52 data.csv | head -50

# Count total rows
wc -l < data.csv

# Filter only associations
grep ";assoc$" data.csv
```

This approach lets the agent process large datasets without flooding stdout.

### dynamics.sh
Get search volume trends over time.
```bash
bash scripts/dynamics.sh \
  --phrase "юрист дтп" \
  --period "monthly" \
  --from-date "2025-01-01"
```

| Param | Required | Default | Values |
|-------|----------|---------|--------|
| `--phrase` | yes | - | text |
| `--period` | no | monthly | daily, weekly, monthly |
| `--from-date` | yes | - | YYYY-MM-DD |
| `--to-date` | no | today | YYYY-MM-DD |
| `--regions` | no | all | region IDs |
| `--devices` | no | all | all, desktop, phone, tablet |

### regions_stats.sh
Get regional distribution.
```bash
bash scripts/regions_stats.sh \
  --phrase "юрист дтп" \
  --region-type "cities"
```

| Param | Required | Default | Values |
|-------|----------|---------|--------|
| `--phrase` | yes | - | text |
| `--region-type` | no | all | cities, regions, all |
| `--devices` | no | all | all, desktop, phone, tablet |

### regions_tree.sh
Show common region IDs.
```bash
bash scripts/regions_tree.sh
```

### search_region.sh
Find region ID by name.
```bash
bash scripts/search_region.sh --name "Москва"
```

## Wordstat Operators

### Quotes `"query"`
Shows demand ONLY for this exact phrase (no additional words).

```
"юрист дтп" → "юрист дтп", "юристы дтп"
             but NOT "юрист по дтп"
```

### Exclamation `!word`
Fixes exact word form.

```
!юрист → "юрист по дтп", "юрист москва"
         but NOT "юристы", "юриста"
```

### Combination `"!word !word"`
Exact phrase + exact forms.

```
"!юрист !по !дтп" → only "юрист по дтп"
```

### Minus `-word`
Exclude queries with this word.

```
юрист дтп -бесплатно -консультация
```

### Grouping `(a|b|c)`
Multiple variants in one query.

```
(юрист|адвокат) дтп → combined demand
```

### Stop words
Fix prepositions with `!` (Wordstat ignores them otherwise):

```
юрист !по дтп    ← correct
юрист по дтп     ← "по" ignored!
```

## Analysis Strategy

1. **Broad query**: `юрист дтп` — see total volume
2. **Narrow with quotes**: `"юрист дтп"` — exact phrase only
3. **Fix forms**: `"!юрист !по !дтп"` — exact match
4. **Clean with minus**: `юрист дтп -бесплатно -онлайн`
5. **Expand**: synonyms, related terms, client problems

## Popular Region IDs

| Region | ID |
|--------|-----|
| Россия | 225 |
| Москва | 213 |
| Москва и область | 1 |
| Санкт-Петербург | 2 |
| Екатеринбург | 54 |
| Новосибирск | 65 |
| Казань | 43 |

Run `bash scripts/regions_tree.sh` for full list.

## Limits

- 10 requests/second
- 1000 requests/day

## Example Session

```
User: Найди запросы для рекламы дымоходов

Claude: Для какого региона анализировать спрос?
        И уточните — вы продаёте готовые дымоходы или
        материалы для их изготовления/утепления?

User: Москва, продаём готовые сэндвич-дымоходы

Claude: [Запускает анализ для региона 213]

        Нашёл запросы. Проверяю интент через веб-поиск...

        ✅ ЦЕЛЕВЫЕ (покупают дымоходы):
        - "дымоход сэндвич купить" — 450 показов
        - "дымоход для бани цена" — 380 показов

        ❌ НЕ ЦЕЛЕВЫЕ (покупают другое):
        - "каолиновая вата для дымохода" — ищут утеплитель, не дымоход
        - "монтаж дымохода своими руками" — DIY, не покупатели
        - "чистка дымохода" — уже владеют, сервисный запрос
```

### Key Points

1. Ask region and wait for answer before running any analysis
2. Clarify what the client sells (needed to filter non-target queries)
3. Verify intent via WebSearch for each promising query. Reason: high-volume queries often have misleading intent
4. Split report into target/non-target with reasoning for each

## Расширенные сценарии

### Поиск упущенного спроса
Анализ рекламной кампании Яндекс Директ для нахождения фраз, не покрытых текущей семантикой.
Требования: XLSX-выгрузка из Яндекс Директ (лист «Тексты»).
Подробнее: [MISSED_DEMAND.md](references/MISSED_DEMAND.md)
