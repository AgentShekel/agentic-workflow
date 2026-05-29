#!/bin/bash
# Common functions for Yandex Webmaster API v4

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"
WEBMASTER_API="https://api.webmaster.yandex.net/v4"

# Load config
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CONFIG_FILE"
    fi

    if [[ -z "$YANDEX_WEBMASTER_TOKEN" ]]; then
        echo "Error: YANDEX_WEBMASTER_TOKEN not found."
        echo "Set in config/.env or environment. See config/README.md for instructions."
        exit 1
    fi
}

# Get user_id from API (cached for session)
# Usage: USER_ID=$(get_user_id)
get_user_id() {
    local curl_cfg="${TMPDIR:-/tmp}/yw_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_WEBMASTER_TOKEN"
CURLEOF

    local response
    response=$(curl -s -K "$curl_cfg" "${WEBMASTER_API}/user")
    local rc=$?
    rm -f "$curl_cfg"

    if [[ $rc -ne 0 ]]; then
        echo "Error: API request failed" >&2
        return 1
    fi

    if echo "$response" | grep -q '"error_code"'; then
        echo "API Error: $response" >&2
        return 1
    fi

    local user_id
    user_id=$(json_value "$response" "user_id")
    if [[ -z "$user_id" ]]; then
        echo "Error: Could not extract user_id from response: $response" >&2
        return 1
    fi

    echo "$user_id"
}

# Convert URL to Webmaster host_id format
# https://example.com:443 -> https:example.com:443
# https://example.com -> https:example.com:443
# http://example.com -> http:example.com:80
url_to_host_id() {
    local url="$1"

    # Remove trailing slash
    url="${url%/}"

    # Extract protocol
    local proto=""
    if [[ "$url" == https://* ]]; then
        proto="https"
        url="${url#https://}"
    elif [[ "$url" == http://* ]]; then
        proto="http"
        url="${url#http://}"
    else
        # Already in host_id format (e.g., https:example.com:443)
        echo "$1"
        return
    fi

    # Extract host and port
    local host="$url"
    local port=""

    if [[ "$host" == *:* ]]; then
        port="${host##*:}"
        host="${host%:*}"
    else
        if [[ "$proto" == "https" ]]; then
            port="443"
        else
            port="80"
        fi
    fi

    echo "${proto}:${host}:${port}"
}

# Resolve host: use --host param, env var, or error
# Usage: HOST_ID=$(resolve_host "$HOST_PARAM")
resolve_host() {
    local host_param="$1"

    if [[ -n "$host_param" ]]; then
        url_to_host_id "$host_param"
    elif [[ -n "$YANDEX_WEBMASTER_HOST" ]]; then
        url_to_host_id "$YANDEX_WEBMASTER_HOST"
    else
        echo "Error: --host is required (or set YANDEX_WEBMASTER_HOST in config/.env)" >&2
        return 1
    fi
}

# Make Webmaster API GET request
# Usage: webmaster_get "/user/{uid}/hosts"
webmaster_get() {
    local endpoint="$1"

    local url="${WEBMASTER_API}${endpoint}"

    local curl_cfg="${TMPDIR:-/tmp}/yw_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_WEBMASTER_TOKEN"
CURLEOF

    curl -s -K "$curl_cfg" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
}

# Make Webmaster API POST request
# Usage: webmaster_post "/user/{uid}/hosts/{hostId}/recrawl/queue" '{"url":"..."}'
webmaster_post() {
    local endpoint="$1"
    local body="$2"

    local url="${WEBMASTER_API}${endpoint}"

    local curl_cfg="${TMPDIR:-/tmp}/yw_curl_cfg_$$.txt"
    cat > "$curl_cfg" <<CURLEOF
-H "Authorization: OAuth $YANDEX_WEBMASTER_TOKEN"
-H "Content-Type: application/json"
CURLEOF

    curl -s -K "$curl_cfg" -X POST -d "$body" "$url"
    local rc=$?
    rm -f "$curl_cfg"
    return $rc
}

# Default date: 30 days ago (cross-platform)
default_from_date() {
    date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null
}

# Default date: today
default_to_date() {
    date +%Y-%m-%d
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
