---
name: yandex-webmaster-guide
domain: marketing
description: |
  [TOOL] Yandex Webmaster API v4 client (indexing status, search
  queries from SERP, crawl errors, backlinks, sitemaps, site diagnostics,
  SQI history). Preloaded by marketing-seo-specialist agent.
---

# yandex-webmaster

Informational skill — website SEO health and search performance via Yandex Webmaster API v4.

## Config

Requires `YANDEX_WEBMASTER_TOKEN` in `config/.env` (synced from yandex-analytics-methodology unified config).
Optionally set `YANDEX_WEBMASTER_HOST` for a default host.
Token setup and OAuth registration details in [config/README.md](config/README.md).

## Workflow

1. **Check connection**: `bash scripts/quota.sh` — verifies token, gets user_id
2. **List hosts**: `bash scripts/hosts.sh` — shows all registered sites
3. **Run report** using appropriate script with `--host` parameter
4. **Interpret results** — the API returns raw JSON; parse and present key metrics

## Scripts

### quota.sh
Check API connection, show user_id, list hosts.
```bash
bash scripts/quota.sh
```

### hosts.sh
List all sites registered in Yandex Webmaster with their verification status.
```bash
bash scripts/hosts.sh
```

### search_queries.sh
Popular search queries from Yandex SERP for a specific site.
```bash
bash scripts/search_queries.sh --host https://example.com:443 --from 2025-01-01 --to 2025-01-31 --limit 20 --order TOTAL_CLICKS
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL (e.g., `https://example.com:443`) |
| `--from` | no | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | no | today | End date (YYYY-MM-DD) |
| `--limit` | no | 20 | Max rows |
| `--order` | no | TOTAL_CLICKS | Sort by: `TOTAL_SHOWS` or `TOTAL_CLICKS` |
| `--indicator` | no | TOTAL_SHOWS,TOTAL_CLICKS,AVG_SHOW_POSITION,AVG_CLICK_POSITION | Query indicators |

### indexing.sh
Indexing stats: summary, history, or indexed page samples.
```bash
bash scripts/indexing.sh --host https://example.com:443 --type summary
bash scripts/indexing.sh --host https://example.com:443 --type history --from 2025-01-01
bash scripts/indexing.sh --host https://example.com:443 --type samples --limit 20
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |
| `--type` | no | summary | `summary`, `history`, or `samples` |
| `--from` | no | 30 days ago | Start date (for history) |
| `--to` | no | today | End date (for history) |
| `--limit` | no | 100 | Max rows (for samples) |

### diagnostics.sh
Site diagnostics — problems found by Yandex crawler.
```bash
bash scripts/diagnostics.sh --host https://example.com:443
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |

### links.sh
External backlinks or broken internal links.
```bash
bash scripts/links.sh --host https://example.com:443 --type external
bash scripts/links.sh --host https://example.com:443 --type internal-broken
bash scripts/links.sh --host https://example.com:443 --type external-history --from 2025-01-01
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |
| `--type` | no | external | `external`, `external-history`, or `internal-broken` |
| `--from` | no | 30 days ago | Start date (for history) |
| `--to` | no | today | End date (for history) |
| `--limit` | no | 100 | Max rows (for samples) |

### sitemaps.sh
List sitemaps registered for a site.
```bash
bash scripts/sitemaps.sh --host https://example.com:443
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |

### recrawl.sh
Submit a URL for recrawling or check recrawl quota.
```bash
bash scripts/recrawl.sh --host https://example.com:443 --url https://example.com/page
bash scripts/recrawl.sh --host https://example.com:443 --quota
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |
| `--url` | no | — | URL to submit for recrawl |
| `--quota` | no | false | Show recrawl quota only |

### sqi.sh
SQI (Site Quality Index) history.
```bash
bash scripts/sqi.sh --host https://example.com:443 --from 2025-01-01
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--host` | yes | — | Host URL |
| `--from` | no | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | no | today | End date (YYYY-MM-DD) |

## API Reference

### Webmaster API v4
- Base: `https://api.webmaster.yandex.net/v4`
- Auth: `Authorization: OAuth <token>`
- First get user_id: `GET /user` → `{"user_id": 12345}`
- Then all requests use: `/user/{user_id}/hosts/...`

