# Support WebApp — Telegram Mini App для службы поддержки

Telegram Mini App для обработки обращений в службу поддержки.
Пользователи взаимодействуют через WebApp, уведомления приходят через Telegram-бота.

---

## Содержание

- [Стек технологий](#стек-технологий)
- [Структура проекта](#структура-проекта)
- [Быстрый старт](#быстрый-старт)
- [Настройка конфигурации](#настройка-конфигурации)
- [Запуск в продакшн](#запуск-в-продакшн)
- [Деплой по субпути /support](#деплой-по-субпути-support)
- [API Reference](#api-reference)
- [Роли и права](#роли-и-права)
- [Статусы обращений](#статусы-обращений)
- [Уведомления](#уведомления)

---

## Стек технологий

| Слой | Технология |
|---|---|
| Backend | Python 3.11+ · FastAPI |
| База данных | SQLite · SQLAlchemy ORM |
| Telegram-бот | python-telegram-bot 21 |
| Frontend | Vanilla JS · Telegram WebApp SDK · Tailwind CSS CDN |
| Авторизация | Telegram initData (HMAC) + JWT (24 ч) |
| Деплой | Один процесс, FastAPI отдаёт API + статику |

---

## Структура проекта

```
/
├── app/
│   ├── main.py              # FastAPI app, подключение роутеров и статики
│   ├── bot.py               # Отправка уведомлений через Telegram-бота
│   ├── config.py            # Загрузка config.yaml
│   ├── database.py          # Инициализация SQLite, сессии
│   ├── models.py            # SQLAlchemy модели (User, Ticket, Message, …)
│   ├── auth.py              # Валидация Telegram initData, выдача JWT
│   ├── dependencies.py      # FastAPI dependencies (current_user)
│   └── routers/
│       ├── users.py         # POST /auth/telegram, GET /auth/me
│       ├── tickets.py       # CRUD обращений, статусы, назначение
│       ├── messages.py      # Чат (GET/POST /tickets/{id}/messages)
│       └── files.py         # Загрузка и скачивание файлов
├── frontend/
│   ├── index.html           # SPA-точка входа
│   ├── app.js               # Роутинг, логика всех экранов
│   └── style.css            # Стили (Telegram theme vars совместимые)
├── uploads/                 # Файлы пользователей (в .gitignore)
├── config.yaml              # Конфигурация ролей и токенов
├── support.db               # SQLite база (создаётся автоматически)
└── requirements.txt
```

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd <repo-dir>
```

### 2. Создать виртуальное окружение

```bash
python3.11 -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить конфигурацию

Отредактируйте `config.yaml`:

```yaml
bot_token: "1234567890:AAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
secret_key: "super-secret-random-string-minimum-32-chars"

roles:
  admins:
    - 123456789      # ваш telegram_id
  support:
    - 987654321
    - 111222333
```

> Как узнать свой `telegram_id` — напишите боту [@userinfobot](https://t.me/userinfobot).

### 5. Запустить приложение

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Приложение будет доступно по адресу `http://localhost:8000`.
Документация API (Swagger UI): `http://localhost:8000/docs`.

---

## Настройка конфигурации

### config.yaml

| Поле | Описание |
|---|---|
| `bot_token` | Токен Telegram-бота из [@BotFather](https://t.me/BotFather) |
| `secret_key` | Случайная строка для подписи JWT (минимум 32 символа) |
| `roles.admins` | Список `telegram_id` с ролью `admin` |
| `roles.support` | Список `telegram_id` с ролью `support` |

Пользователи, не указанные в конфиге, получают роль `author` при первом входе.

### Генерация secret_key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Настройка Telegram-бота

1. Создайте бота через [@BotFather](https://t.me/BotFather): `/newbot`
2. Получите токен и вставьте в `config.yaml`
3. Для Mini App: в BotFather → `/newapp` → укажите URL вашего сервера
4. Или используйте `/setmenubutton` чтобы добавить кнопку открытия WebApp

---

## Запуск в продакшн

### Через systemd

Создайте файл `/etc/systemd/system/support-webapp.service`:

```ini
[Unit]
Description=Support WebApp
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/support-webapp
ExecStart=/opt/support-webapp/.venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable support-webapp
sudo systemctl start support-webapp
```

### Nginx reverse proxy (с HTTPS)

Telegram Mini App требует HTTPS. Пример конфига Nginx:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    client_max_body_size 11M;   # чуть больше лимита 10 МБ

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Получить SSL-сертификат бесплатно:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Деплой по субпути /support

Если приложение должно быть доступно по адресу `https://int.fhill.ru/support/`
(а не по корню домена), нужно настроить три вещи.

### Как это работает

```
Браузер                  Nginx                    FastAPI
──────────               ──────────               ──────────
GET /support/         →  strip /support/       →  GET /
GET /support/style.css→  strip /support/       →  GET /style.css  (StaticFiles)
fetch('/support/tickets')→ strip /support/     →  GET /tickets    (router)
href="/support/files/…" →  strip /support/     →  GET /files/…    (router)
```

Nginx снимает префикс `/support` — FastAPI работает без каких-либо изменений.
Frontend знает о префиксе через переменную `window.SUPPORT_BASE_PATH`.

### Шаг 1 — Раскомментировать строку в index.html

Откройте `frontend/index.html` и раскомментируйте строку в `<head>`:

```html
<script>window.SUPPORT_BASE_PATH = '/support';</script>
```

Это единственное изменение в коде.

### Шаг 2 — Nginx конфиг

```nginx
server {
    listen 443 ssl;
    server_name int.fhill.ru;

    ssl_certificate     /etc/letsencrypt/live/int.fhill.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/int.fhill.ru/privkey.pem;

    client_max_body_size 11M;

    # ── Support WebApp ────────────────────────────────────────────
    location /support/ {
        # Trailing slash в proxy_pass снимает префикс /support/
        # Браузер запрашивает /support/tickets → FastAPI получает /tickets
        proxy_pass         http://127.0.0.1:8000/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # Редирект /support → /support/ (чтобы относительные пути работали)
    location = /support {
        return 301 /support/;
    }
}
```

> **Важно:** trailing slash в `proxy_pass http://127.0.0.1:8000/` — ключевой момент.
> Именно он заставляет Nginx вырезать `/support/` из URI перед передачей FastAPI.

### Шаг 3 — Перезагрузить Nginx

```bash
sudo nginx -t          # проверить конфиг
sudo systemctl reload nginx
```

### Шаг 4 — Запустить FastAPI (без изменений)

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

FastAPI не знает о субпути — это задача Nginx. Приложение работает как обычно на порту 8000.

### Итоговая проверка

```bash
# Приложение открывается
curl -IL https://int.fhill.ru/support/

# API отвечает (через субпуть)
curl https://int.fhill.ru/support/auth/me
# → 403 (это ожидаемо без токена, значит nginx проксирует корректно)
```

### Если на сервере уже есть другие сайты

Просто добавьте блок `location /support/` в существующий `server {}` блок для `int.fhill.ru`.
Остальные location-блоки не затрагиваются.

---

## API Reference

Все защищённые эндпоинты требуют заголовок:
```
Authorization: Bearer <jwt-token>
```

### Авторизация

```
POST /auth/telegram
Body: { "initData": "<raw initData from Telegram.WebApp>" }
→    { "token": "<jwt>", "user": { id, telegram_id, username, full_name, role } }

GET  /auth/me
→    { id, telegram_id, username, full_name, role }
```

### Обращения

```
GET  /tickets?filter=mine|all|closed&urgent=true|false
POST /tickets          { title, description, steps?, url?, is_urgent }
GET  /tickets/{id}
PUT  /tickets/{id}     { title?, description?, steps?, url?, is_urgent? }
PUT  /tickets/{id}/status   { "status": "<new_status>" }
PUT  /tickets/{id}/assign   {}
PUT  /tickets/{id}/urgent   { "is_urgent": true|false }
```

### Чат

```
GET  /tickets/{id}/messages
POST /tickets/{id}/messages   multipart: text=..., file=<upload>
```

### Файлы

```
POST /tickets/{id}/files      multipart: file=<upload>
GET  /files/{stored_path}
```

**Ограничения файлов:**
- Максимальный размер: **10 МБ**
- Запрещённые расширения: `.exe .bat .cmd .sh .msi .ps1 .vbs .app .bin .dll .com`

---

## Роли и права

| Действие | Author | Support | Admin |
|---|:---:|:---:|:---:|
| Создать обращение | ✅ | ✅ | ✅ |
| Видеть вкладку «Все» | ❌ | ✅ | ✅ |
| Видеть вкладку «Мои» | ✅ | ✅ | ✅ |
| Видеть закрытые (свои) | ✅ | ✅ | ✅ |
| Редактировать обращение | только свои, только `new` | ❌ | ❌ |
| Поставить/снять «Срочно» | ✅ (своё) | ✅ | ✅ |
| Взять обращение | ❌ | ✅ | ✅ |
| Менять статус | `closed` из `biz_review`, `reopened` | ✅ | ✅ |
| Писать в чат | ✅ | ✅ | ✅ |
| Прикладывать файлы | ✅ | ✅ | ✅ |

---

## Статусы обращений

```
new ──────────────→ in_progress ──→ on_pause ──→ in_progress
                         │               ↑
                         ↓               │
                     biz_review ─────────┘
                         │
                         ↓ (автор или поддержка)
                       closed
                         │
                         ↓ (автор)
                      reopened ──→ in_progress
```

| Код | Название | Кто переходит |
|---|---|---|
| `new` | Новое | — (начальный статус) |
| `in_progress` | В работе | Поддержка/Админ |
| `on_pause` | На паузе | Поддержка/Админ |
| `biz_review` | Проверка бизнесом | Поддержка/Админ |
| `closed` | Закрытое | Автор (из `biz_review`) или Поддержка/Админ |
| `reopened` | Переоткрытое | Автор (из `closed`) |

---

## Уведомления

Бот отправляет уведомления с кнопкой **«Открыть»** (deep link `?startapp=ticket_{id}`):

| Событие | Кому |
|---|---|
| Создано новое обращение | Все support + admins |
| Обращение отмечено «Срочно» | Все support + admins (с пометкой 🔴) |
| Статус изменился | Автор обращения |
| Обращение взято специалистом | Автор обращения |
| Статус → `biz_review` | Автор (с призывом ответить) |
| Новое сообщение от автора | Все support + admins |
| Новое сообщение от поддержки | Автор обращения |

---

## Разработка

### Переменные окружения (альтернатива config.yaml)

Вместо редактирования `config.yaml` можно использовать `.env`-файл и доработать `config.py`.

### Запуск с автоперезагрузкой

```bash
uvicorn app.main:app --reload --port 8000
```

### Просмотр БД

```bash
sqlite3 support.db
.tables
SELECT * FROM tickets;
```

### Swagger UI

После запуска: `http://localhost:8000/docs`
