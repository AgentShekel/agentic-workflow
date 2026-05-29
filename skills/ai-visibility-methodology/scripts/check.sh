#!/bin/bash
# Unified AI Visibility Check — queries any AI platform via OpenRouter or direct API
# Usage: bash check.sh --platform chatgpt --prompts prompts.txt --brand "Brand" [--url domain.com] [--output results.json]
#
# Supported platforms: chatgpt, claude, gemini, deepseek, perplexity
# With OpenRouter: all platforms use single API key
# Without OpenRouter: falls back to individual API keys

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Platform → model mapping for OpenRouter
declare -A OPENROUTER_MODELS
OPENROUTER_MODELS[chatgpt]="openai/gpt-4o"
OPENROUTER_MODELS[claude]="anthropic/claude-sonnet-4-20250514"
OPENROUTER_MODELS[gemini]="google/gemini-2.0-flash-001"
OPENROUTER_MODELS[deepseek]="deepseek/deepseek-chat"
OPENROUTER_MODELS[perplexity]="perplexity/sonar"

# Platform → direct API config
declare -A DIRECT_API_URL
DIRECT_API_URL[chatgpt]="https://api.openai.com/v1/chat/completions"
DIRECT_API_URL[claude]="https://api.anthropic.com/v1/messages"
DIRECT_API_URL[gemini]="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
DIRECT_API_URL[deepseek]="https://api.deepseek.com/v1/chat/completions"
DIRECT_API_URL[perplexity]="https://api.perplexity.ai/chat/completions"

declare -A DIRECT_API_KEY_VAR
DIRECT_API_KEY_VAR[chatgpt]="OPENAI_API_KEY"
DIRECT_API_KEY_VAR[claude]="ANTHROPIC_API_KEY"
DIRECT_API_KEY_VAR[gemini]="GOOGLE_AI_API_KEY"
DIRECT_API_KEY_VAR[deepseek]="DEEPSEEK_API_KEY"
DIRECT_API_KEY_VAR[perplexity]="PERPLEXITY_API_KEY"

declare -A DIRECT_MODELS
DIRECT_MODELS[chatgpt]="gpt-4o"
DIRECT_MODELS[claude]="claude-sonnet-4-20250514"
DIRECT_MODELS[gemini]="gemini-2.0-flash"
DIRECT_MODELS[deepseek]="deepseek-chat"
DIRECT_MODELS[perplexity]="sonar"

PLATFORM=""
PROMPTS_FILE=""
BRAND=""
SITE_URL=""
MODEL_OVERRIDE=""
OUTPUT=""
ALL_PLATFORMS=false
PROJECT=""
SEGMENT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) PLATFORM="$2"; shift 2 ;;
        --all) ALL_PLATFORMS=true; shift ;;
        --prompts) PROMPTS_FILE="$2"; shift 2 ;;
        --brand) BRAND="$2"; shift 2 ;;
        --url) SITE_URL="$2"; shift 2 ;;
        --model) MODEL_OVERRIDE="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --project) PROJECT="$2"; shift 2 ;;
        --segment) SEGMENT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Load project data if --project specified
if [[ -n "$PROJECT" ]]; then
    pdir=$(init_project "$PROJECT")
    if [[ -z "$BRAND" ]]; then
        BRAND=$(get_project_field "$PROJECT" "brand-methodology")
    fi
    if [[ -z "$SITE_URL" ]]; then
        SITE_URL=$(get_project_field "$PROJECT" "url")
    fi
fi

if [[ -z "$PROMPTS_FILE" || -z "$BRAND" ]]; then
    echo "Usage: bash check.sh --platform chatgpt --prompts prompts.txt --brand \"Brand\" [--url domain.com]"
    echo "       bash check.sh --all --prompts prompts.txt --brand \"Brand\""
    echo "       bash check.sh --all --project my-brand --prompts prompts.txt"
    echo ""
    echo "Platforms: chatgpt, claude, gemini, deepseek, perplexity"
    echo "Use --all to check all platforms sequentially"
    echo "Use --project to link to a persistent project (auto-fills brand/url, saves history)"
    echo "Use --segment to tag results with a product/service segment"
    exit 1
fi

if [[ ! -f "$PROMPTS_FILE" ]]; then
    echo "Error: Prompts file not found: $PROMPTS_FILE"
    exit 1
fi

# Determine API mode: OpenRouter or Direct
get_api_mode() {
    local platform="$1"
    if [[ -n "$OPENROUTER_API_KEY" ]]; then
        echo "openrouter"
    else
        local key_var="${DIRECT_API_KEY_VAR[$platform]}"
        if [[ -n "${!key_var}" ]]; then
            echo "direct"
        else
            echo "none"
        fi
    fi
}

