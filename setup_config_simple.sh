#!/bin/bash
CONFIG="$(dirname "$0")/config.yaml"

echo "Настройка config.yaml"
echo "===================="
echo ""

# Читаем токен
echo -n "Telegram Bot Token: "
read -r BOT_TOKEN

if [[ -z "$BOT_TOKEN" ]]; then
    echo "Ошибка: токен не может быть пустым"
    exit 1
fi

echo "Токен принят: ${BOT_TOKEN:0:8}..."
echo ""

# Генерируем секретный ключ (простым способом)
echo "Генерация secret_key..."
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
echo "secret_key: ${SECRET_KEY:0:8}..."
echo ""

# Записываем в файл
cat > "$CONFIG" <<EOF
bot_token: "$BOT_TOKEN"
secret_key: "$SECRET_KEY"

roles:
  admins: []
  support: []
EOF

echo "Готово! Файл записан: $CONFIG"