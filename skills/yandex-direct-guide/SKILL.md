---
name: yandex-direct-guide
domain: marketing
description: |
  [TOOL] Yandex Direct API v5 client (campaigns, ads, bids, keywords,
  spend reports, CTR, conversions). Preloaded by marketing-ppc-specialist agent.
---

# yandex-direct

Informational skill — ad campaign management and statistics via Yandex Direct API v5.

## Config

Requires `YANDEX_DIRECT_TOKEN` in `config/.env`.
Optionally `YANDEX_DIRECT_LOGIN` for agency accounts.
See `config/README.md` for token setup instructions.

**Important:** OAuth token with Direct scope is NOT enough. You must also register the app via Yandex Direct support:
1. Copy **ClientId** from the OAuth app settings page
2. Contact **Yandex Direct support** — provide your username and ClientId
3. Wait for approval (usually 1-2 business days)

Without this step, the API returns error 58 ("Незавершенная регистрация") / 403 Forbidden.

## Workflow

1. **Check connection**: `bash scripts/quota.sh`
2. **Run script** for the needed operation
3. **Interpret results** — scripts output formatted data; parse and present key metrics

## Scripts

### quota.sh
Check API connection and account info.
```bash
bash scripts/quota.sh
```

### campaigns.sh
List and manage campaigns.
```bash
# List all campaigns
bash scripts/campaigns.sh --action list

# List only accepted campaigns
bash scripts/campaigns.sh --action list --status ACCEPTED

# Suspend a campaign
bash scripts/campaigns.sh --action suspend --id 12345

# Resume a campaign
bash scripts/campaigns.sh --action resume --id 12345

# Archive a campaign
bash scripts/campaigns.sh --action archive --id 12345

# Unarchive a campaign
bash scripts/campaigns.sh --action unarchive --id 12345
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--action` | no | list | `list`, `suspend`, `resume`, `archive`, `unarchive` |
| `--id` | for actions | - | Campaign ID (required for suspend/resume/archive/unarchive) |
| `--status` | no | - | Filter by status: ACCEPTED, DRAFT, MODERATION, etc. |
| `--limit` | no | 100 | Max campaigns to return |

### ads.sh
List ads for a campaign or ad group.
```bash
# List ads for a campaign
bash scripts/ads.sh --campaign 12345 --limit 20

# List ads for an ad group
bash scripts/ads.sh --adgroup 67890
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--campaign` | no | - | Filter by campaign ID |
| `--adgroup` | no | - | Filter by ad group ID |
| `--limit` | no | 50 | Max ads to return |

### keywords.sh
List keywords for a campaign or ad group.
```bash
# Keywords for a campaign
bash scripts/keywords.sh --campaign 12345 --limit 50

# Keywords for an ad group
bash scripts/keywords.sh --adgroup 67890
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--campaign` | no | - | Filter by campaign ID |
| `--adgroup` | no | - | Filter by ad group ID |
| `--limit` | no | 100 | Max keywords to return |

### report.sh
Generate statistics reports. **Most important script.**
```bash
# Campaign performance for a month
bash scripts/report.sh --type campaign --from 2025-01-01 --to 2025-01-31

# Ad performance
bash scripts/report.sh --type ad --from 2025-01-01 --to 2025-01-31

# Keyword performance
bash scripts/report.sh --type keyword --from 2025-01-01 --to 2025-01-31

# Search queries report
bash scripts/report.sh --type search_queries --from 2025-01-01 --to 2025-01-31 --campaign 12345

# Custom report with specific fields, save to CSV
bash scripts/report.sh --type custom --from 2025-01-01 --to 2025-01-31 --fields "Date,CampaignName,Impressions,Clicks,Cost,Ctr" --csv report.csv
```

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `--type` | no | campaign | `campaign`, `ad`, `keyword`, `search_queries`, `custom` |
| `--from` | no | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | no | today | End date (YYYY-MM-DD) |
| `--campaign` | no | - | Filter by campaign ID |
| `--fields` | for custom | - | Comma-separated field names |
| `--csv` | no | - | Save output to CSV file |

## API Reference

### Base URL
- Production: `https://api.direct.yandex.com/json/v5/`
- Sandbox: `https://api-sandbox.direct.yandex.com/json/v5/`

### Auth
- Header: `Authorization: Bearer <token>`

### Request format
All requests are POST with JSON body:
```json
{"method": "get", "params": {...}}
```

### Key services & endpoints

| Service | Endpoint | Methods |
|---------|----------|---------|
| Campaigns | `/campaigns` | get, add, update, suspend, resume, archive, unarchive |
| AdGroups | `/adgroups` | get, add, update, delete |
| Ads | `/ads` | get, add, update, delete, suspend, resume |
| Keywords | `/keywords` | get, add, update, delete, suspend, resume |
| Reports | `/reports` | POST (special format) |
| Clients | `/clients` | get |

### Reports service

