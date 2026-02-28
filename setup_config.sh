#!/usr/bin/env bash
# setup_config.sh — интерактивная настройка config.yaml
# Использование: bash setup_config.sh [--non-interactive]

set -euo pipefail

CONFIG="$(dirname "$0")/config.yaml"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
die()  { echo -e "${RED}✗ ERROR:${NC} $*" >&2; exit 1; }

# ── Режим non-interactive (для CI / тестов) ────────────────────────────────
NON_INTERACTIVE=false
[[ "${1:-}" == "--non-interactive" ]] && NON_INTERACTIVE=true

ask() {
    local prompt="$1" default="${2:-}" var
    if $NON_INTERACTIVE; then
        echo "$default"
        return
    fi
    if [[ -n "$default" ]]; then
        read -rp "$prompt [$default]: " var
        echo "${var:-$default}"
    else
        read -rp "$prompt: " var
        echo "$var"
    fi
}

ask_list() {
    local prompt="$1"
    if $NON_INTERACTIVE; then
        echo ""
        return
    fi
    echo "$prompt (через пробел, Enter — пропустить):"
    read -r var
    echo "$var"
}

# ── Приветствие ────────────────────────────────────────────────────────────
echo ""
echo "  Support Webapp — настройка config.yaml"
echo "  ─────────────────────────────────────"

# ── Существующий конфиг ────────────────────────────────────────────────────
if [[ -f "$CONFIG" ]]; then
    warn "Файл $CONFIG уже существует."
    if ! $NON_INTERACTIVE; then
        read -rp "  Перезаписать? [y/N]: " yn
        [[ "${yn,,}" == "y" ]] || { echo "Отменено."; exit 0; }
    fi
fi

# ── Ввод параметров ────────────────────────────────────────────────────────
echo ""
BOT_TOKEN=$(ask "Telegram Bot Token" "${BOT_TOKEN:-}")
[[ -n "$BOT_TOKEN" ]] || die "Bot token не может быть пустым."

SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 24 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(24))')}"

echo ""
ADMIN_IDS_RAW=$(ask_list "Telegram ID администраторов")
SUPPORT_IDS_RAW=$(ask_list "Telegram ID сотрудников поддержки")

# ── Формирование YAML-списков ──────────────────────────────────────────────
build_yaml_list() {
    local raw="$1"
    local out=""
    for id in $raw; do
        [[ "$id" =~ ^[0-9]+$ ]] || die "Некорректный Telegram ID: '$id' (только цифры)."
        out+="    - $id"$'\n'
    done
    echo "$out"
}

ADMIN_YAML=$(build_yaml_list "$ADMIN_IDS_RAW")
SUPPORT_YAML=$(build_yaml_list "$SUPPORT_IDS_RAW")

# ── Запись файла ───────────────────────────────────────────────────────────
cat > "$CONFIG" <<EOF
bot_token: "$BOT_TOKEN"
secret_key: "$SECRET_KEY"

roles:
  admins:
${ADMIN_YAML:-    []}
  support:
${SUPPORT_YAML:-    []}
EOF

ok "Конфиг записан: $CONFIG"
echo ""
echo "  bot_token:  ${BOT_TOKEN:0:8}…"
echo "  secret_key: ${SECRET_KEY:0:8}…"
[[ -n "$ADMIN_IDS_RAW"   ]] && echo "  admins:     $ADMIN_IDS_RAW"   || warn "Список admins пуст."
[[ -n "$SUPPORT_IDS_RAW" ]] && echo "  support:    $SUPPORT_IDS_RAW" || warn "Список support пуст."
echo ""