# Make API call via OpenRouter (OpenAI-compatible)
call_openrouter() {
    local model="$1"
    local prompt="$2"

    local body
    body=$(cat <<REQEOF
{"model":"$model","messages":[{"role":"user","content":"$(json_escape "$prompt")"}],"max_tokens":1500,"temperature":0.3}
REQEOF
)

    local curl_cfg="${TMPDIR:-/tmp}/aiv_curl_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: Bearer $OPENROUTER_API_KEY"
-H "Content-Type: application/json"
-H "HTTP-Referer: https://claude-code-skill"
-H "X-Title: AI Visibility Check"
CURLEOF

    local response
    response=$(curl -s -K "$curl_cfg" -d "$body" "https://openrouter.ai/api/v1/chat/completions" 2>/dev/null)
    rm -f "$curl_cfg"

    # Extract content from OpenAI-compatible response
    echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['choices'][0]['message']['content'])
except:
    print('')
" 2>/dev/null
}

# Make API call via direct platform API
call_direct() {
    local platform="$1"
    local prompt="$2"
    local key_var="${DIRECT_API_KEY_VAR[$platform]}"
    local api_key="${!key_var}"
    local url="${DIRECT_API_URL[$platform]}"
    local model="${DIRECT_MODELS[$platform]}"

    local curl_cfg="${TMPDIR:-/tmp}/aiv_curl_$$.txt"

    if [[ "$platform" == "claude" ]]; then
        # Anthropic uses different API format
        local body="{\"model\":\"$model\",\"max_tokens\":1500,\"messages\":[{\"role\":\"user\",\"content\":\"$(json_escape "$prompt")\"}]}"
        cat > "$curl_cfg" <<CURLEOF
-H "x-api-key: $api_key"
-H "anthropic-version: 2023-06-01"
-H "Content-Type: application/json"
CURLEOF
        local response
        response=$(curl -s -K "$curl_cfg" -d "$body" "$url" 2>/dev/null)
        rm -f "$curl_cfg"
        echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['content'][0]['text'])
except:
    print('')
" 2>/dev/null

    elif [[ "$platform" == "gemini" ]]; then
        # Google uses different API format
        local body="{\"contents\":[{\"parts\":[{\"text\":\"$(json_escape "$prompt")\"}]}],\"generationConfig\":{\"maxOutputTokens\":1500,\"temperature\":0.3}}"
        local response
        response=$(curl -s -H "Content-Type: application/json" -d "$body" "${url}?key=${api_key}" 2>/dev/null)
        rm -f "$curl_cfg"
        echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['candidates'][0]['content']['parts'][0]['text'])
except:
    print('')
" 2>/dev/null

    else
        # OpenAI-compatible (ChatGPT, DeepSeek, Perplexity)
        local body="{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"$(json_escape "$prompt")\"}],\"max_tokens\":1500,\"temperature\":0.3}"
        cat > "$curl_cfg" <<CURLEOF
-H "Authorization: Bearer $api_key"
-H "Content-Type: application/json"
CURLEOF
        local response
        response=$(curl -s -K "$curl_cfg" -d "$body" "$url" 2>/dev/null)
        rm -f "$curl_cfg"
        echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['choices'][0]['message']['content'])
except:
    print('')
" 2>/dev/null
    fi
}

