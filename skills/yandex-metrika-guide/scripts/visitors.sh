#!/bin/bash
# Get visitor demographics and geography
# Usage: bash scripts/visitors.sh --counter ID [--from DATE] [--to DATE] [--type TYPE]
# TYPE: geo (default), age, gender

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)
TYPE="geo"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --counter) YANDEX_METRIKA_COUNTER="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --type) TYPE="$2"; shift 2 ;;
        *) shift ;;
    esac
done
require_counter

PARAMS="date1=${FROM_DATE}&date2=${TO_DATE}"

echo "=== Visitors ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo "Type: $TYPE"
echo ""

case "$TYPE" in
    geo)
        echo "--- Geography (countries) ---"
        response=$(metrika_stat "geo_country" "$PARAMS&limit=10")
        echo "$response"
        echo ""
        echo "--- Geography (regions) ---"
        response2=$(metrika_custom "ym:s:visits,ym:s:users" "ym:s:regionCity" "$PARAMS&limit=15&sort=-ym:s:visits")
        echo "$response2"
        ;;
    age)
        response=$(metrika_stat "age_gender" "$PARAMS&limit=20")
        echo "$response"
        ;;
    gender)
        response=$(metrika_custom "ym:s:visits,ym:s:users" "ym:s:gender" "$PARAMS")
        echo "$response"
        ;;
    *)
        echo "Unknown type: $TYPE (use: geo, age, gender)"
        exit 1
        ;;
esac
