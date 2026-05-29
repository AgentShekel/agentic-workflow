---
name: yandex-analytics-methodology
domain: marketing
description: |
  [TOOL] Unified Yandex analytics hub configuration (shared
  tokens, cross-service workflows across Webmaster, Metrika, Wordstat, Direct,
  Search, seo-auditing, semantic-drift). Preloaded by marketing-web-analyst and
  marketing-traffic-lead agents.
---

# yandex-analytics

Informational skill — unified Yandex analytics hub with single config and cross-service workflows.

## Config

Single config file for all Yandex services: `config/.env`

```bash
# === OAuth Token (Webmaster + Metrika + Direct + Wordstat) ===
# One token with all scopes — see config/README.md for setup
YANDEX_OAUTH_TOKEN=y0_your_token

# === Metrika ===
# Counter ID is PER-PROJECT — pass via --counter flag when running metrika scripts
# Set here only as default if you mostly work with one site:
# YANDEX_METRIKA_COUNTER=12345678

# === Yandex Cloud Search API v2 ===
YANDEX_SEARCH_API_KEY=your_api_key
YANDEX_CLOUD_FOLDER_ID=your_folder_id

# === Optional: Direct sandbox ===
# YANDEX_DIRECT_SANDBOX=true
# YANDEX_DIRECT_LOGIN=agency_client_login

# === Semantic Drift ===
# No API keys needed — uses local sentence-transformers model
```

**Note:** Metrika counter ID varies per project. All metrika scripts accept `--counter ID` flag.

Run `bash scripts/check.sh` to verify which services are configured.

## Architecture

This skill is an orchestrator over individual Yandex skills:

```
yandex-analytics/          <- unified entry point
  config/.env              <- SINGLE config for all services
  scripts/
    check.sh               <- verify all connections
    sync-config.sh         <- propagate config to individual skills
    dashboard.sh           <- quick status of all services
  SKILL.md                 <- this file

yandex-webmaster/          <- indexing, queries, diagnostics
yandex-metrika/            <- traffic, behavior, conversions
yandex-wordstat/           <- search demand, semantics
yandex-direct/             <- ad campaigns, statistics
yandex-search/             <- SERP positions, competitors
seo-audit/                 <- comprehensive SEO audit orchestrator
semantic-drift/            <- topical drift analysis
```

## Setup (one-time)

### Step 1: Configure tokens
```bash
cp config/.env.example config/.env
# Edit config/.env with your tokens
```

### Step 2: Sync config to all skills
```bash
bash scripts/sync-config.sh
```
This propagates the unified config to individual skill config directories.

### Step 3: Verify connections
```bash
bash scripts/check.sh
```

## Quick Reference

### What do I need for...?

| Task | Required Services | Command |
|------|------------------|---------|
| Site traffic overview | Metrika | `bash ~/...metrika/scripts/overview.sh --counter ID` |
| Check indexing | Webmaster | `bash ~/...webmaster/scripts/indexing.sh` |
| Search positions | Search XML | `bash ~/...search/scripts/positions.sh` |
| Keyword research | Wordstat | `bash ~/...wordstat/scripts/top_requests.sh` |
| Ad campaign stats | Direct | `bash ~/...direct/scripts/report.sh` |
| Full SEO audit | All | invoke `seo-auditing` skill |
| Semantic drift | Webmaster + Metrika | `python ~/...semantic-drift/scripts/analyze.py` |

### Token Scopes Required

| Service | OAuth Scope |
|---------|-------------|
| Webmaster | Яндекс.Вебмастер -> Получение информации о сайтах |
| Metrika | Яндекс.Метрика -> Получение статистики, чтение параметров |
| Direct | Яндекс.Директ -> Управление кампаниями, Получение статистики |
| Wordstat | API Вордстата |

All four use the same OAuth token if you add all scopes when creating the app.

### Нюансы регистрации

