#!/bin/sh
# Get totalCount from Yandex Wordstat API for an OR-query.
# Thin wrapper: reads token from config/.env, delegates to missed_demand.py.
#
# Usage:
#   bash scripts/query_total.sh --phrase "(купить|заказать) телефон ретро" [--regions "213"]
#
# Output: JSON {"total_count": N, "query": "..."} or {"error": "...", "query": "..."}

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"

# Load token (same pattern as top_requests.sh)
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
fi

if [ -z "$YANDEX_WORDSTAT_TOKEN" ]; then
    echo "Error: YANDEX_WORDSTAT_TOKEN not found."
    echo "Set in config/.env or environment. See config/README.md."
    exit 1
fi

# Parse arguments
PHRASE=""
REGIONS=""

while [ $# -gt 0 ]; do
    case $1 in
        --phrase|-p) PHRASE="$2"; shift 2 ;;
        --regions|-r) REGIONS="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$PHRASE" ]; then
    echo "Usage: query_total.sh --phrase \"(a|b) query\" [--regions \"213\"]"
    echo ""
    echo "Options:"
    echo "  --phrase, -p   Search phrase with operators and minus-words (required)"
    echo "  --regions, -r  Region IDs, comma-separated (optional)"
    echo ""
    echo "Output: JSON with total_count"
    exit 1
fi

# Delegate to Python
uv run --script "$SCRIPT_DIR/missed_demand.py" query-total \
    --token "$YANDEX_WORDSTAT_TOKEN" \
    --phrase "$PHRASE" \
    ${REGIONS:+--regions "$REGIONS"}
