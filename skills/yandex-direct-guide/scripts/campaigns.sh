#!/bin/bash
# List and manage Yandex Direct campaigns
# Usage:
#   bash scripts/campaigns.sh --action list [--status STATUS] [--limit N]
#   bash scripts/campaigns.sh --action suspend --id 12345
#   bash scripts/campaigns.sh --action resume --id 12345
#   bash scripts/campaigns.sh --action archive --id 12345
#   bash scripts/campaigns.sh --action unarchive --id 12345

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

ACTION="list"
CAMPAIGN_ID=""
STATUS_FILTER=""
LIMIT=100

while [[ $# -gt 0 ]]; do
    case "$1" in
        --action) ACTION="$2"; shift 2 ;;
        --id) CAMPAIGN_ID="$2"; shift 2 ;;
        --status) STATUS_FILTER="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

case "$ACTION" in
    list)
        echo "=== Campaigns ==="
        echo ""

        # Build SelectionCriteria
        selection='{}'
        if [[ -n "$STATUS_FILTER" ]]; then
            selection="{\"Statuses\":[\"$STATUS_FILTER\"]}"
            echo "Filter: status = $STATUS_FILTER"
            echo ""
        fi

        body="{\"method\":\"get\",\"params\":{\"SelectionCriteria\":$selection,\"FieldNames\":[\"Id\",\"Name\",\"Status\",\"State\",\"StatusPayment\",\"DailyBudget\",\"StartDate\",\"Statistics\"],\"Page\":{\"Limit\":$LIMIT}}}"

        response=$(direct_post "campaigns" "$body")
        if [[ $? -ne 0 ]]; then
            echo "Error: API request failed"
            exit 1
        fi

        if echo "$response" | grep -q '"error"'; then
            echo "API Error:"
            echo "$response"
            exit 1
        fi

        # Output raw JSON for Claude to parse and format
        echo "$response"
        ;;

    suspend)
        if [[ -z "$CAMPAIGN_ID" ]]; then
            echo "Error: --id is required for suspend action"
            exit 1
        fi

        echo "=== Suspending Campaign $CAMPAIGN_ID ==="
        body="{\"method\":\"suspend\",\"params\":{\"SelectionCriteria\":{\"Ids\":[$CAMPAIGN_ID]}}}"

        response=$(direct_post "campaigns" "$body")
        if echo "$response" | grep -q '"error"'; then
            echo "Error:"
            echo "$response"
            exit 1
        fi

        echo "Campaign $CAMPAIGN_ID suspended"
        echo "$response"
        ;;

    resume)
        if [[ -z "$CAMPAIGN_ID" ]]; then
            echo "Error: --id is required for resume action"
            exit 1
        fi

        echo "=== Resuming Campaign $CAMPAIGN_ID ==="
        body="{\"method\":\"resume\",\"params\":{\"SelectionCriteria\":{\"Ids\":[$CAMPAIGN_ID]}}}"

        response=$(direct_post "campaigns" "$body")
        if echo "$response" | grep -q '"error"'; then
            echo "Error:"
            echo "$response"
            exit 1
        fi

        echo "Campaign $CAMPAIGN_ID resumed"
        echo "$response"
        ;;

    archive)
        if [[ -z "$CAMPAIGN_ID" ]]; then
            echo "Error: --id is required for archive action"
            exit 1
        fi

        echo "=== Archiving Campaign $CAMPAIGN_ID ==="
        body="{\"method\":\"archive\",\"params\":{\"SelectionCriteria\":{\"Ids\":[$CAMPAIGN_ID]}}}"

        response=$(direct_post "campaigns" "$body")
        if echo "$response" | grep -q '"error"'; then
            echo "Error:"
            echo "$response"
            exit 1
        fi

        echo "Campaign $CAMPAIGN_ID archived"
        echo "$response"
        ;;

    unarchive)
        if [[ -z "$CAMPAIGN_ID" ]]; then
            echo "Error: --id is required for unarchive action"
            exit 1
        fi

        echo "=== Unarchiving Campaign $CAMPAIGN_ID ==="
        body="{\"method\":\"unarchive\",\"params\":{\"SelectionCriteria\":{\"Ids\":[$CAMPAIGN_ID]}}}"

        response=$(direct_post "campaigns" "$body")
        if echo "$response" | grep -q '"error"'; then
            echo "Error:"
            echo "$response"
            exit 1
        fi

        echo "Campaign $CAMPAIGN_ID unarchived"
        echo "$response"
        ;;

    *)
        echo "Unknown action: $ACTION"
        echo "Available actions: list, suspend, resume, archive, unarchive"
        exit 1
        ;;
esac