#### Wordstat API
- Использует OAuth-токен (тот же, что Вебмастер/Метрика), но требует отдельное одобрение доступа к API
- Ошибка без одобрения: 403 Forbidden
- Как получить доступ: отправить запрос через поддержку Яндекс Директа с логином и ClientId из OAuth-приложения
- Одобрение Wordstat и Direct — отдельные процессы, одно может быть одобрено без другого
- После одобрения существующий OAuth-токен сразу работает — новый токен получать не нужно

#### Direct API
- Использует тот же OAuth-токен, тоже требует отдельное одобрение доступа к API
- Ошибка без одобрения: код 58 «Незавершенная регистрация»
- Как получить доступ:
  1. Зайти на `direct.yandex.ru` → Настройки (шестерёнка) → Настройки API
  2. Вкладка «Мои заявки» → «Новая заявка»
  3. Прямая ссылка: `https://direct.yandex.ru/registered/main.pl?cmd=apiSettings`
  4. Указать ClientId из OAuth-приложения, описать назначение
  5. Ждать от 1 часа до 3 рабочих дней (рассмотрение пн-пт 10:00-19:00 МСК)
- Одна заявка на приложение — покрывает всех пользователей этого приложения

#### Search API v2 (Yandex Cloud)
- Не использует OAuth — полностью отдельная авторизация через Yandex Cloud
- Старый XML API (`xml.yandex.ru`) мёртв с ~2025 года (ошибка 4002)
- **Шаги настройки:**
  1. Зарегистрироваться в `console.yandex.cloud`
  2. Создать сервисный аккаунт
  3. Назначить роли: `search-api.executor` + `search-api.webSearch.user` (обе обязательны)
  4. Создать API-ключ для сервисного аккаунта
  5. Скопировать folder ID из консоли Cloud (выпадающий список слева вверху → копировать ID)
- **Частая ошибка:** неправильный folder ID. Каталог должен быть в том же облаке, где у сервисного аккаунта назначены роли
- API асинхронный: POST для отправки запроса → опрос endpoint операций → получение XML в base64
- Тарификация: оплата за запрос (бесплатного лимита, как у старого XML API, нет)

#### Общие советы
- Создавайте одно OAuth-приложение со всеми скоупами на `oauth.yandex.ru/client/new` — экономит время
- Скоупы для включения: Вебмастер, Метрика, Директ, Вордстат (4 галочки)
- После создания OAuth-приложения всё равно нужно отдельно подать заявки на доступ к API Директа и Вордстата
- Search API использует совершенно другую авторизацию (API-ключ Yandex Cloud, не OAuth)

## Workflow Examples

### "How's the site doing?" (quick dashboard)
```bash
bash scripts/dashboard.sh --host https://example.com
```
Runs: Metrika overview + Webmaster summary + SQI. Shows combined metrics.

### "Full SEO audit"
Invoke the `seo-auditing` skill — it will use data from all configured services.

### "Semantic drift analysis"
```bash
# Resolve skills root (default ~/.claude/skills, override via SKILLS_ROOT env)
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/skills}"

# 1. Collect data
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/search_queries.sh \
  --host https://example.com --limit 500 --csv /tmp/queries.csv

# 2. Analyze
python "$SKILLS_ROOT"/semantic-drift/scripts/analyze.py \
  --queries /tmp/queries.csv --output /tmp/drift.html
```

### "Research keyword + check position + see traffic"
```bash
# 1. Demand in Wordstat
bash "$SKILLS_ROOT"/yandex-wordstat/scripts/top_requests.sh \
  --phrase "купить кирпич" --regions 213

# 2. Current position
bash "$SKILLS_ROOT"/yandex-search/scripts/positions.sh \
  --domain example.com --query "купить кирпич" --region 213

# 3. Current traffic to related pages (pass counter ID for the project)
bash "$SKILLS_ROOT"/yandex-metrika/scripts/pages.sh --counter 12345678 --url "/kirpich/"
```

## Limits Summary

| Service | Rate Limit | Daily Limit |
|---------|-----------|-------------|
| Webmaster | ~5 req/s | depends on token |
| Metrika | ~5 req/s | depends on token |
| Wordstat | 10 req/s | 1000 req/day |
| Direct | 5 req/s | reports async |
| Search API v2 | 1 req/s | pay-per-use |
