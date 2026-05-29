#!/bin/bash
# Common functions for Yandex Direct API v5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"
DIRECT_API="https://api.direct.yandex.com/json/v5"
DIRECT_SANDBOX_API="https://api-sandbox.direct.yandex.com/json/v5"

# Load config
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CONFIG_FILE"
    fi

    if [[ -z "$YANDEX_DIRECT_TOKEN" ]]; then
        echo "Error: YANDEX_DIRECT_TOKEN not found."
        echo "Set in config/.env or environment. See config/README.md for instructions."
        exit 1
    fi

    # Use sandbox if configured
    if [[ "$YANDEX_DIRECT_SANDBOX" == "true" ]]; then
        DIRECT_API="$DIRECT_SANDBOX_API"
        echo "(Using sandbox API)"
    fi
}

# Get base URL (for use after load_config)
get_api_url() {
    echo "$DIRECT_API"
}

# Make Direct API POST request
# Usage: direct_post "service" '{"method":"get","params":{...}}'
direct_post() {
    local service="$1"
    local body="$2"

    local url="${DIRECT_API}/${service}"

    local curl_cfg="${TMPDIR:-/tmp}/yd_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: Bearer $YANDEX_DIRECT_TOKEN"
-H "Content-Type: application/json"
-H "Accept-Language: ru"
CURLEOF

    # Add Client-Login header for agency accounts
    if [[ -n "$YANDEX_DIRECT_LOGIN" ]]; then
        echo "-H \"Client-Login: $YANDEX_DIRECT_LOGIN\"" >> "$curl_cfg"
    fi

    curl -s -K "$curl_cfg" -X POST -d "$body" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
}

# Make Direct Reports API request with async handling
# Usage: direct_report '{"params":{...}}'
# Returns TSV data on success
direct_report() {
    local body="$1"
    local max_retries=30
    local retry_delay=5

    local url="${DIRECT_API}/reports"

    local curl_cfg="${TMPDIR:-/tmp}/yd_report_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: Bearer $YANDEX_DIRECT_TOKEN"
-H "Content-Type: application/json"
-H "Accept-Language: ru"
-H "returnMoneyInMicros: true"
-H "skipReportHeader: true"
-H "skipReportSummary: true"
CURLEOF

    if [[ -n "$YANDEX_DIRECT_LOGIN" ]]; then
        echo "-H \"Client-Login: $YANDEX_DIRECT_LOGIN\"" >> "$curl_cfg"
    fi

    local attempt=0
    while [[ $attempt -lt $max_retries ]]; do
        local http_code_file="${TMPDIR:-/tmp}/yd_http_code_$$.txt"
        local response
        response=$(curl -s -K "$curl_cfg" -X POST -d "$body" -w "\n%{http_code}" "$url")
        local rc=$?

        # Extract HTTP code from last line
        local http_code
        http_code=$(echo "$response" | tail -1)
        local body_response
        body_response=$(echo "$response" | sed '$d')

        case "$http_code" in
            200)
                # Report ready
                rm -f "$curl_cfg" "$http_code_file"
                echo "$body_response"
                return 0
                ;;
            201)
                # Report is being built offline
                echo "Report is being built (attempt $((attempt + 1))/$max_retries)..." >&2
                sleep "$retry_delay"
                ;;
            202)
                # Report is being generated
                echo "Report is being generated (attempt $((attempt + 1))/$max_retries)..." >&2
                sleep "$retry_delay"
                ;;
            *)
                # Error
                rm -f "$curl_cfg" "$http_code_file"
                echo "Error (HTTP $http_code):" >&2
                echo "$body_response" >&2
                return 1
                ;;
        esac

        attempt=$((attempt + 1))
    done

    rm -f "$curl_cfg"
    echo "Error: Report generation timed out after $max_retries attempts" >&2
    return 1
}

# Convert money from micros (1 ruble = 1000000 micros) to rubles
# Usage: money_from_micros "1500000" -> "1.50"
money_from_micros() {
    local micros="$1"
    if [[ -z "$micros" || "$micros" == "null" || "$micros" == "--" ]]; then
        echo "0.00"
        return
    fi
    # Use awk for floating point division
    echo "$micros" | awk '{printf "%.2f", $1 / 1000000}'
}

# Extract JSON value (no jq dependency)
json_value() {
    local json="$1"
    local key="$2"
    echo "$json" | grep -o "\"$key\":[^,}]*" | head -1 | sed 's/.*://' | tr -d '"[:space:]'
}

json_string() {
    local json="$1"
    local key="$2"
    echo "$json" | grep -o "\"$key\":\"[^\"]*\"" | head -1 | sed 's/.*:"//' | tr -d '"'
}

# Extract JSON array (simple - returns content between [ and ])
json_array() {
    local json="$1"
    local key="$2"
    echo "$json" | grep -o "\"$key\":\[[^]]*\]" | head -1 | sed "s/\"$key\"://"
}

format_number() {
    local num="$1"
    printf "%'d" "$num" 2>/dev/null || echo "$num"
}

# Parse TSV report and display as formatted table
# Usage: echo "$tsv_data" | format_tsv_report
format_tsv_report() {
    local input
    input=$(cat)

    if [[ -z "$input" ]]; then
        echo "(empty report)"
        return
    fi

    # First line is header
    local header
    header=$(echo "$input" | head -1)

    # Detect money columns by name (Cost, AvgCpc, CostPerConversion, AvgCpa, Revenue)
    local money_cols=""
    local col_idx=0
    IFS=$'\t' read -ra hdr_arr <<< "$header"
    for col_name in "${hdr_arr[@]}"; do
        case "$col_name" in
            Cost|AvgCpc|CostPerConversion|AvgCpa|Revenue|AvgCpm)
                money_cols="$money_cols $col_idx"
                ;;
        esac
        col_idx=$((col_idx + 1))
    done

    # Print header
    echo "$header" | tr '\t' ' | ' | sed 's/^/| /;s/$/ |/'
    # Print separator
    echo "$header" | awk -F'\t' '{for(i=1;i<=NF;i++) printf "| --- "; print "|"}'

    # Print data rows, converting money columns from micros to rubles
    echo "$input" | tail -n +2 | while IFS= read -r line; do
        if [[ -z "$line" ]]; then
            continue
        fi
        IFS=$'\t' read -ra cols <<< "$line"
        local output=""
        for i in "${!cols[@]}"; do
            local val="${cols[$i]}"
            # Check if this column is a money column
            if echo "$money_cols" | grep -qw "$i"; then
                val=$(money_from_micros "$val")
                val="${val} RUB"
            fi
            if [[ -z "$output" ]]; then
                output="| $val"
            else
                output="$output | $val"
            fi
        done
        echo "$output |"
    done
}

# Default dates helper (last 30 days)
default_from_date() {
    date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null
}

default_to_date() {
    date +%Y-%m-%d
}
