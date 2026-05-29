#!/bin/bash
# Get external backlinks or broken internal links
# Usage:
#   bash scripts/links.sh --host https://example.com:443 --type external
#   bash scripts/links.sh --host https://example.com:443 --type external-history --from 2025-01-01
#   bash scripts/links.sh --host https://example.com:443 --type internal-broken

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(default_from_date)
TO_DATE=$(default_to_date)
TYPE="external"
LIMIT=100
HOST_PARAM=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_PARAM="$2"; shift 2 ;;
        --type) TYPE="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

HOST_ID=$(resolve_host "$HOST_PARAM")
if [[ $? -ne 0 ]]; then
    echo "$HOST_ID"
    exit 1
fi

USER_ID=$(get_user_id)
if [[ $? -ne 0 ]]; then
    echo "Error: Could not get user_id"
    exit 1
fi

echo "=== Links: $TYPE ==="
echo "Host: $HOST_ID"
echo ""

case "$TYPE" in
    external)
        echo "--- External Links (samples) ---"
        echo "Limit: $LIMIT"
        echo ""
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/links/external/samples?limit=${LIMIT}&offset=0")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    external-history)
        echo "--- External Links History ---"
        echo "Period: $FROM_DATE — $TO_DATE"
        echo ""
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/links/external/history?date_from=${FROM_DATE}&date_to=${TO_DATE}")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    internal-broken)
        echo "--- Broken Internal Links (samples) ---"
        echo "Limit: $LIMIT"
        echo ""
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/links/internal/samples?limit=${LIMIT}&offset=0")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    *)
        echo "Unknown type: $TYPE (use: external, external-history, internal-broken)"
        exit 1
        ;;
esac
