#!/bin/bash
# Common functions for Yandex Cloud Search API v2
# Migrated from old XML API (xml.yandex.ru) to Yandex Cloud gateway

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"
CACHE_DIR="$SCRIPT_DIR/../cache"
SEARCH_API="https://searchapi.api.cloud.yandex.net/v2/web/searchAsync"
OPERATIONS_API="https://operation.api.cloud.yandex.net/operations"

# Load config
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CONFIG_FILE"
    fi

    if [[ -z "$YANDEX_SEARCH_API_KEY" ]]; then
        echo "Error: YANDEX_SEARCH_API_KEY not found."
        echo "Set in config/.env or environment. Get key at console.yandex.cloud"
        exit 1
    fi

    if [[ -z "$YANDEX_CLOUD_FOLDER_ID" ]]; then
        echo "Error: YANDEX_CLOUD_FOLDER_ID not found."
        echo "Set in config/.env or environment."
        exit 1
    fi
}

# Escape string for JSON value
json_escape() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\t'/\\t}"
    echo "$str"
}

# Make async search request and wait for XML results
# Usage: xml=$(cloud_search "query" "region" "limit" "page" "sort" "filter")
cloud_search() {
    local query="$1"
    local region="${2:-225}"
    local limit="${3:-10}"
    local page="${4:-0}"
    local sort="${5:-relevance}"
    local filter="${6:-moderate}"

    if [[ -z "$query" ]]; then
        echo "Error: query is required" >&2
        return 1
    fi

    # Map sort
    local sort_mode="SORT_MODE_BY_RELEVANCE"
    if [[ "$sort" == "time" || "$sort" == "tm" ]]; then
        sort_mode="SORT_MODE_BY_TIME"
    fi

    # Map filter to family mode
    local family_mode="FAMILY_MODE_MODERATE"
    case "$filter" in
        none) family_mode="FAMILY_MODE_NONE" ;;
        strict) family_mode="FAMILY_MODE_STRICT" ;;
    esac

    local escaped_query
    escaped_query=$(json_escape "$query")

    # Build JSON body via temp file (avoids shell escaping issues)
    local tmpfile="${TMPDIR:-/tmp}/yc_search_$$.json"
    cat > "$tmpfile" <<JSONEOF
{
  "query": {
    "searchType": "SEARCH_TYPE_RU",
    "queryText": "${escaped_query}",
    "familyMode": "${family_mode}",
    "page": "${page}",
    "fixTypoMode": "FIX_TYPO_MODE_ON"
  },
  "sortSpec": {
    "sortMode": "${sort_mode}",
    "sortOrder": "SORT_ORDER_DESC"
  },
  "groupSpec": {
    "groupMode": "GROUP_MODE_DEEP",
    "groupsOnPage": "${limit}",
    "docsInGroup": "1"
  },
  "maxPassages": "2",
  "region": "${region}",
  "l10N": "LOCALIZATION_RU",
  "folderId": "${YANDEX_CLOUD_FOLDER_ID}",
  "responseFormat": "FORMAT_XML"
}
JSONEOF

    # Submit async request
    local response
    response=$(curl -s -X POST "$SEARCH_API" \
        -H "Authorization: Api-Key $YANDEX_SEARCH_API_KEY" \
        -H "Content-Type: application/json" \
        -d "@$tmpfile")
    rm -f "$tmpfile"

    # Helper: extract JSON string value by key (handles spaces around colon)
    _json_val() {
        local json="$1" key="$2"
        echo "$json" | sed -n 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1
    }

    # Check for immediate error (gRPC-style errors have "code" and "message")
    if echo "$response" | grep -q '"code"'; then
        local err_msg
        err_msg=$(_json_val "$response" "message")
        echo "API Error: ${err_msg:-$response}" >&2
        return 1
    fi

    # Get operation ID
    local op_id
    op_id=$(_json_val "$response" "id")

    if [[ -z "$op_id" ]]; then
        echo "Error: no operation ID. Response: $response" >&2
        return 1
    fi

    # Poll for completion
    local max_attempts=30
    local attempt=0
    while [[ $attempt -lt $max_attempts ]]; do
        sleep 1

        local status
        status=$(curl -s "$OPERATIONS_API/$op_id" \
            -H "Authorization: Api-Key $YANDEX_SEARCH_API_KEY")

        # Check if done
        if echo "$status" | grep -qE '"done"[[:space:]]*:[[:space:]]*true'; then
            # Extract rawData (base64-encoded XML)
            local raw_data
            raw_data=$(_json_val "$status" "rawData")

            if [[ -n "$raw_data" ]]; then
                echo "$raw_data" | base64 -d 2>/dev/null || echo "$raw_data"
                return 0
            fi

            # If no rawData, return full response for debugging
            echo "$status"
            return 0
        fi

        # Check for error
        if echo "$status" | grep -q '"error"'; then
            local err_msg
            err_msg=$(_json_val "$status" "message")
            echo "Operation error: ${err_msg:-$status}" >&2
            return 1
        fi

        attempt=$((attempt + 1))
    done

    echo "Error: timeout waiting for search results (${max_attempts}s)" >&2
    return 1
}

