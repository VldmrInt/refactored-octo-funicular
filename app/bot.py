"""
Telegram bot notifications.
All functions are async and safe to call via asyncio.create_task().
Errors are swallowed so bot failures never break the main API.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import ADMIN_IDS, SUPPORT_IDS

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "new": "Новое",
    "in_progress": "В работе",
    "on_pause": "На паузе",
    "biz_review": "Проверка бизнесом",
    "closed": "Закрытое",
    "reopened": "Переоткрытое",
}


def _get_bot():
    from telegram import Bot
    from app.config import BOT_TOKEN
    return Bot(token=BOT_TOKEN)


def _support_recipients() -> list[int]:
    return list(set(ADMIN_IDS + SUPPORT_IDS))


async def _send(chat_id: int, text: str, reply_markup=None) -> None:
    try:
        bot = _get_bot()
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as exc:
        logger.warning("Bot send failed to %s: %s", chat_id, exc)


def _open_button(ticket_number: str, ticket_id: int):
    try:
        url = f"https://t.me/bot?startapp=ticket_{ticket_id}"
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("Открыть", url=url)]]
        )
    except Exception:
        return None


async def notify_new_ticket(ticket, author) -> None:
    prefix = "🔴 СРОЧНО! " if ticket.is_urgent else ""
    text = (
        f"{prefix}📋 Новое обращение <b>{ticket.number}</b>\n"
        f"<b>{ticket.title}</b>\n"
        f"Автор: @{author.username or author.full_name}"
    )
    markup = _open_button(ticket.number, ticket.id)
    for uid in _support_recipients():
        await _send(uid, text, markup)


async def notify_status_changed(ticket, old_status: str, initiator) -> None:
    label_old = _STATUS_LABELS.get(old_status, old_status)
    label_new = _STATUS_LABELS.get(ticket.status, ticket.status)
    text = (
        f"🔄 Статус обращения <b>{ticket.number}</b> изменён\n"
        f"{label_old} → <b>{label_new}</b>"
    )
    markup = _open_button(ticket.number, ticket.id)

    author_telegram_id = ticket.author.telegram_id
    if author_telegram_id:
        if ticket.status == "biz_review":
            text_author = (
                f"⏳ Обращение <b>{ticket.number}</b> ждёт вашего ответа.\n"
                f"Статус: <b>Проверка бизнесом</b>\n"
                f"Пожалуйста, проверьте и закройте или ответьте в чате."
            )
            await _send(author_telegram_id, text_author, markup)
        else:
            await _send(author_telegram_id, text, markup)


async def notify_assigned(ticket, assignee) -> None:
    text = (
        f"👤 Обращение <b>{ticket.number}</b> взято в работу\n"
        f"Специалист: {assignee.full_name}"
    )
    markup = _open_button(ticket.number, ticket.id)
    author_telegram_id = ticket.author.telegram_id
    if author_telegram_id:
        await _send(author_telegram_id, text, markup)


async def notify_urgent(ticket, initiator) -> None:
    text = (
        f"🔴 СРОЧНО! Обращение <b>{ticket.number}</b> отмечено как срочное\n"
        f"<b>{ticket.title}</b>"
    )
    markup = _open_button(ticket.number, ticket.id)
    for uid in _support_recipients():
        await _send(uid, text, markup)


async def notify_new_message(ticket, message, sender) -> None:
    markup = _open_button(ticket.number, ticket.id)

    if sender.role in ("support", "admin"):
        author_telegram_id = ticket.author.telegram_id
        if author_telegram_id:
            text = (
                f"💬 Новое сообщение в обращении <b>{ticket.number}</b>\n"
                f"Поддержка: {message.text[:100]}"
            )
            await _send(author_telegram_id, text, markup)
    else:
        sender_label = f"@{sender.username}" if sender.username else sender.full_name
        text = (
            f"💬 Новое сообщение от автора в обращении <b>{ticket.number}</b>\n"
            f"{sender_label}: {message.text[:100]}"
        )
        for uid in _support_recipients():
            await _send(uid, text, markup)
