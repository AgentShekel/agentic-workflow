#!/bin/bash
# Check Yandex Direct API connection and account info
# Usage: bash scripts/quota.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

echo "=== Yandex Direct API Check ==="
echo ""

# Get client info via Clients.get
body='{"method":"get","params":{"FieldNames":["Login","ClientId","ClientInfo","Currency","Grants","Notification","Phone","DateRange","AccountQuality","Archived","Representatives"]}}'

response=$(direct_post "clients" "$body")
if [[ $? -ne 0 ]]; then
    echo "Error: API request failed"
    exit 1
fi

# Check for errors
if echo "$response" | grep -q '"error"'; then
    echo "API Error:"
    echo "$response"
    exit 1
fi

# Parse response
login=$(json_string "$response" "Login")
client_id=$(json_value "$response" "ClientId")
currency=$(json_string "$response" "Currency")
client_info=$(json_string "$response" "ClientInfo")

echo "Login: $login"
echo "Client ID: $client_id"
echo "Currency: $currency"
if [[ -n "$client_info" ]]; then
    echo "Info: $client_info"
fi

if [[ -n "$YANDEX_DIRECT_LOGIN" ]]; then
    echo "Agency login (Client-Login): $YANDEX_DIRECT_LOGIN"
fi

echo ""
echo "Connection OK"
