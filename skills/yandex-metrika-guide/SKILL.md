---
name: yandex-metrika-guide
domain: marketing
description: |
  [TOOL] Yandex Metrika API client (traffic overview, sources,
  devices, conversions, popular pages, audience geography, demographics).
  Preloaded by marketing-web-analyst and marketing-ppc-specialist agents.
---

# yandex-metrika

Informational skill — website traffic and user behavior analytics via Yandex Metrika API.

## Config

Requires `YANDEX_METRIKA_TOKEN` in `config/.env` (synced from yandex-analytics-methodology unified config).
Token setup and OAuth details in [config/README.md](config/README.md).

**Counter ID is per-project** — pass it via `--counter` flag on every script call.
Alternatively, set `YANDEX_METRIKA_COUNTER` in `config/.env` as a default for a single site.

## Workflow

1. **Check connection**: `bash scripts/quota.sh --counter 12345678`
2. **Run report** using appropriate script
3. **Interpret results** — the API returns raw JSON; parse and present key metrics

## Scripts

All scripts accept `--counter ID` to specify the Metrika counter. If not passed, falls back to `YANDEX_METRIKA_COUNTER` from config/.env.

### quota.sh
Check API connection and counter info.
```bash
bash scripts/quota.sh --counter 12345678
```

### overview.sh
Traffic overview: visits, pageviews, users, bounce rate, avg duration.
```bash
bash scripts/overview.sh --counter 12345678 --from 2025-01-01 --to 2025-01-31
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | no | today | End date (YYYY-MM-DD) |

### sources.sh
Traffic sources: search engines, referrals, direct, social.
```bash
bash scripts/sources.sh --counter 12345678 --from 2025-01-01 --to 2025-01-31 --limit 10
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date |
| `--to` | no | today | End date |
| `--limit` | no | 10 | Max rows per report |

### pages.sh
Popular pages: pageviews and users by URL.
```bash
bash scripts/pages.sh --counter 12345678 --from 2025-01-01 --limit 20

# Filter by URL substring
bash scripts/pages.sh --counter 12345678 --url "/price/"
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date |
| `--to` | no | today | End date |
| `--limit` | no | 20 | Max rows |
| `--url` | no | - | Filter pages by URL substring |

### devices.sh
Device, browser, and OS statistics.
```bash
bash scripts/devices.sh --counter 12345678 --type device
bash scripts/devices.sh --counter 12345678 --type browser
bash scripts/devices.sh --counter 12345678 --type os
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date |
| `--to` | no | today | End date |
| `--type` | no | device | `device`, `browser`, or `os` |

### goals.sh
Configured goals and conversion statistics.
```bash
# List goals only
bash scripts/goals.sh --counter 12345678 --list

# Goals with conversion stats
bash scripts/goals.sh --counter 12345678 --from 2025-01-01
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date |
| `--to` | no | today | End date |
| `--list` | no | false | Only list goals, skip stats |

### visitors.sh
Visitor demographics and geography.
```bash
bash scripts/visitors.sh --counter 12345678 --type geo
bash scripts/visitors.sh --counter 12345678 --type age
bash scripts/visitors.sh --counter 12345678 --type gender
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--counter` | yes* | from .env | Metrika counter ID |
| `--from` | no | 30 days ago | Start date |
| `--to` | no | today | End date |
| `--type` | no | geo | `geo`, `age`, or `gender` |

\* `--counter` is required unless `YANDEX_METRIKA_COUNTER` is set in config/.env

## API Reference

### Stat API (reports)
- Base: `https://api-metrika.yandex.net/stat/v1/data`
- Auth: `Authorization: OAuth <token>`
- Key params: `id` (counter), `preset` (report type), `date1`/`date2`, `metrics`, `dimensions`, `filters`, `sort`, `limit`

### Presets (most useful)
| Preset | Description |
|--------|-------------|
| `sources_summary` | Traffic by source type |
| `sources_search_engines` | Search engine breakdown |
| `sources_sites` | Referral sites |
| `tech_platforms` | Devices (desktop/mobile/tablet) |
| `tech_browsers` | Browser stats |
| `tech_os` | OS stats |
| `geo_country` | Geography by country |
| `age_gender` | Age and gender |
| `conversion_rate` | Goal conversions |

### Custom metrics (ym:s:*)
| Metric | Description |
|--------|-------------|
| `ym:s:visits` | Visits |
| `ym:s:pageviews` | Page views |
| `ym:s:users` | Unique users |
| `ym:s:bounceRate` | Bounce rate |
| `ym:s:avgVisitDurationSeconds` | Avg visit duration |

### Custom dimensions (ym:s:*)
| Dimension | Description |
|-----------|-------------|
| `ym:s:TrafficSource` | Traffic source |
| `ym:s:regionCity` | City |
| `ym:s:gender` | Gender |
| `ym:s:ageInterval` | Age group |
| `ym:s:deviceCategory` | Device type |

### Page-level metrics (ym:pv:*)
| Metric/Dimension | Description |
|------------------|-------------|
| `ym:pv:pageviews` | Page views |
| `ym:pv:users` | Users |
| `ym:pv:URLPath` | Page URL |

### Management API
- Base: `https://api-metrika.yandex.net/management/v1/counter/{id}/`
- Endpoints: `goals`, `filters`, `operations`, `grants`

## Common use cases

### "How's the site doing?"
```bash
bash scripts/overview.sh --counter 12345678
bash scripts/sources.sh --counter 12345678
bash scripts/devices.sh --counter 12345678
```

### "Which pages get the most traffic?"
```bash
bash scripts/pages.sh --counter 12345678 --limit 30
```

### "Are goals converting?"
```bash
bash scripts/goals.sh --counter 12345678
```

### "Who visits the site?"
```bash
bash scripts/visitors.sh --counter 12345678 --type geo
bash scripts/visitors.sh --counter 12345678 --type age
```

### Custom query (advanced)
Use `common.sh` functions directly:
```bash
source scripts/common.sh
load_config
YANDEX_METRIKA_COUNTER=12345678

# Custom metrics + dimensions
metrika_custom "ym:s:visits,ym:s:bounceRate" "ym:s:TrafficSource" "date1=2025-01-01&date2=2025-01-31&limit=10"
```

## Sharing

To share this skill with colleagues:
1. Copy the entire `yandex-metrika/` folder to their `~/.claude/skills/`
2. They create their own `config/.env` with their token
3. Run `bash scripts/quota.sh --counter THEIR_COUNTER` to verify

## Limits

- API rate limit: ~5 requests/second
- Daily limit depends on token type
- Data availability: ~5 min delay for real-time, historical data available fully