# --- XML parsing functions (same XML format as old API) ---

# Extract value from XML tag
xml_extract() {
    local xml="$1"
    local tag="$2"
    echo "$xml" | sed -n 's/.*<'"$tag"'[^>]*>\([^<]*\)<.*/\1/p' | head -1
}

# Extract all values from XML tag
xml_extract_all() {
    local xml="$1"
    local tag="$2"
    echo "$xml" | sed -n 's/.*<'"$tag"'[^>]*>\([^<]*\)<.*/\1/p'
}

# Extract all <group> blocks from XML response
xml_extract_groups() {
    local xml="$1"
    echo "$xml" | tr '\n' ' ' | sed 's/<group>/\n<group>/g' | grep -o '<group>.*</group>'
}

# Extract URL from a group block
group_url() {
    local group="$1"
    echo "$group" | sed -n 's/.*<url>\([^<]*\)<.*/\1/p' | head -1
}

# Extract domain from a group block
group_domain() {
    local group="$1"
    echo "$group" | sed -n 's/.*<domain>\([^<]*\)<.*/\1/p' | head -1
}

# Extract title from a group block (strip inner HTML tags like <hlword>)
group_title() {
    local group="$1"
    # Extract everything between <title> and </title>, then strip inner tags
    echo "$group" | sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' | head -1 | sed 's/<[^>]*>//g'
}

# Extract headline/snippet from a group block
group_headline() {
    local group="$1"
    local headline
    headline=$(echo "$group" | sed -n 's/.*<headline>\(.*\)<\/headline>.*/\1/p' | head -1 | sed 's/<[^>]*>//g')
    if [[ -z "$headline" ]]; then
        headline=$(echo "$group" | sed -n 's/.*<passage>\(.*\)<\/passage>.*/\1/p' | head -1 | sed 's/<[^>]*>//g')
    fi
    echo "$headline"
}

# Extract total found count
xml_total_found() {
    local xml="$1"
    echo "$xml" | sed -n 's/.*<found[^>]*>\([0-9]*\)<.*/\1/p' | head -1
}

# Check for API error in XML response
xml_has_error() {
    local xml="$1"
    echo "$xml" | grep -q '<error'
}

# Extract error message
xml_error_message() {
    local xml="$1"
    echo "$xml" | grep -oP '<error[^>]*>\K[^<]*' | head -1
}

# Parse results into numbered output: POSITION|URL|DOMAIN|TITLE|SNIPPET
parse_results() {
    local xml="$1"
    local page="${2:-0}"
    local groups_per_page="${3:-10}"

    local groups
    groups=$(xml_extract_groups "$xml")

    if [[ -z "$groups" ]]; then
        echo "No results found."
        return 1
    fi

    local position=0
    while IFS= read -r group; do
        position=$((position + 1))
        local abs_position=$(( page * groups_per_page + position ))
        local url domain title snippet
        url=$(group_url "$group")
        domain=$(group_domain "$group")
        title=$(group_title "$group")
        snippet=$(group_headline "$group")
        echo "${abs_position}|${url}|${domain}|${title}|${snippet}"
    done <<< "$groups"
}

# Check if domain appears in search results
# Returns: "position|url" or empty
find_domain_in_results() {
    local xml="$1"
    local target_domain="$2"
    local page="${3:-0}"
    local groups_per_page="${4:-10}"

    local groups
    groups=$(xml_extract_groups "$xml")
    [[ -z "$groups" ]] && return 1

    local position=0
    while IFS= read -r group; do
        position=$((position + 1))
        local abs_position=$(( page * groups_per_page + position ))
        local domain url
        domain=$(group_domain "$group")
        url=$(group_url "$group")

        if [[ "$domain" == "$target_domain" || "$domain" == *".${target_domain}" ]]; then
            echo "${abs_position}|${url}"
            return 0
        fi
    done <<< "$groups"

    return 1
}

# Rate limiting between requests
rate_limit_sleep() {
    sleep 1
}
