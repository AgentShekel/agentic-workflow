#!/bin/bash
# Generate Yandex Direct statistics reports
# Usage:
#   bash scripts/report.sh --type campaign --from 2025-01-01 --to 2025-01-31
#   bash scripts/report.sh --type ad --from 2025-01-01 --to 2025-01-31
#   bash scripts/report.sh --type keyword --from 2025-01-01 --to 2025-01-31
#   bash scripts/report.sh --type search_queries --from 2025-01-01 --to 2025-01-31 --campaign 12345
#   bash scripts/report.sh --type custom --from 2025-01-01 --to 2025-01-31 --fields "Date,CampaignName,Impressions,Clicks,Cost,Ctr" --csv report.csv

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

# Defaults
REPORT_TYPE="campaign"
FROM_DATE=$(default_from_date)
TO_DATE=$(default_to_date)
CAMPAIGN_ID=""
CUSTOM_FIELDS=""
CSV_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --type) REPORT_TYPE="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        --campaign) CAMPAIGN_ID="$2"; shift 2 ;;
        --fields) CUSTOM_FIELDS="$2"; shift 2 ;;
        --csv) CSV_FILE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Generate unique report name to avoid conflicts
REPORT_NAME="claude_report_${REPORT_TYPE}_$(date +%s)"

# Build SelectionCriteria
SELECTION_FILTER=""
if [[ -n "$CAMPAIGN_ID" ]]; then
    SELECTION_FILTER=",\"Filter\":[{\"Field\":\"CampaignId\",\"Operator\":\"EQUALS\",\"Values\":[\"$CAMPAIGN_ID\"]}]"
fi

# Determine report parameters based on type
case "$REPORT_TYPE" in
    campaign)
        REPORT_TYPE_API="CAMPAIGN_PERFORMANCE_REPORT"
        FIELDS="CampaignName,CampaignId,Impressions,Clicks,Cost,Ctr,AvgCpc,Conversions,CostPerConversion"
        echo "=== Campaign Performance Report ==="
        ;;
    ad)
        REPORT_TYPE_API="AD_PERFORMANCE_REPORT"
        FIELDS="AdGroupName,AdGroupId,AdId,Impressions,Clicks,Cost,Ctr,AvgCpc,Conversions"
        echo "=== Ad Performance Report ==="
        ;;
    keyword)
        REPORT_TYPE_API="CRITERIA_PERFORMANCE_REPORT"
        FIELDS="CampaignName,AdGroupName,CriteriaId,Criteria,Impressions,Clicks,Cost,Ctr,AvgCpc,AvgImpressionPosition"
        echo "=== Keyword Performance Report ==="
        ;;
    search_queries)
        REPORT_TYPE_API="SEARCH_QUERY_PERFORMANCE_REPORT"
        FIELDS="CampaignName,AdGroupName,Query,Impressions,Clicks,Cost,Ctr,AvgCpc"
        echo "=== Search Query Performance Report ==="
        ;;
    custom)
        REPORT_TYPE_API="CUSTOM_REPORT"
        if [[ -z "$CUSTOM_FIELDS" ]]; then
            echo "Error: --fields is required for custom report type"
            echo "Example: --fields \"Date,CampaignName,Impressions,Clicks,Cost,Ctr\""
            exit 1
        fi
        FIELDS="$CUSTOM_FIELDS"
        echo "=== Custom Report ==="
        ;;
    *)
        echo "Unknown report type: $REPORT_TYPE"
        echo "Available types: campaign, ad, keyword, search_queries, custom"
        exit 1
        ;;
esac

echo "Period: $FROM_DATE — $TO_DATE"
if [[ -n "$CAMPAIGN_ID" ]]; then
    echo "Campaign filter: $CAMPAIGN_ID"
fi
echo "Fields: $FIELDS"
echo ""

# Build FieldNames JSON array from comma-separated string
FIELDS_JSON=""
IFS=',' read -ra FIELD_ARR <<< "$FIELDS"
for field in "${FIELD_ARR[@]}"; do
    field=$(echo "$field" | tr -d '[:space:]')
    if [[ -z "$FIELDS_JSON" ]]; then
        FIELDS_JSON="\"$field\""
    else
        FIELDS_JSON="$FIELDS_JSON,\"$field\""
    fi
done

# Build report request body
body="{\"params\":{\"SelectionCriteria\":{\"DateFrom\":\"$FROM_DATE\",\"DateTo\":\"$TO_DATE\"$SELECTION_FILTER},\"FieldNames\":[$FIELDS_JSON],\"ReportName\":\"$REPORT_NAME\",\"ReportType\":\"$REPORT_TYPE_API\",\"DateRangeType\":\"CUSTOM_DATE\",\"Format\":\"TSV\",\"IncludeVAT\":\"YES\"}}"

echo "Generating report..."
echo ""

# Send report request with async handling
report_data=$(direct_report "$body")
rc=$?

if [[ $rc -ne 0 ]]; then
    echo "Error generating report"
    exit 1
fi

if [[ -z "$report_data" ]]; then
    echo "(empty report - no data for the selected period)"
    exit 0
fi

# Save to CSV if requested
if [[ -n "$CSV_FILE" ]]; then
    echo "$report_data" | tr '\t' ',' > "$CSV_FILE"
    echo "Report saved to: $CSV_FILE"
    echo ""
fi

# Display formatted report
echo "--- Report Data ---"
echo ""
echo "$report_data" | format_tsv_report
