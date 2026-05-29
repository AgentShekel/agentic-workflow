#!/bin/bash
# Check connection to all Yandex services
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/../../" && pwd)"

echo "=== Yandex Analytics Health Check ==="
echo ""

TOTAL=0
OK=0
FAIL=0
SKIP=0

check_skill() {
    local name="$1"
    local script="$2"
    TOTAL=$((TOTAL + 1))

    if [[ ! -f "$SKILLS_DIR/$name/scripts/$script" ]]; then
        echo "  [SKIP] $name — not installed"
        SKIP=$((SKIP + 1))
        return
    fi

    local result
    result=$(bash "$SKILLS_DIR/$name/scripts/$script" 2>&1)

    if echo "$result" | grep -qi "error\|not found\|missing"; then
        echo "  [FAIL] $name"
        echo "         $(echo "$result" | head -1)"
        FAIL=$((FAIL + 1))
    else
        echo "  [ OK ] $name"
        OK=$((OK + 1))
    fi
}

check_skill "yandex-webmaster-guide" "quota.sh"
check_skill "yandex-metrika-guide" "quota.sh"
check_skill "yandex-wordstat-guide" "quota.sh"
check_skill "yandex-direct-guide" "quota.sh"
check_skill "yandex-search-guide" "quota.sh"
check_skill "yandex-business" "quota.sh"

echo ""
echo "=== Results ==="
echo "Total: $TOTAL | OK: $OK | Failed: $FAIL | Skipped: $SKIP"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "Fix failed services: check config/.env and run sync-config.sh"
fi
