#!/bin/bash
# Get traffic overview for a date range
# Usage: bash scripts/overview.sh --counter ID [--from DATE] [--to DATE]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Defaults: last 30 days
FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        *) shift ;;
    esac
done
require_counter

PARAMS="date1=${FROM_DATE}&date2=${TO_DATE}"

echo "=== Traffic Overview ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo "Counter: $YANDEX_METRIKA_COUNTER"
echo ""

# Visits, pageviews, users, bounce rate, avg duration
response=$(metrika_stat "sources_summary" "$PARAMS&limit=1")
if echo "$response" | grep -q '"errors"'; then
    echo "Error:"; echo "$response"; exit 1
fi

# Get totals
totals=$(echo "$response" | grep -o '"totals":\[[^]]*\]' | head -1)
echo "Raw totals: $totals"
echo ""

# Also get basic metrics via custom query
response2=$(metrika_custom "ym:s:visits,ym:s:pageviews,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds" "" "$PARAMS")
if echo "$response2" | grep -q '"totals"'; then
    totals2=$(echo "$response2" | grep -o '"totals":\[[^]]*\]' | head -1)
    echo "Metrics totals: $totals2"
fi
