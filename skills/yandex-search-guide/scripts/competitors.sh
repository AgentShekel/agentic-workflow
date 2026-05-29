#!/bin/bash
# Find competitors for a query - who ranks in top results (Yandex Cloud Search API v2)
# Usage: bash scripts/competitors.sh --query "search text" [--region 213] [--limit 10]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Defaults
QUERY=""
REGION="225"
LIMIT="10"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --query) QUERY="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$QUERY" ]]; then
    echo "Error: --query is required"
    echo "Usage: bash scripts/competitors.sh --query \"search text\" [--region 213]"
    exit 1
fi

echo "=== Competitors Analysis ==="
echo "Query: $QUERY"
echo "Region: $REGION"
echo "Top: $LIMIT"
echo ""

response=$(cloud_search "$QUERY" "$REGION" "$LIMIT" "0" "relevance" "moderate")

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

printf "%-4s  %-30s  %-60s  %s\n" "Pos" "Domain" "URL" "Title"
printf "%-4s  %-30s  %-60s  %s\n" "---" "------------------------------" "------------------------------------------------------------" "-----"

position=0
declare -A domain_counts

while IFS= read -r group; do
    position=$((position + 1))

    url=$(group_url "$group")
    domain=$(group_domain "$group")
    title=$(group_title "$group")

    display_domain="${domain:0:30}"
    display_url="${url:0:60}"
    display_title="${title:0:80}"

    printf "%-4s  %-30s  %-60s  %s\n" "$position" "$display_domain" "$display_url" "$display_title"

    if [[ -n "$domain" ]]; then
        current=${domain_counts[$domain]:-0}
        domain_counts[$domain]=$((current + 1))
    fi
done <<< "$groups"

echo ""
echo "=== Unique Domains ==="
echo ""

for domain in "${!domain_counts[@]}"; do
    echo "${domain_counts[$domain]} $domain"
done | sort -rn | while read -r count domain; do
    if [[ "$count" -gt 1 ]]; then
        echo "  $domain ($count results)"
    else
        echo "  $domain"
    fi
done

echo ""
echo "Total unique domains: ${#domain_counts[@]}"
