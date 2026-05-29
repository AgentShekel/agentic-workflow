---
name: yandex-search-guide
domain: marketing
description: |
  [TOOL] Yandex Cloud Search API v2 client (position tracking,
  competitor analysis, SERP monitoring). Preloaded by marketing-seo-specialist
  agent.
---

# yandex-search

Informational skill — search positions and Yandex SERP analysis via Yandex Cloud Search API v2.

## Config

Requires `YANDEX_SEARCH_API_KEY` and `YANDEX_CLOUD_FOLDER_ID` in `config/.env`.
Synced from unified config via `yandex-analytics/scripts/sync-config.sh`.

Setup:
1. Create service account in Yandex Cloud console
2. Assign roles: `search-api.executor`, `search-api.webSearch.user`
3. Create API key for the service account
4. Get folder ID from Cloud console (top-left dropdown)

## Workflow

1. **Check connection**: `bash scripts/quota.sh`
2. **Run search/check** using appropriate script
3. **Interpret results** — async API returns XML; scripts parse and present key data

## Scripts

### quota.sh
Check API connection with a test query.
```bash
bash scripts/quota.sh
```

### search.sh
Search Yandex and show results.
```bash
bash scripts/search.sh --query "купить дымоход" --region 213 --limit 10

# With time sorting
bash scripts/search.sh --query "купить дымоход" --region 213 --sort time

# Strict SafeSearch
bash scripts/search.sh --query "купить дымоход" --filter strict
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--query` | yes | - | Search query |
| `--region` | no | 225 (Russia) | Region ID |
| `--limit` | no | 10 | Results per page (max 100) |
| `--page` | no | 0 | Page number (0-indexed) |
| `--sort` | no | relevancy | `relevancy` or `time` |
| `--filter` | no | moderate | `none`, `moderate`, or `strict` |

### positions.sh
Check position of a specific domain for search queries. **The most important script.**
```bash
# Check single query
bash scripts/positions.sh --domain example.com --query "купить дымоход" --region 213

# Check multiple queries from file (one per line)
bash scripts/positions.sh --domain example.com --queries queries.txt --region 213 --csv results.csv

# Check up to N pages deep
bash scripts/positions.sh --domain example.com --query "купить дымоход" --region 213 --depth 10
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--domain` | yes | - | Domain to find (e.g., `example.com`) |
| `--query` | one of | - | Single search query |
| `--queries` | one of | - | File with queries (one per line) |
| `--region` | no | 225 | Region ID |
| `--depth` | no | 5 | Pages to check (5 = top 50) |
| `--csv` | no | - | Export results to CSV file |

Logic: searches page 0, checks if domain appears in results. If not found, checks page 1, and so on up to `--depth`.
Output: query, position (or "not found in top N"), URL that ranked.

### competitors.sh
Find competitors for a query — who ranks in top 10.
```bash
bash scripts/competitors.sh --query "купить дымоход" --region 213
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--query` | yes | - | Search query |
| `--region` | no | 225 | Region ID |
| `--limit` | no | 10 | Number of results |

Output: position, domain, URL, title for top results.

## API Reference

### Yandex Cloud Search API v2 (Async)

**Step 1 — Submit search:**
- Endpoint: `POST https://searchapi.api.cloud.yandex.net/v2/web/searchAsync`
- Auth: `Authorization: Api-Key <API_KEY>`
- Body: JSON with query, folderId, region, sortSpec, groupSpec, responseFormat
- Returns: operation ID

**Step 2 — Poll for result:**
- Endpoint: `GET https://operation.api.cloud.yandex.net/operations/{operationId}`
- Auth: same Api-Key header
- Returns: `done: true` with `rawData` (base64-encoded XML) when ready

### Request body structure
```json
{
  "query": {
    "searchType": "SEARCH_TYPE_RU",
    "queryText": "search text",
    "familyMode": "FAMILY_MODE_MODERATE",
    "page": "0",
    "fixTypoMode": "FIX_TYPO_MODE_ON"
  },
  "sortSpec": {
    "sortMode": "SORT_MODE_BY_RELEVANCE",
    "sortOrder": "SORT_ORDER_DESC"
  },
  "groupSpec": {
    "groupMode": "GROUP_MODE_DEEP",
    "groupsOnPage": "10",
    "docsInGroup": "1"
  },
  "maxPassages": "2",
  "region": "225",
  "l10N": "LOCALIZATION_RU",
  "folderId": "<folder-id>",
  "responseFormat": "FORMAT_XML"
}
```

### Response XML structure
```
response/found              — total results count
response/results/grouping/group — each result group
  group/doc/url             — page URL
  group/doc/title           — page title (may contain <hlword> tags)
  group/doc/headline        — snippet text
  group/doc/domain          — domain
  group/doc/passages/passage — text excerpts
```

### Position calculation
```
Position = page * groups_per_page + position_in_page (1-indexed)
```

### Common region IDs
| ID | Region |
|----|--------|
| 225 | Russia |
| 213 | Moscow |
| 2 | Saint Petersburg |
| 54 | Yekaterinburg |
| 43 | Kazan |
| 66 | Novosibirsk |
| 56 | Nizhny Novgorod |

## Common use cases

### "What position does our site have?"
```bash
bash scripts/positions.sh --domain mysite.ru --query "купить дымоход" --region 213
```

### "Check positions for multiple queries"
```bash
# Create queries.txt with one query per line, then:
bash scripts/positions.sh --domain mysite.ru --queries queries.txt --region 213 --csv results.csv
```

### "Who are our competitors in search?"
```bash
bash scripts/competitors.sh --query "купить дымоход" --region 213
```

### "What shows up in search for this query?"
```bash
bash scripts/search.sh --query "купить дымоход" --region 213
```

### Custom query (advanced)
Use `common.sh` functions directly:
```bash
source scripts/common.sh
load_config

# Async XML search
xml=$(cloud_search "купить дымоход" "213" "10" "0" "relevance" "moderate")
echo "$xml"
```

## Sharing

To share this skill with colleagues:
1. Copy the entire `yandex-search/` folder to their `~/.claude/skills/`
2. They create their own `config/.env` with their API key and folder ID
3. Run `bash scripts/quota.sh` to verify

## Limits

- Yandex Cloud Search API v2: pay-per-use (check pricing at cloud.yandex.ru)
- Rate limit: 1 request/second recommended in batch mode
- Each request is async: ~1-3 seconds for result
- Max results per page: 100 (groupsOnPage)
- Pages: 0-indexed
