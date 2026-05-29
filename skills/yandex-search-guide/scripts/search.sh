#!/bin/bash
# Search Yandex and show results (Yandex Cloud Search API v2)
# Usage: bash scripts/search.sh --query "search text" [--region 213] [--limit 10] [--page 0] [--sort relevancy] [--filter moderate]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Defaults
QUERY=""
REGION="225"
LIMIT="10"
PAGE="0"
SORT="relevance"
FILTER="moderate"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --query) QUERY="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --page) PAGE="$2"; shift 2 ;;
        --sort)
            case "$2" in
                time|tm) SORT="time" ;;
                *) SORT="relevance" ;;
            esac
            shift 2 ;;
        --filter) FILTER="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$QUERY" ]]; then
    echo "Error: --query is required"
    echo "Usage: bash scripts/search.sh --query \"search text\" [--region 213] [--limit 10]"
    exit 1
fi

if [[ "$LIMIT" -gt 100 ]]; then
    echo "Warning: limit capped at 100"
    LIMIT=100
fi

echo "=== Yandex Search Results ==="
echo "Query: $QUERY"
echo "Region: $REGION"
echo "Page: $PAGE (results $((PAGE * LIMIT + 1))-$((PAGE * LIMIT + LIMIT)))"
echo "Sort: $([ "$SORT" = "time" ] && echo "by time" || echo "by relevancy")"
echo "Filter: $FILTER"
echo ""

response=$(cloud_search "$QUERY" "$REGION" "$LIMIT" "$PAGE" "$SORT" "$FILTER")

if [[ $? -ne 0 ]]; then
    echo "Error: API request failed"
    exit 1
fi

if xml_has_error "$response"; then
    error_msg=$(xml_error_message "$response")
    echo "API Error: $error_msg"
    exit 1
fi

total=$(xml_total_found "$response")
echo "Total found: ${total:-unknown}"
echo ""

groups=$(xml_extract_groups "$response")

if [[ -z "$groups" ]]; then
    echo "No results found."
    exit 0
fi

position=0
while IFS= read -r group; do
    position=$((position + 1))
    abs_position=$(( PAGE * LIMIT + position ))

    url=$(group_url "$group")
    domain=$(group_domain "$group")
    title=$(group_title "$group")
    snippet=$(group_headline "$group")

    echo "--- #${abs_position} ---"
    echo "  Title:   $title"
    echo "  URL:     $url"
    echo "  Domain:  $domain"
    if [[ -n "$snippet" ]]; then
        echo "  Snippet: $snippet"
    fi
    echo ""
done <<< "$groups"

echo "--- End of page $PAGE (showed $position results) ---"
