#!/bin/bash
# Check position of a domain in Yandex search results (Yandex Cloud Search API v2)
# Usage:
#   bash scripts/positions.sh --domain example.com --query "search text" [--region 213] [--depth 5]
#   bash scripts/positions.sh --domain example.com --queries queries.txt [--region 213] [--depth 5] [--csv results.csv]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Defaults
DOMAIN=""
QUERY=""
QUERIES_FILE=""
REGION="225"
DEPTH=5
GROUPS_PER_PAGE=10
CSV_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --query) QUERY="$2"; shift 2 ;;
        --queries) QUERIES_FILE="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --depth) DEPTH="$2"; shift 2 ;;
        --csv) CSV_FILE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then
    echo "Error: --domain is required"
    echo "Usage: bash scripts/positions.sh --domain example.com --query \"search text\""
    exit 1
fi

if [[ -z "$QUERY" && -z "$QUERIES_FILE" ]]; then
    echo "Error: --query or --queries is required"
    exit 1
fi

# Build list of queries
queries=()
if [[ -n "$QUERY" ]]; then
    queries+=("$QUERY")
elif [[ -n "$QUERIES_FILE" ]]; then
    if [[ ! -f "$QUERIES_FILE" ]]; then
        echo "Error: queries file not found: $QUERIES_FILE"
        exit 1
    fi
    while IFS= read -r line; do
        line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$line" && ! "$line" =~ ^# ]]; then
            queries+=("$line")
        fi
    done < "$QUERIES_FILE"
fi

if [[ ${#queries[@]} -eq 0 ]]; then
    echo "Error: no queries to check"
    exit 1
fi

MAX_POSITION=$((DEPTH * GROUPS_PER_PAGE))

echo "=== Position Check ==="
echo "Domain: $DOMAIN"
echo "Region: $REGION"
echo "Depth: $DEPTH pages (top $MAX_POSITION)"
echo "Queries: ${#queries[@]}"
echo ""

if [[ -n "$CSV_FILE" ]]; then
    echo "query,position,url,region" > "$CSV_FILE"
fi

total_queries=${#queries[@]}
found_count=0
not_found_count=0

for qi in "${!queries[@]}"; do
    q="${queries[$qi]}"
    query_num=$((qi + 1))

    echo "[$query_num/$total_queries] \"$q\""

    position_found=""
    url_found=""

    for (( page=0; page < DEPTH; page++ )); do
        if [[ $page -gt 0 || $qi -gt 0 ]]; then
            rate_limit_sleep
        fi

        response=$(cloud_search "$q" "$REGION" "$GROUPS_PER_PAGE" "$page" "relevance" "moderate")

        if [[ $? -ne 0 ]]; then
            echo "  Error: API request failed on page $page"
            continue
        fi

        if xml_has_error "$response"; then
            error_msg=$(xml_error_message "$response")
            echo "  API Error: $error_msg"
            break
        fi

        result=$(find_domain_in_results "$response" "$DOMAIN" "$page" "$GROUPS_PER_PAGE")

        if [[ -n "$result" ]]; then
            position_found=$(echo "$result" | cut -d'|' -f1)
            url_found=$(echo "$result" | cut -d'|' -f2)
            break
        fi

        groups=$(xml_extract_groups "$response")
        group_count=$(echo "$groups" | grep -c '<group>' 2>/dev/null || echo 0)
        if [[ -z "$groups" ]] || [[ "$group_count" -lt "$GROUPS_PER_PAGE" ]]; then
            break
        fi
    done

    if [[ -n "$position_found" ]]; then
        echo "  Position: $position_found"
        echo "  URL: $url_found"
        found_count=$((found_count + 1))
    else
        echo "  Not found in top $MAX_POSITION"
        not_found_count=$((not_found_count + 1))
    fi
    echo ""

    if [[ -n "$CSV_FILE" ]]; then
        csv_query=$(echo "$q" | sed 's/"/""/g')
        if [[ -n "$position_found" ]]; then
            echo "\"$csv_query\",$position_found,\"$url_found\",$REGION" >> "$CSV_FILE"
        else
            echo "\"$csv_query\",not_found,,${REGION}" >> "$CSV_FILE"
        fi
    fi
done

echo "=== Summary ==="
echo "Total queries: $total_queries"
echo "Found: $found_count"
echo "Not found: $not_found_count"

if [[ -n "$CSV_FILE" ]]; then
    echo "Results saved to: $CSV_FILE"
fi
