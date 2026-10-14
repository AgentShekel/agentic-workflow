#!/bin/bash
# Check Yandex Metrika API connection and counter info
# Usage: bash scripts/quota.sh [--counter ID]
# Without --counter: checks token validity by listing available counters

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "=== Yandex Metrika API Check ==="

if [[ -n "$YANDEX_METRIKA_COUNTER" ]]; then
    # Check specific counter
    echo "Counter: $YANDEX_METRIKA_COUNTER"
    echo ""

    response=$(metrika_management "")
    if [[ $? -ne 0 ]]; then
        echo "Error: API request failed"
        exit 1
    fi

    if echo "$response" | grep -q '"errors"'; then
        echo "API Error:"
        echo "$response"
        exit 1
    fi

    name=$(json_string "$response" "name")
    site=$(json_string "$response" "site")
    create_time=$(json_string "$response" "create_time")

    echo "Counter name: $name"
    echo "Site: $site"
    echo "Created: $create_time"
else
    # No counter — just check token is valid by listing counters
    echo "No counter specified — checking token validity..."
    echo ""

    local_url="${METRIKA_API}/management/v1/counters?per_page=5"
    curl_cfg="${TMPDIR:-/tmp}/ym_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_METRIKA_TOKEN"
CURLEOF

    response=$(curl -s -K "$curl_cfg" "$local_url")
    rm -f "$curl_cfg"

    if echo "$response" | grep -q '"errors"'; then
        echo "API Error:"
        echo "$response"
        exit 1
    fi

    rows=$(echo "$response" | grep -o '"rows":[0-9]*' | head -1 | sed 's/.*://')
    echo "Token valid. Available counters: ${rows:-unknown}"
fi

echo ""
echo "Connection OK"
