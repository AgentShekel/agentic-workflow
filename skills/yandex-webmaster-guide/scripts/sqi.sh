#!/bin/bash
# Get SQI (Site Quality Index) history
# Usage: bash scripts/sqi.sh --host https://example.com:443 [--from DATE] [--to DATE]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(default_from_date)
TO_DATE=$(default_to_date)
HOST_PARAM=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_PARAM="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
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

echo "=== SQI History ==="
echo "Host: $HOST_ID"
echo "Period: $FROM_DATE — $TO_DATE"
echo ""

response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/sqi/history?date_from=${FROM_DATE}&date_to=${TO_DATE}")
if [[ $? -ne 0 ]]; then
    echo "Error: API request failed"
    exit 1
fi

if echo "$response" | grep -q '"error_code"'; then
    echo "API Error:"
    echo "$response"
    exit 1
fi

echo "$response"
