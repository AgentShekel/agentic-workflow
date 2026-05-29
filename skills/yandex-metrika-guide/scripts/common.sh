#!/bin/bash
# Common functions for Yandex Metrika API

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"
METRIKA_API="https://api-metrika.yandex.net"

# Load config
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CONFIG_FILE"
    fi

    if [[ -z "$YANDEX_METRIKA_TOKEN" ]]; then
        echo "Error: YANDEX_METRIKA_TOKEN not found."
        echo "Set in config/.env or environment. See config/README.md for instructions."
        exit 1
    fi
}

# Require counter — call after parsing args that may set YANDEX_METRIKA_COUNTER via --counter
require_counter() {
    if [[ -z "$YANDEX_METRIKA_COUNTER" ]]; then
        echo "Error: Counter ID not specified."
        echo "Pass --counter <ID> or set YANDEX_METRIKA_COUNTER in config/.env"
        exit 1
    fi
}

# Make Metrika Stat API request (GET)
# Usage: metrika_stat "preset" "extra_params"
metrika_stat() {
    local preset="$1"
    local extra="$2"

    local url="${METRIKA_API}/stat/v1/data?id=${YANDEX_METRIKA_COUNTER}&preset=${preset}"
    if [[ -n "$extra" ]]; then
        url="${url}&${extra}"
    fi

    local curl_cfg="${TMPDIR:-/tmp}/ym_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_METRIKA_TOKEN"
-H "Content-Type: application/x-yandex-lang"
CURLEOF

    curl -s -K "$curl_cfg" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
}

# Make Metrika Stat API request with custom dimensions/metrics
# Usage: metrika_custom "metrics" "dimensions" "extra_params"
metrika_custom() {
    local metrics="$1"
    local dimensions="$2"
    local extra="$3"

    local url="${METRIKA_API}/stat/v1/data?id=${YANDEX_METRIKA_COUNTER}&metrics=${metrics}"
    if [[ -n "$dimensions" ]]; then
        url="${url}&dimensions=${dimensions}"
    fi
    if [[ -n "$extra" ]]; then
        url="${url}&${extra}"
    fi

    local curl_cfg="${TMPDIR:-/tmp}/ym_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_METRIKA_TOKEN"
CURLEOF

    curl -s -K "$curl_cfg" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
}

# Make Metrika Management API request
# Usage: metrika_management "endpoint"
metrika_management() {
    local endpoint="$1"

    local url="${METRIKA_API}/management/v1/counter/${YANDEX_METRIKA_COUNTER}/${endpoint}"

    local curl_cfg="${TMPDIR:-/tmp}/ym_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_METRIKA_TOKEN"
CURLEOF

    curl -s -K "$curl_cfg" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
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

format_number() {
    local num="$1"
    printf "%'d" "$num" 2>/dev/null || echo "$num"
}
