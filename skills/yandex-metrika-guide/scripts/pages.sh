#!/bin/bash
# Get popular pages report
# Usage: bash scripts/pages.sh --counter ID [--from DATE] [--to DATE] [--limit N] [--url FILTER]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)
LIMIT=20
URL_FILTER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --url) URL_FILTER="$2"; shift 2 ;;
        *) shift ;;
    esac
done
require_counter

PARAMS="date1=${FROM_DATE}&date2=${TO_DATE}&limit=${LIMIT}"

echo "=== Popular Pages ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo ""

if [[ -n "$URL_FILTER" ]]; then
    # Filter by URL containing string
    PARAMS="${PARAMS}&filters=ym:pv:URLPath=~'${URL_FILTER}'"
    echo "Filter: URL contains '$URL_FILTER'"
    echo ""
fi

# Page views by URL
response=$(metrika_custom "ym:pv:pageviews,ym:pv:users" "ym:pv:URLPath" "$PARAMS&sort=-ym:pv:pageviews")
echo "$response"