# Run check for a single platform
run_platform_check() {
    local platform="$1"
    local api_mode
    api_mode=$(get_api_mode "$platform")

    if [[ "$api_mode" == "none" ]]; then
        echo "[SKIP] $platform — no API key available"
        return 1
    fi

    local model_name
    if [[ -n "$MODEL_OVERRIDE" ]]; then
        model_name="$MODEL_OVERRIDE"
    elif [[ "$api_mode" == "openrouter" ]]; then
        model_name="${OPENROUTER_MODELS[$platform]}"
    else
        model_name="${DIRECT_MODELS[$platform]}"
    fi

    echo "=== $platform Visibility Check (via $api_mode) ==="
    echo "Brand: $BRAND"
    echo "Model: $model_name"
    echo "Prompts: $(grep -cv '^$\|^#' "$PROMPTS_FILE") queries"
    echo ""

    local RESULTS="["
    local FIRST=true
    local mentioned_count=0
    local link_count=0
    local total_count=0

    while IFS= read -r prompt || [[ -n "$prompt" ]]; do
        [[ -z "$prompt" || "$prompt" == \#* ]] && continue

        total_count=$((total_count + 1))
        echo -n "  [$total_count] $prompt ... "

        local answer=""
        if [[ "$api_mode" == "openrouter" ]]; then
            answer=$(call_openrouter "$model_name" "$prompt")
        else
            answer=$(call_direct "$platform" "$prompt")
        fi

        if [[ -z "$answer" ]]; then
            echo "API ERROR"
            continue
        fi

        # Analyze response
        local mentioned link_present position sentiment competitors excerpt sources_json
        mentioned=$(check_mention "$answer" "$BRAND")
        link_present="false"
        if [[ -n "$SITE_URL" ]]; then
            link_present=$(check_link "$answer" "$SITE_URL")
        fi
        position=$(find_position "$answer" "$BRAND")
        sentiment=$(analyze_sentiment "$answer" "$BRAND")
        competitors=$(extract_competitors "$answer" "$BRAND")
        excerpt=$(truncate_text "$answer" 200)
        sources_json=$(extract_sources "$answer")

        if [[ "$mentioned" == "true" ]]; then
            mentioned_count=$((mentioned_count + 1))
            echo "FOUND (pos: $position, $sentiment)"
        else
            echo "NOT FOUND"
        fi

        if [[ "$link_present" == "true" ]]; then
            link_count=$((link_count + 1))
        fi

        local result
        result=$(make_result_json "$prompt" "$mentioned" "$link_present" "$position" "$sentiment" "$competitors" "$excerpt")

        if [[ "$FIRST" == "true" ]]; then
            RESULTS="$RESULTS
$result"
            FIRST=false
        else
            RESULTS="$RESULTS,
$result"
        fi

        # Rate limiting
        sleep 1

    done < "$PROMPTS_FILE"

    RESULTS="$RESULTS
]"

    # Calculate metrics
    local mention_rate=0
    local citation_rate=0
    if [[ $total_count -gt 0 ]]; then
        mention_rate=$(( mentioned_count * 100 / total_count ))
        citation_rate=$(( link_count * 100 / total_count ))
    fi

    echo ""
    echo "--- Summary: Mention Rate: ${mention_rate}% | Citation Rate: ${citation_rate}% ---"
    echo ""

    # Calculate top-1 rate
    local top1_count=0
    # Count results where position == 1 using python for reliability
    top1_count=$(echo "$RESULTS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(sum(1 for r in data if r.get('position') == 1))
except:
    print(0)
" 2>/dev/null || echo "0")

    local top1_rate=0
    if [[ $total_count -gt 0 ]]; then
        top1_rate=$(( top1_count * 100 / total_count ))
    fi

    local segment_field=""
    if [[ -n "$SEGMENT" ]]; then
        segment_field="\"segment\": \"$(json_escape "$SEGMENT")\","
    fi

    local project_field=""
    if [[ -n "$PROJECT" ]]; then
        project_field="\"project\": \"$(json_escape "$PROJECT")\","
    fi

    local FULL_JSON
    FULL_JSON=$(cat <<EOF
{
  "platform": "$platform",
  "api_mode": "$api_mode",
  "model": "$model_name",
  $project_field
  $segment_field
  "brand-methodology": "$(json_escape "$BRAND")",
  "site_url": "$(json_escape "$SITE_URL")",
  "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "metrics": {
    "total_prompts": $total_count,
    "mentioned": $mentioned_count,
    "links_found": $link_count,
    "mention_rate": $mention_rate,
    "citation_rate": $citation_rate,
    "top1_rate": $top1_rate
  },
  "results": $RESULTS
}
EOF
)

    local output_file="$OUTPUT"
    if [[ "$ALL_PLATFORMS" == "true" && -n "$OUTPUT" ]]; then
        # In --all mode, save per-platform files
        local dir ext base
        dir=$(dirname "$OUTPUT")
        base=$(basename "$OUTPUT" | sed 's/\.[^.]*$//')
        ext=$(basename "$OUTPUT" | grep -o '\.[^.]*$')
        output_file="${dir}/${base}-${platform}${ext}"
    fi

    if [[ -n "$output_file" ]]; then
        echo "$FULL_JSON" > "$output_file"
        echo "Results saved to: $output_file"
        # Auto-save to history if project is set
        if [[ -n "$PROJECT" ]]; then
            local hist_path
            hist_path=$(save_to_history "$PROJECT" "$output_file")
            echo "History saved: $hist_path"
        fi
    else
        echo "$FULL_JSON"
        # Save to history via temp file if project is set
        if [[ -n "$PROJECT" ]]; then
            local tmp_file="${TMPDIR:-/tmp}/aiv_result_${platform}_$$.json"
            echo "$FULL_JSON" > "$tmp_file"
            local hist_path
            hist_path=$(save_to_history "$PROJECT" "$tmp_file")
            rm -f "$tmp_file"
            echo "History saved: $hist_path" >&2
        fi
    fi
}

# Main execution
if [[ "$ALL_PLATFORMS" == "true" ]]; then
    echo "=== Running visibility check across ALL platforms ==="
    echo ""
    for p in chatgpt claude gemini deepseek perplexity; do
        run_platform_check "$p"
        echo ""
    done
elif [[ -n "$PLATFORM" ]]; then
    if [[ -z "${OPENROUTER_MODELS[$PLATFORM]}" ]]; then
        echo "Error: Unknown platform '$PLATFORM'"
        echo "Supported: chatgpt, claude, gemini, deepseek, perplexity"
        exit 1
    fi
    run_platform_check "$PLATFORM"
else
    echo "Error: Specify --platform or --all"
    exit 1
fi
