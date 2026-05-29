#!/bin/bash
# Get indexing stats: summary, history, or page samples
# Usage:
#   bash scripts/indexing.sh --host https://example.com:443 --type summary
#   bash scripts/indexing.sh --host https://example.com:443 --type history --from 2025-01-01
#   bash scripts/indexing.sh --host https://example.com:443 --type samples --limit 20

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(default_from_date)
TO_DATE=$(default_to_date)
TYPE="summary"
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

echo "=== Indexing: $TYPE ==="
echo "Host: $HOST_ID"
echo ""

case "$TYPE" in
    summary)
        echo "--- Indexing Summary ---"
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/summary")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    history)
        echo "--- Indexing History ---"
        echo "Period: $FROM_DATE — $TO_DATE"
        echo ""
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/indexing/history?date_from=${FROM_DATE}&date_to=${TO_DATE}")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    samples)
        echo "--- Indexed Pages (samples) ---"
        echo "Limit: $LIMIT"
        echo ""
        response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/indexing/samples?limit=${LIMIT}&offset=0")
        if echo "$response" | grep -q '"error_code"'; then
            echo "API Error:"; echo "$response"; exit 1
        fi
        echo "$response"
        ;;
    *)
        echo "Unknown type: $TYPE (use: summary, history, samples)"
        exit 1
        ;;
esac
