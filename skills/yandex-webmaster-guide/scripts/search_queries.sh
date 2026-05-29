#!/bin/bash
# Get popular search queries from Yandex SERP
# Usage: bash scripts/search_queries.sh --host https://example.com:443 [--from DATE] [--to DATE] [--limit N] [--order ORDER] [--indicator INDICATORS]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(default_from_date)
TO_DATE=$(default_to_date)
LIMIT=20
ORDER="TOTAL_CLICKS"
INDICATOR="TOTAL_SHOWS,TOTAL_CLICKS,AVG_SHOW_POSITION,AVG_CLICK_POSITION"
HOST_PARAM=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_PARAM="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --order) ORDER="$2"; shift 2 ;;
        --indicator) INDICATOR="$2"; shift 2 ;;
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

echo "=== Popular Search Queries ==="
echo "Host: $HOST_ID"
echo "Period: $FROM_DATE — $TO_DATE"
echo "Order by: $ORDER"
echo "Limit: $LIMIT"
echo ""

# Build query params
PARAMS="order_by=${ORDER}&date_from=${FROM_DATE}&date_to=${TO_DATE}&limit=${LIMIT}"

# Add indicators
IFS=',' read -ra INDICATORS <<< "$INDICATOR"
for ind in "${INDICATORS[@]}"; do
    PARAMS="${PARAMS}&query_indicator=${ind}"
done

response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/search-queries/popular?${PARAMS}")
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
