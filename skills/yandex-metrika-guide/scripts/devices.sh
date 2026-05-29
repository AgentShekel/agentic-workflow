#!/bin/bash
# Get device/browser/OS statistics
# Usage: bash scripts/devices.sh --counter ID [--from DATE] [--to DATE] [--type TYPE]
# TYPE: device (default), browser, os

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)
TYPE="device"

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

echo "=== Device Statistics ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo "Type: $TYPE"
echo ""

case "$TYPE" in
    device)
        response=$(metrika_stat "tech_platforms" "$PARAMS&limit=10")
        ;;
    browser)
        response=$(metrika_stat "tech_browsers" "$PARAMS&limit=15")
        ;;
    os)
        response=$(metrika_stat "tech_os" "$PARAMS&limit=10")
        ;;
    *)
        echo "Unknown type: $TYPE (use: device, browser, os)"
        exit 1
        ;;
esac

echo "$response"
