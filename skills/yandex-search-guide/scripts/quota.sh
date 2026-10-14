#!/bin/bash
# Check Yandex Cloud Search API v2 connection with a test query
# Usage: bash scripts/quota.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

echo "=== Yandex Cloud Search API v2 Check ==="
echo "Folder: $YANDEX_CLOUD_FOLDER_ID"
echo ""

# Make a simple test query
echo "Running test query: 'test'..."
response=$(cloud_search "test" "225" "1" "0")

if [[ $? -ne 0 ]]; then
    echo "Error: API request failed"
    echo "$response"
    exit 1
fi

# Check for XML errors
if xml_has_error "$response"; then
    error_msg=$(xml_error_message "$response")
    echo "API Error: $error_msg"
    exit 1
fi

# Check for valid response
total=$(xml_total_found "$response")

if [[ -z "$total" ]]; then
    echo "Warning: Could not parse XML response. Raw output (first 500 chars):"
    echo "$response" | head -c 500
    exit 1
fi

echo "Total results found: $total"
echo ""

# Show first result as proof
groups=$(xml_extract_groups "$response")
if [[ -n "$groups" ]]; then
    first_group=$(echo "$groups" | head -1)
    first_url=$(group_url "$first_group")
    first_title=$(group_title "$first_group")
    echo "First result:"
    echo "  Title: $first_title"
    echo "  URL: $first_url"
fi

echo ""
echo "Connection OK"
