#!/bin/bash
# Get site diagnostics — problems found by Yandex crawler
# Usage: bash scripts/diagnostics.sh --host https://example.com:443

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

HOST_PARAM=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_PARAM="$2"; shift 2 ;;
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

echo "=== Site Diagnostics ==="
echo "Host: $HOST_ID"
echo ""

response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/diagnostics")
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
