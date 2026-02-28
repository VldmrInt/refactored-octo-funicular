from io import BytesIO

from tests.conftest import auth_headers, make_user, TICKET_PAYLOAD


def _create_ticket(client, user):
    return client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()


class TestMessages:
    def test_send_and_list(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = _create_ticket(client, user)

        r = client.post(
            f"/tickets/{ticket['id']}/messages",
            data={"text": "Привет, поддержка!"},
            headers=auth_headers(user),
        )
        assert r.status_code == 201
        msg = r.json()
        assert msg["text"] == "Привет, поддержка!"
        assert msg["sender_id"] == user.id
        assert msg["sender_role"] == "author"

        r = client.get(f"/tickets/{ticket['id']}/messages", headers=auth_headers(user))
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_support_can_reply(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = _create_ticket(client, author)

        r = client.post(
            f"/tickets/{ticket['id']}/messages",
            data={"text": "Мы разбираемся"},
            headers=auth_headers(support),
        )
        assert r.status_code == 201
        assert r.json()["sender_role"] == "support"

    def test_stranger_cannot_message(self, client, db):
        owner = make_user(db, telegram_id=1)
        stranger = make_user(db, telegram_id=2)
        ticket = _create_ticket(client, owner)

        r = client.post(
            f"/tickets/{ticket['id']}/messages",
            data={"text": "Я тоже хочу"},
            headers=auth_headers(stranger),
        )
        assert r.status_code == 403

    def test_cannot_send_to_nonexistent_ticket(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post(
            "/tickets/99999/messages",
            data={"text": "Никуда"},
            headers=auth_headers(user),
        )
        assert r.status_code == 404

    def test_cannot_send_to_closed_ticket(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = _create_ticket(client, author)
        tid = ticket["id"]

        # new → in_progress → biz_review → closed
        client.put(f"/tickets/{tid}/status", json={"status": "in_progress"}, headers=auth_headers(support))
        client.put(f"/tickets/{tid}/status", json={"status": "biz_review"}, headers=auth_headers(support))
        client.put(f"/tickets/{tid}/status", json={"status": "closed"}, headers=auth_headers(author))

        r = client.post(
            f"/tickets/{tid}/messages",
            data={"text": "Уже поздно"},
            headers=auth_headers(author),
        )
        assert r.status_code == 400

    def test_messages_ordered_by_time(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = _create_ticket(client, user)
        hdrs = auth_headers(user)

        for text in ("Первое", "Второе", "Третье"):
            client.post(f"/tickets/{ticket['id']}/messages", data={"text": text}, headers=hdrs)

        msgs = client.get(f"/tickets/{ticket['id']}/messages", headers=hdrs).json()
        texts = [m["text"] for m in msgs]
        assert texts == ["Первое", "Второе", "Третье"]

    def test_send_message_with_file(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = _create_ticket(client, user)
        r = client.post(
            f"/tickets/{ticket['id']}/messages",
            data={"text": "Сообщение с файлом"},
            files={"file": ("document.txt", BytesIO(b"Content of file"), "text/plain")},
            headers=auth_headers(user),
        )
        assert r.status_code == 201
        msg = r.json()
        assert msg["text"] == "Сообщение с файлом"
        assert len(msg["files"]) == 1
        assert msg["files"][0]["filename"] == "document.txt"
        assert msg["files"][0]["filesize"] == 15  # len(b"Content of file") == 15

    def test_no_token_returns_403(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = _create_ticket(client, user)
        r = client.get(f"/tickets/{ticket['id']}/messages")
        assert r.status_code == 403
