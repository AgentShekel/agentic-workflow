#!/bin/bash
# Check Yandex Webmaster API connection and show user info
# Usage: bash scripts/quota.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

echo "=== Yandex Webmaster API Check ==="
echo ""

# Get user_id
USER_ID=$(get_user_id)
if [[ $? -ne 0 ]]; then
    echo "Error: Could not get user_id"
    exit 1
fi

echo "User ID: $USER_ID"
echo ""

# List hosts
echo "--- Registered Hosts ---"
response=$(webmaster_get "/user/${USER_ID}/hosts")
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
echo "Connection OK"
