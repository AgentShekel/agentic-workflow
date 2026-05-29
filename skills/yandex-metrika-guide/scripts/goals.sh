#!/bin/bash
# Get goals list and conversion stats
# Usage: bash scripts/goals.sh --counter ID [--from DATE] [--to DATE] [--list]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --list) LIST_ONLY=true; shift ;;
        *) shift ;;
    esac
done
require_counter

echo "=== Goals ==="
echo "Counter: $YANDEX_METRIKA_COUNTER"
echo ""

# Get goals list from Management API
echo "--- Configured Goals ---"
goals_response=$(metrika_management "goals")
echo "$goals_response"
echo ""

if [[ "$LIST_ONLY" == "true" ]]; then
    exit 0
fi

# Get conversion stats
echo "--- Conversions ($FROM_DATE — $TO_DATE) ---"
PARAMS="date1=${FROM_DATE}&date2=${TO_DATE}"
response=$(metrika_stat "conversion_rate" "$PARAMS&limit=20")
echo "$response"
