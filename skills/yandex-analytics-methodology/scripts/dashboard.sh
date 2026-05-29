#!/bin/bash
# Quick dashboard — combined metrics from available Yandex services
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/../../" && pwd)"

HOST=""
FROM_DATE=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
TO_DATE=$(date +%Y-%m-%d)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --from) FROM_DATE="$2"; shift 2 ;;
        --to) TO_DATE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "=== Yandex Analytics Dashboard ==="
echo "Period: $FROM_DATE — $TO_DATE"
echo ""

# --- Metrika ---
if [[ -f "$SKILLS_DIR/yandex-metrika/scripts/overview.sh" ]]; then
    echo "--- Traffic (Metrika) ---"
    bash "$SKILLS_DIR/yandex-metrika/scripts/overview.sh" --from "$FROM_DATE" --to "$TO_DATE" 2>/dev/null
    echo ""
fi

# --- Webmaster ---
if [[ -n "$HOST" && -f "$SKILLS_DIR/yandex-webmaster/scripts/indexing.sh" ]]; then
    echo "--- Indexing (Webmaster) ---"
    bash "$SKILLS_DIR/yandex-webmaster/scripts/indexing.sh" --host "$HOST" --type summary 2>/dev/null
    echo ""

    echo "--- SQI (Webmaster) ---"
    bash "$SKILLS_DIR/yandex-webmaster/scripts/sqi.sh" --host "$HOST" --from "$FROM_DATE" 2>/dev/null
    echo ""

    echo "--- Diagnostics (Webmaster) ---"
    bash "$SKILLS_DIR/yandex-webmaster/scripts/diagnostics.sh" --host "$HOST" 2>/dev/null
    echo ""
fi

echo "=== Dashboard Complete ==="