Special endpoint for statistics:
- URL: `https://api.direct.yandex.com/json/v5/reports`
- Extra headers: `Accept-Language`, `returnMoneyInMicros`, `skipReportHeader`, `skipReportSummary`
- Returns TSV/CSV data, not JSON
- Async: HTTP 201 = building, 202 = in progress, 200 = ready

#### Report types
| Type | Description |
|------|-------------|
| `CAMPAIGN_PERFORMANCE_REPORT` | Campaign-level stats |
| `AD_PERFORMANCE_REPORT` | Ad-level stats |
| `CRITERIA_PERFORMANCE_REPORT` | Keyword/criteria stats |
| `SEARCH_QUERY_PERFORMANCE_REPORT` | Search queries |
| `CUSTOM_REPORT` | Custom field selection |

#### Common report fields
| Field | Description |
|-------|-------------|
| `Date` | Date |
| `CampaignName` | Campaign name |
| `CampaignId` | Campaign ID |
| `AdGroupName` | Ad group name |
| `AdGroupId` | Ad group ID |
| `Impressions` | Impressions |
| `Clicks` | Clicks |
| `Cost` | Cost (micros) |
| `Ctr` | CTR % |
| `AvgCpc` | Average CPC (micros) |
| `Conversions` | Conversions |
| `CostPerConversion` | CPA (micros) |
| `AvgImpressionPosition` | Avg position |
| `Query` | Search query (for SEARCH_QUERY_PERFORMANCE_REPORT) |

### Monetary values
All monetary values are in **micros** (1 ruble = 1,000,000 micros). Divide by 1,000,000 to get rubles.

### Campaign statuses
| Status | Description |
|--------|-------------|
| `ACCEPTED` | Active / accepted by moderation |
| `DRAFT` | Draft |
| `MODERATION` | In moderation |
| `SUSPENDED` | Suspended by user |
| `OFF` | Stopped (budget/time) |
| `ENDED` | Ended |
| `ARCHIVED` | Archived |

### Ad statuses
| Status | Description |
|--------|-------------|
| `ACCEPTED` | Active |
| `DRAFT` | Draft |
| `MODERATION` | In moderation |
| `SUSPENDED` | Suspended |
| `REJECTED` | Rejected |

## Common use cases

### "How are my ads performing?"
```bash
bash scripts/report.sh --type campaign --from 2025-01-01 --to 2025-01-31
```

### "Show my active campaigns"
```bash
bash scripts/campaigns.sh --action list --status ACCEPTED
```

### "What keywords are expensive?"
```bash
bash scripts/report.sh --type keyword --from 2025-01-01 --to 2025-01-31
```
Sort results by Cost descending to find expensive keywords.

### "What are people searching for?"
```bash
bash scripts/report.sh --type search_queries --from 2025-01-01 --to 2025-01-31
```

### "Pause a campaign"
```bash
bash scripts/campaigns.sh --action suspend --id 12345
```

### "Daily breakdown of costs"
```bash
bash scripts/report.sh --type custom --from 2025-01-01 --to 2025-01-31 --fields "Date,CampaignName,Impressions,Clicks,Cost,Ctr,AvgCpc"
```

### Custom query (advanced)
Use `common.sh` functions directly:
```bash
source scripts/common.sh
load_config

# Get campaign list
direct_post "campaigns" '{"method":"get","params":{"SelectionCriteria":{},"FieldNames":["Id","Name","Status","State"]}}'

# Get report
direct_report '{"params":{"SelectionCriteria":{"DateFrom":"2025-01-01","DateTo":"2025-01-31"},"FieldNames":["Date","CampaignName","Clicks","Cost"],"ReportName":"my_report","ReportType":"CAMPAIGN_PERFORMANCE_REPORT","DateRangeType":"CUSTOM_DATE","Format":"TSV","IncludeVAT":"YES"}}'
```

## Example session

```
User: Покажи статистику расходов по кампаниям за последний месяц
Agent:
1. bash scripts/quota.sh  → connection OK
2. bash scripts/report.sh --type campaign --from 2025-02-01 --to 2025-02-28
3. Parse TSV output, convert Cost from micros to rubles, present table

User: Какие поисковые запросы самые дорогие?
Agent:
1. bash scripts/report.sh --type search_queries --from 2025-02-01 --to 2025-02-28
2. Sort by Cost, show top queries with Clicks, Cost, CTR

User: Останови кампанию 12345
Agent:
1. bash scripts/campaigns.sh --action suspend --id 12345
2. Confirm campaign suspended
```

## Sharing

To share this skill with colleagues:
1. Copy the entire `yandex-direct/` folder to their `~/.claude/skills/`
2. They create their own `config/.env` with their token
3. Run `bash scripts/quota.sh` to verify

## Limits

- API rate limit: varies by method (campaigns: 5 req/sec, reports: 5 req/sec)
- Reports may take time to generate (async processing)
- Report data granularity depends on report type
- Monetary values always in micros — scripts auto-convert to rubles
