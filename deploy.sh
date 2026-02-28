#!/usr/bin/env bash
# deploy.sh — обновление support-webapp на сервере
# Использование: sudo bash deploy.sh
# Или с кастомными параметрами: BRANCH=main APP_DIR=/opt/support bash deploy.sh

set -euo pipefail

# ── Настройки ──────────────────────────────────────────────────
APP_DIR="${APP_DIR:-/opt/support-webapp}"
VENV_DIR="$APP_DIR/.venv"
SERVICE="${SERVICE:-support-webapp}"
BRANCH="${BRANCH:-master}"
REPO_URL="${REPO_URL:-}"   # оставьте пустым, если уже склонировано

# ── Цвета ──────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo -e "${GREEN}==>${NC} $*"; }
warn()  { echo -e "${YELLOW}WARN:${NC} $*"; }
die()   { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }

# ── Проверки ───────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Запустите от root: sudo bash deploy.sh"
command -v git      >/dev/null || die "git не установлен"
command -v python3  >/dev/null || die "python3 не установлен"

# ── Клонирование (первый раз) ──────────────────────────────────
if [[ ! -d "$APP_DIR/.git" ]]; then
    [[ -n "$REPO_URL" ]] || die "APP_DIR=$APP_DIR не существует. Укажите REPO_URL."
    step "Клонирование репозитория в $APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# ── Git pull ───────────────────────────────────────────────────
step "Обновление кода (ветка: $BRANCH)"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

COMMIT=$(git log -1 --pretty=format:'%h %s')
echo "  Текущий коммит: $COMMIT"

# ── Виртуальное окружение и зависимости ───────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    step "Создание виртуального окружения"
    python3 -m venv "$VENV_DIR"
fi

step "Установка/обновление зависимостей"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r requirements.txt

# ── Перезапуск сервиса ─────────────────────────────────────────
if systemctl is-active --quiet "$SERVICE"; then
    step "Перезапуск сервиса $SERVICE"
    systemctl restart "$SERVICE"
elif systemctl list-unit-files --quiet "$SERVICE.service" &>/dev/null; then
    step "Запуск сервиса $SERVICE"
    systemctl start "$SERVICE"
else
    warn "Сервис '$SERVICE' не найден в systemd — перезапустите вручную"
fi

# ── Итог ───────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✓ Деплой завершён${NC}"
echo "  Директория: $APP_DIR"
echo "  Коммит:     $COMMIT"

if systemctl is-active --quiet "$SERVICE"; then
    echo -e "  Сервис:     ${GREEN}running${NC}"
else
    echo -e "  Сервис:     ${YELLOW}не запущен${NC}"
fi
