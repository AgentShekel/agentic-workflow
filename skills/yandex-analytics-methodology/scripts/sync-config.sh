#!/bin/bash
# Sync unified config to all individual Yandex skill configs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIFIED_ENV="$SCRIPT_DIR/../config/.env"
SKILLS_DIR="$(cd "$SCRIPT_DIR/../../" && pwd)"

if [[ ! -f "$UNIFIED_ENV" ]]; then
    echo "Error: config/.env not found. Copy from config/.env.example first."
    exit 1
fi

source "$UNIFIED_ENV"

echo "=== Syncing Yandex Analytics Config ==="
echo ""

# --- Webmaster ---
WM_DIR="$SKILLS_DIR/yandex-webmaster/config"
if [[ -d "$SKILLS_DIR/yandex-webmaster" ]]; then
    mkdir -p "$WM_DIR"
    cat > "$WM_DIR/.env" <<EOF
YANDEX_WEBMASTER_TOKEN=${YANDEX_OAUTH_TOKEN}
EOF
    echo "[OK] yandex-webmaster"
else
    echo "[SKIP] yandex-webmaster-guide — skill not installed"
fi

# --- Metrika ---
MK_DIR="$SKILLS_DIR/yandex-metrika/config"
if [[ -d "$SKILLS_DIR/yandex-metrika" ]]; then
    mkdir -p "$MK_DIR"
    cat > "$MK_DIR/.env" <<EOF
YANDEX_METRIKA_TOKEN=${YANDEX_OAUTH_TOKEN}
# Counter is per-project — pass via --counter flag or set here for default site
${YANDEX_METRIKA_COUNTER:+YANDEX_METRIKA_COUNTER=${YANDEX_METRIKA_COUNTER}}
EOF
    echo "[OK] yandex-metrika-guide (counter: pass via --counter per project)"
else
    echo "[SKIP] yandex-metrika-guide — skill not installed"
fi

# --- Direct ---
DR_DIR="$SKILLS_DIR/yandex-direct/config"
if [[ -d "$SKILLS_DIR/yandex-direct" ]]; then
    mkdir -p "$DR_DIR"
    cat > "$DR_DIR/.env" <<EOF
YANDEX_DIRECT_TOKEN=${YANDEX_OAUTH_TOKEN}
${YANDEX_DIRECT_LOGIN:+YANDEX_DIRECT_LOGIN=${YANDEX_DIRECT_LOGIN}}
${YANDEX_DIRECT_SANDBOX:+YANDEX_DIRECT_SANDBOX=${YANDEX_DIRECT_SANDBOX}}
EOF
    echo "[OK] yandex-direct"
else
    echo "[SKIP] yandex-direct-guide — skill not installed"
fi

# --- Search (Yandex Cloud Search API v2) ---
SX_DIR="$SKILLS_DIR/yandex-search/config"
if [[ -d "$SKILLS_DIR/yandex-search" ]]; then
    mkdir -p "$SX_DIR"
    cat > "$SX_DIR/.env" <<EOF
YANDEX_SEARCH_API_KEY=${YANDEX_SEARCH_API_KEY}
YANDEX_CLOUD_FOLDER_ID=${YANDEX_CLOUD_FOLDER_ID}
EOF
    echo "[OK] yandex-search"
else
    echo "[SKIP] yandex-search-guide — skill not installed"
fi

# --- Business ---
BZ_DIR="$SKILLS_DIR/yandex-business/config"
if [[ -d "$SKILLS_DIR/yandex-business" ]]; then
    mkdir -p "$BZ_DIR"
    cat > "$BZ_DIR/.env" <<EOF
YANDEX_MAPS_APIKEY=${YANDEX_MAPS_APIKEY}
${YANDEX_BUSINESS_TOKEN:+YANDEX_BUSINESS_TOKEN=${YANDEX_OAUTH_TOKEN}}
EOF
    echo "[OK] yandex-business"
else
    echo "[SKIP] yandex-business — skill not installed"
fi

# --- Wordstat (uses same OAuth token) ---
WS_DIR="$SKILLS_DIR/yandex-wordstat/config"
if [[ -d "$SKILLS_DIR/yandex-wordstat" ]]; then
    mkdir -p "$WS_DIR"
    cat > "$WS_DIR/.env" <<EOF
YANDEX_WORDSTAT_TOKEN=${YANDEX_OAUTH_TOKEN}
EOF
    echo "[OK] yandex-wordstat"
else
    echo "[SKIP] yandex-wordstat-guide — skill not installed"
fi

echo ""
echo "Done! Run 'bash scripts/check.sh' to verify connections."
