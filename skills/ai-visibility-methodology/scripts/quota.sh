#!/bin/bash
# Check API connections for all configured AI platforms
# Usage: bash quota.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

echo "=== AI Visibility — API Connection Check ==="
echo ""

TOTAL=0
OK=0
FAIL=0
SKIP=0

# OpenAI
TOTAL=$((TOTAL + 1))
if [[ -n "$OPENAI_API_KEY" ]]; then
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $OPENAI_API_KEY" \
        "https://api.openai.com/v1/models" 2>/dev/null)
    if [[ "$response" == "200" ]]; then
        echo "[OK]   OpenAI (ChatGPT)"
        OK=$((OK + 1))
    else
        echo "[FAIL] OpenAI — HTTP $response"
        FAIL=$((FAIL + 1))
    fi
else
    echo "[SKIP] OpenAI — OPENAI_API_KEY not set"
    SKIP=$((SKIP + 1))
fi

# Perplexity
TOTAL=$((TOTAL + 1))
if [[ -n "$PERPLEXITY_API_KEY" ]]; then
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"sonar","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' \
        "https://api.perplexity.ai/chat/completions" 2>/dev/null)
    if [[ "$response" == "200" ]]; then
        echo "[OK]   Perplexity"
        OK=$((OK + 1))
    else
        echo "[FAIL] Perplexity — HTTP $response"
        FAIL=$((FAIL + 1))
    fi
else
    echo "[SKIP] Perplexity — PERPLEXITY_API_KEY not set"
    SKIP=$((SKIP + 1))
fi

# Anthropic
TOTAL=$((TOTAL + 1))
if [[ -n "$ANTHROPIC_API_KEY" ]]; then
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "anthropic-version: 2023-06-01" \
        -H "Content-Type: application/json" \
        -d '{"model":"claude-sonnet-4-20250514","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}' \
        "https://api.anthropic.com/v1/messages" 2>/dev/null)
    if [[ "$response" == "200" ]]; then
        echo "[OK]   Anthropic (Claude)"
        OK=$((OK + 1))
    else
        echo "[FAIL] Anthropic — HTTP $response"
        FAIL=$((FAIL + 1))
    fi
else
    echo "[SKIP] Anthropic — ANTHROPIC_API_KEY not set"
    SKIP=$((SKIP + 1))
fi

# Google Gemini
TOTAL=$((TOTAL + 1))
if [[ -n "$GOOGLE_AI_API_KEY" ]]; then
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_AI_API_KEY" 2>/dev/null)
    if [[ "$response" == "200" ]]; then
        echo "[OK]   Google (Gemini)"
        OK=$((OK + 1))
    else
        echo "[FAIL] Google Gemini — HTTP $response"
        FAIL=$((FAIL + 1))
    fi
else
    echo "[SKIP] Google — GOOGLE_AI_API_KEY not set"
    SKIP=$((SKIP + 1))
fi

# Playwright (always available in Claude Code)
TOTAL=$((TOTAL + 1))
echo "[OK]   Playwright (browser fallback — always available)"
OK=$((OK + 1))

echo ""
echo "=== Summary: $TOTAL total | $OK OK | $FAIL failed | $SKIP skipped ==="

if [[ $OK -eq 0 ]]; then
    echo ""
    echo "No API keys configured. The skill will use Playwright browser automation."
    echo "Set API keys in config/.env for faster, more reliable checks."
fi
