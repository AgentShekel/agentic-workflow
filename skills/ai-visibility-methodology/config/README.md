# AI Visibility — Config Setup

## API Keys (Optional)

API keys enable fast, reliable checks without browser automation.
Store in `config/.env` or set as environment variables.

### OpenAI (ChatGPT)
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Set `OPENAI_API_KEY=sk-...`

### Perplexity
1. Go to https://www.perplexity.ai/settings/api
2. Generate API key
3. Set `PERPLEXITY_API_KEY=pplx-...`

### Anthropic (Claude)
1. Go to https://console.anthropic.com/settings/keys
2. Create a new API key
3. Set `ANTHROPIC_API_KEY=sk-ant-...`

### Google (Gemini)
1. Go to https://aistudio.google.com/apikey
2. Create API key
3. Set `GOOGLE_AI_API_KEY=AI...`

## No API Keys?

The skill works with Claude Code's built-in tools:
- **Playwright** — browser automation for Perplexity, Yandex Neyro (no login)
- **WebSearch** — Claude's own search for self-check
- **Manual mode** — generates prompts, you paste them into AI platforms yourself

## .env Template

```bash
# AI Visibility — API Keys
# Leave empty if not available; Playwright fallback will be used

OPENAI_API_KEY=
PERPLEXITY_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_AI_API_KEY=
```

## Sync from Orchestrator

If using yandex-analytics-methodology orchestrator, keys are synced automatically:
```bash
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/skills}"
bash "$SKILLS_ROOT"/yandex-analytics/scripts/sync-config.sh
```