### Host ID format
Yandex Webmaster uses host IDs in format `https:example.com:443`. Scripts accept
normal URLs like `https://example.com` or `https://example.com:443` and convert
them automatically.

### Key endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /user` | Get user_id |
| `GET /user/{uid}/hosts` | List all registered sites |
| `GET /user/{uid}/hosts/{hostId}/summary` | Site indexing summary |
| `GET /user/{uid}/hosts/{hostId}/search-queries/popular` | Popular search queries |
| `GET /user/{uid}/hosts/{hostId}/indexing/samples` | Indexed page samples |
| `GET /user/{uid}/hosts/{hostId}/indexing/history` | Indexing history |
| `GET /user/{uid}/hosts/{hostId}/links/external/samples` | External backlinks |
| `GET /user/{uid}/hosts/{hostId}/links/external/history` | External links history |
| `GET /user/{uid}/hosts/{hostId}/links/internal/samples` | Broken internal links |
| `GET /user/{uid}/hosts/{hostId}/diagnostics` | Site diagnostics |
| `GET /user/{uid}/hosts/{hostId}/sitemaps` | Sitemaps |
| `POST /user/{uid}/hosts/{hostId}/recrawl/queue` | Submit URL for recrawl |
| `GET /user/{uid}/hosts/{hostId}/recrawl/quota` | Recrawl quota |
| `GET /user/{uid}/hosts/{hostId}/sqi/history` | SQI history |
| `GET /user/{uid}/hosts/{hostId}/search-queries/all/history` | All queries stats |

### Search queries indicators
| Indicator | Description |
|-----------|-------------|
| `TOTAL_SHOWS` | Total impressions in search |
| `TOTAL_CLICKS` | Total clicks from search |
| `AVG_SHOW_POSITION` | Average position when shown |
| `AVG_CLICK_POSITION` | Average position when clicked |

## Common use cases

### "How's the site doing in Yandex?"
```bash
bash scripts/quota.sh
bash scripts/indexing.sh --host https://example.com:443 --type summary
bash scripts/sqi.sh --host https://example.com:443
```

### "What queries bring traffic from Yandex?"
```bash
bash scripts/search_queries.sh --host https://example.com:443 --limit 30 --order TOTAL_CLICKS
```

### "Are there indexing problems?"
```bash
bash scripts/diagnostics.sh --host https://example.com:443
bash scripts/indexing.sh --host https://example.com:443 --type samples
```

### "What's the backlink profile?"
```bash
bash scripts/links.sh --host https://example.com:443 --type external --limit 50
bash scripts/links.sh --host https://example.com:443 --type external-history
```

### "Are sitemaps working?"
```bash
bash scripts/sitemaps.sh --host https://example.com:443
```

### "Force recrawl a page"
```bash
bash scripts/recrawl.sh --host https://example.com:443 --quota
bash scripts/recrawl.sh --host https://example.com:443 --url https://example.com/updated-page
```

### Custom query (advanced)
Use `common.sh` functions directly:
```bash
source scripts/common.sh
load_config
USER_ID=$(get_user_id)

# Custom GET request
webmaster_get "/user/${USER_ID}/hosts"
```

## Sharing

To share this skill with colleagues:
1. Copy the entire `yandex-webmaster/` folder to their `~/.claude/skills/`
2. They create their own `config/.env` with their token
3. Run `bash scripts/quota.sh` to verify

## Limits

- API rate limit: ~5 requests/second
- Recrawl quota: limited per day (check via `--quota`)
- Historical data depth varies by endpoint
- Host must be verified in Yandex Webmaster to access data
