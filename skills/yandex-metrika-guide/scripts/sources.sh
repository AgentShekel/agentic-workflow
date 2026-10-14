#!/bin/bash
# Get traffic sources breakdown
# Usage: bash scripts/sources.sh --counter ID [--from DATE] [--to DATE] [--limit N]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)
LIMIT=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) shift ;;
    esac
done
require_counter

PARAMS="date1=${FROM_DATE}&date2=${TO_DATE}&limit=${LIMIT}"

echo "=== Traffic Sources ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo ""

# Source summary
echo "--- By source type ---"
response=$(metrika_stat "sources_summary" "$PARAMS")
echo "$response"
echo ""

# Search engines
echo "--- By search engine ---"
response=$(metrika_stat "sources_search_engines" "$PARAMS")
echo "$response"
echo ""

# Referral sites
echo "--- By referral sites ---"
response=$(metrika_stat "sources_sites" "$PARAMS")
echo "$response"
