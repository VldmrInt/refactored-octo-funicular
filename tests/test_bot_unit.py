import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app import bot


class TestSupportRecipients:
    def test_support_recipients(self):
        with patch("app.bot.ADMIN_IDS", [100, 200]):
            with patch("app.bot.SUPPORT_IDS", [300, 400]):
                recipients = bot._support_recipients()
                assert set(recipients) == {100, 200, 300, 400}

    def test_support_recipients_dedup(self):
        with patch("app.bot.ADMIN_IDS", [100, 200, 300]):
            with patch("app.bot.SUPPORT_IDS", [300, 400]):
                recipients = bot._support_recipients()
                assert set(recipients) == {100, 200, 300, 400}


class TestSend:
    @pytest.mark.asyncio
    async def test_send_success(self):
        with patch("app.bot._get_bot") as mock_get_bot:
            mock_bot = AsyncMock()
            mock_bot.send_message = AsyncMock()
            mock_get_bot.return_value = mock_bot

            await bot._send(12345, "Test message")

            mock_bot.send_message.assert_called_once_with(
                chat_id=12345,
                text="Test message",
                parse_mode="HTML",
                reply_markup=None
            )

    @pytest.mark.asyncio
    async def test_send_with_markup(self):
        with patch("app.bot._get_bot") as mock_get_bot:
            mock_bot = AsyncMock()
            mock_bot.send_message = AsyncMock()
            mock_get_bot.return_value = mock_bot

            markup = MagicMock()
            await bot._send(12345, "Test message", markup)

            mock_bot.send_message.assert_called_once_with(
                chat_id=12345,
                text="Test message",
                parse_mode="HTML",
                reply_markup=markup
            )

    @pytest.mark.asyncio
    async def test_send_failure_logs_warning(self):
        with patch("app.bot._get_bot") as mock_get_bot:
            mock_bot = AsyncMock()
            mock_bot.send_message.side_effect = Exception("Bot error")
            mock_get_bot.return_value = mock_bot

            with patch("app.bot.logger") as mock_logger:
                await bot._send(12345, "Test message")

                mock_logger.warning.assert_called_once()


class TestOpenButton:
    def test_open_button_creates_markup(self):
        with patch("app.bot.InlineKeyboardButton") as mock_button:
            with patch("app.bot.InlineKeyboardMarkup") as mock_markup:
                mock_button.return_value = "button"
                mock_markup.return_value = "markup"

                result = bot._open_button("#123", 456)

                assert result == "markup"
                mock_markup.assert_called_once_with([["button"]])

    def test_open_button_url_format(self):
        with patch("app.bot.InlineKeyboardButton") as mock_button:
            with patch("app.bot.InlineKeyboardMarkup") as mock_markup:
                mock_button_instance = MagicMock()
                mock_button.return_value = mock_button_instance
                mock_markup.return_value = "markup"

                bot._open_button("#ABC-001", 123)

                mock_button.assert_called_once()
                call_kwargs = mock_button.call_args[1]
                assert "ticket_123" in call_kwargs["url"]


class TestNotifyNewTicket:
    @pytest.mark.asyncio
    async def test_notify_new_ticket(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button") as mock_button:
                with patch("app.bot._support_recipients", return_value=[100, 200]):
                    ticket = MagicMock()
                    ticket.id = 1
                    ticket.number = "#001"
                    ticket.title = "Test ticket"
                    ticket.is_urgent = False

                    author = MagicMock()
                    author.username = "testuser"
                    author.full_name = "Test User"

                    mock_button.return_value = "markup"

                    await bot.notify_new_ticket(ticket, author)

                    assert mock_send.call_count == 2
                    for call in mock_send.call_args_list:
                        assert "#001" in call.args[1]
                        assert "Test ticket" in call.args[1]

    @pytest.mark.asyncio
    async def test_notify_urgent_ticket(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                with patch("app.bot._support_recipients", return_value=[100]):
                    ticket = MagicMock()
                    ticket.id = 1
                    ticket.number = "#001"
                    ticket.title = "Urgent issue"
                    ticket.is_urgent = True

                    author = MagicMock()
                    author.username = "user"

                    await bot.notify_new_ticket(ticket, author)

                    call_text = mock_send.call_args[0][1]
                    assert "🔴 СРОЧНО" in call_text


class TestNotifyStatusChanged:
    @pytest.mark.asyncio
    async def test_notify_status_changed(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                ticket = MagicMock()
                ticket.id = 1
                ticket.number = "#001"
                ticket.status = "in_progress"
                ticket.author_id = 10

                initiator = MagicMock()

                await bot.notify_status_changed(ticket, "new", initiator)

                call_text = mock_send.call_args[0][1]
                assert "#001" in call_text
                assert "изменён" in call_text


class TestNotifyAssigned:
    @pytest.mark.asyncio
    async def test_notify_assigned(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                ticket = MagicMock()
                ticket.id = 1
                ticket.number = "#001"
                ticket.author_id = 10

                assignee = MagicMock()
                assignee.full_name = "Support Agent"

                await bot.notify_assigned(ticket, assignee)

                call_text = mock_send.call_args[0][1]
                assert "#001" in call_text
                assert "Support Agent" in call_text


class TestNotifyUrgent:
    @pytest.mark.asyncio
    async def test_notify_urgent(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                with patch("app.bot._support_recipients", return_value=[100, 200]):
                    ticket = MagicMock()
                    ticket.id = 1
                    ticket.number = "#001"
                    ticket.title = "Critical issue"

                    initiator = MagicMock()

                    await bot.notify_urgent(ticket, initiator)

                    assert mock_send.call_count == 2
                    call_text = mock_send.call_args[0][1]
                    assert "🔴 СРОЧНО" in call_text
                    assert "#001" in call_text


class TestNotifyNewMessage:
    @pytest.mark.asyncio
    async def test_notify_support_reply_to_author(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                ticket = MagicMock()
                ticket.id = 1
                ticket.number = "#001"

                message = MagicMock()
                message.text = "Here is the solution"

                sender = MagicMock()
                sender.role = "support"

                await bot.notify_new_message(ticket, message, sender)

                call_text = mock_send.call_args[0][1]
                assert "#001" in call_text
                assert "solution" in call_text

    @pytest.mark.asyncio
    async def test_notify_author_message_to_support(self):
        with patch("app.bot._send") as mock_send:
            with patch("app.bot._open_button", return_value=None):
                with patch("app.bot._support_recipients", return_value=[100, 200]):
                    ticket = MagicMock()
                    ticket.id = 1
                    ticket.number = "#001"

                    message = MagicMock()
                    message.text = "I need help"

                    sender = MagicMock()
                    sender.role = "author"
                    sender.username = "customer"

                    await bot.notify_new_message(ticket, message, sender)

                    assert mock_send.call_count == 2
                    call_text = mock_send.call_args[0][1]
                    assert "#001" in call_text
                    assert "customer" in call_text