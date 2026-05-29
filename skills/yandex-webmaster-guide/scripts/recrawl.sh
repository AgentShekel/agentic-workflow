#!/bin/bash
# Submit URL for recrawl or check recrawl quota
# Usage:
#   bash scripts/recrawl.sh --host https://example.com:443 --url https://example.com/page
#   bash scripts/recrawl.sh --host https://example.com:443 --quota

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

HOST_PARAM=""
RECRAWL_URL=""
SHOW_QUOTA=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_PARAM="$2"; shift 2 ;;
        --url) RECRAWL_URL="$2"; shift 2 ;;
        --quota) SHOW_QUOTA=true; shift ;;
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

echo "=== Recrawl ==="
echo "Host: $HOST_ID"
echo ""

if [[ "$SHOW_QUOTA" == "true" ]]; then
    echo "--- Recrawl Quota ---"
    response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/recrawl/quota")
    if echo "$response" | grep -q '"error_code"'; then
        echo "API Error:"; echo "$response"; exit 1
    fi
    echo "$response"
    exit 0
fi

if [[ -z "$RECRAWL_URL" ]]; then
    # No URL specified — show quota by default
    echo "--- Recrawl Quota ---"
    response=$(webmaster_get "/user/${USER_ID}/hosts/${HOST_ID}/recrawl/quota")
    if echo "$response" | grep -q '"error_code"'; then
        echo "API Error:"; echo "$response"; exit 1
    fi
    echo "$response"
    echo ""
    echo "To submit a URL for recrawl, use: --url <URL>"
    exit 0
fi

# Submit URL for recrawl
echo "--- Submitting URL for recrawl ---"
echo "URL: $RECRAWL_URL"
echo ""

body="{\"url\":\"${RECRAWL_URL}\"}"
response=$(webmaster_post "/user/${USER_ID}/hosts/${HOST_ID}/recrawl/queue" "$body")
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
echo ""
echo "URL submitted for recrawl."
