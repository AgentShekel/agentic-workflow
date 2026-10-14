#!/bin/bash
# List keywords for a campaign or ad group
# Usage:
#   bash scripts/keywords.sh --campaign 12345 [--limit 50]
#   bash scripts/keywords.sh --adgroup 67890 [--limit 50]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

CAMPAIGN_ID=""
ADGROUP_ID=""
LIMIT=100

while [[ $# -gt 0 ]]; do
    case "$1" in
        --campaign) CAMPAIGN_ID="$2"; shift 2 ;;
        --adgroup) ADGROUP_ID="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "=== Keywords ==="
echo ""

# Build SelectionCriteria
if [[ -n "$CAMPAIGN_ID" ]]; then
    selection="{\"CampaignIds\":[$CAMPAIGN_ID]}"
    echo "Campaign: $CAMPAIGN_ID"
elif [[ -n "$ADGROUP_ID" ]]; then
    selection="{\"AdGroupIds\":[$ADGROUP_ID]}"
    echo "Ad Group: $ADGROUP_ID"
else
    echo "Error: specify --campaign or --adgroup"
    echo "Usage:"
    echo "  bash scripts/keywords.sh --campaign 12345"
    echo "  bash scripts/keywords.sh --adgroup 67890"
    exit 1
fi

echo "Limit: $LIMIT"
echo ""

body="{\"method\":\"get\",\"params\":{\"SelectionCriteria\":$selection,\"FieldNames\":[\"Id\",\"Keyword\",\"AdGroupId\",\"CampaignId\",\"Bid\",\"ContextBid\",\"Status\",\"State\",\"StatusClarification\"],\"Page\":{\"Limit\":$LIMIT}}}"

response=$(direct_post "keywords" "$body")
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
