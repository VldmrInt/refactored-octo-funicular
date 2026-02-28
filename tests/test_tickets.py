import pytest
from tests.conftest import auth_headers, make_user, TICKET_PAYLOAD


class TestCreateTicket:
    def test_create_ok(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user))
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == TICKET_PAYLOAD["title"]
        assert data["status"] == "new"
        assert data["is_urgent"] is False
        assert data["number"].startswith("#")
        assert data["author"]["telegram_id"] == 1

    def test_create_urgent(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post(
            "/tickets",
            json={**TICKET_PAYLOAD, "is_urgent": True},
            headers=auth_headers(user),
        )
        assert r.status_code == 201
        assert r.json()["is_urgent"] is True

    def test_create_missing_description(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post(
            "/tickets",
            json={"title": "Без описания"},
            headers=auth_headers(user),
        )
        assert r.status_code == 422

    def test_create_missing_title(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post(
            "/tickets",
            json={"description": "Без заголовка"},
            headers=auth_headers(user),
        )
        assert r.status_code == 422

    def test_create_unauthorized(self, client):
        r = client.post("/tickets", json=TICKET_PAYLOAD)
        assert r.status_code == 403

    def test_numbers_increment(self, client, db):
        user = make_user(db, telegram_id=1)
        hdrs = auth_headers(user)
        t1 = client.post("/tickets", json=TICKET_PAYLOAD, headers=hdrs).json()
        t2 = client.post("/tickets", json=TICKET_PAYLOAD, headers=hdrs).json()
        assert t1["number"] != t2["number"]


class TestListTickets:
    def test_list_mine(self, client, db):
        user = make_user(db, telegram_id=1)
        client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user))
        r = client.get("/tickets?filter=mine", headers=auth_headers(user))
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_list_mine_empty(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.get("/tickets?filter=mine", headers=auth_headers(user))
        assert r.status_code == 200
        assert r.json() == []

    def test_list_mine_isolates_from_others(self, client, db):
        u1 = make_user(db, telegram_id=1)
        u2 = make_user(db, telegram_id=2)
        client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(u1))
        r = client.get("/tickets?filter=mine", headers=auth_headers(u2))
        assert r.json() == []

    def test_list_all_forbidden_for_author(self, client, db):
        user = make_user(db, telegram_id=1, role="author")
        r = client.get("/tickets?filter=all", headers=auth_headers(user))
        assert r.status_code == 403

    def test_list_all_allowed_for_support(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author))
        r = client.get("/tickets?filter=all", headers=auth_headers(support))
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_list_all_allowed_for_admin(self, client, db):
        author = make_user(db, telegram_id=1)
        admin = make_user(db, telegram_id=2, role="admin")
        client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author))
        r = client.get("/tickets?filter=all", headers=auth_headers(admin))
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestGetTicket:
    def test_get_own(self, client, db):
        user = make_user(db, telegram_id=1)
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()
        r = client.get(f"/tickets/{created['id']}", headers=auth_headers(user))
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_not_found(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.get("/tickets/99999", headers=auth_headers(user))
        assert r.status_code == 404

    def test_get_other_users_ticket_denied(self, client, db):
        owner = make_user(db, telegram_id=1)
        other = make_user(db, telegram_id=2)
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(owner)).json()
        r = client.get(f"/tickets/{created['id']}", headers=auth_headers(other))
        assert r.status_code == 403

    def test_support_can_get_any_ticket(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        r = client.get(f"/tickets/{created['id']}", headers=auth_headers(support))
        assert r.status_code == 200


class TestEditTicket:
    def test_author_can_edit_new(self, client, db):
        user = make_user(db, telegram_id=1)
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()
        r = client.put(
            f"/tickets/{created['id']}",
            json={"title": "Новый заголовок"},
            headers=auth_headers(user),
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Новый заголовок"

    def test_other_user_cannot_edit(self, client, db):
        owner = make_user(db, telegram_id=1)
        other = make_user(db, telegram_id=2)
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(owner)).json()
        r = client.put(
            f"/tickets/{created['id']}",
            json={"title": "Взлом"},
            headers=auth_headers(other),
        )
        assert r.status_code == 403

    def test_cannot_edit_after_status_change(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        created = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        # Move to in_progress
        client.put(
            f"/tickets/{created['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(support),
        )
        r = client.put(
            f"/tickets/{created['id']}",
            json={"title": "Поздно"},
            headers=auth_headers(author),
        )
        assert r.status_code == 403


class TestChangeStatus:
    def _create(self, client, user):
        return client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()

    def test_support_new_to_in_progress(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = self._create(client, author)
        r = client.put(
            f"/tickets/{ticket['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(support),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

    def test_invalid_transition_new_to_closed(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = self._create(client, author)
        r = client.put(
            f"/tickets/{ticket['id']}/status",
            json={"status": "closed"},
            headers=auth_headers(support),
        )
        assert r.status_code == 400

    def test_author_cannot_move_to_in_progress(self, client, db):
        author = make_user(db, telegram_id=1)
        ticket = self._create(client, author)
        r = client.put(
            f"/tickets/{ticket['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(author),
        )
        assert r.status_code == 403

    def test_full_lifecycle(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        hdrs_s = auth_headers(support)
        hdrs_a = auth_headers(author)
        ticket = self._create(client, author)
        tid = ticket["id"]

        # new → in_progress
        r = client.put(f"/tickets/{tid}/status", json={"status": "in_progress"}, headers=hdrs_s)
        assert r.json()["status"] == "in_progress"

        # in_progress → biz_review
        r = client.put(f"/tickets/{tid}/status", json={"status": "biz_review"}, headers=hdrs_s)
        assert r.json()["status"] == "biz_review"

        # author closes from biz_review
        r = client.put(f"/tickets/{tid}/status", json={"status": "closed"}, headers=hdrs_a)
        assert r.json()["status"] == "closed"

        # author reopens
        r = client.put(f"/tickets/{tid}/status", json={"status": "reopened"}, headers=hdrs_a)
        assert r.json()["status"] == "reopened"

    def test_status_change_creates_system_message(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = self._create(client, author)
        client.put(
            f"/tickets/{ticket['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(support),
        )
        msgs = client.get(
            f"/tickets/{ticket['id']}/messages", headers=auth_headers(support)
        ).json()
        assert any(m["sender_role"] == "system" for m in msgs)


class TestAssignTicket:
    def test_support_assigns(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        r = client.put(
            f"/tickets/{ticket['id']}/assign",
            json={},
            headers=auth_headers(support),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assignee"]["id"] == support.id
        # Auto-transition new → in_progress on assign
        assert data["status"] == "in_progress"

    def test_author_cannot_assign(self, client, db):
        author = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        r = client.put(
            f"/tickets/{ticket['id']}/assign",
            json={},
            headers=auth_headers(author),
        )
        assert r.status_code == 403

    def test_cannot_assign_twice(self, client, db):
        author = make_user(db, telegram_id=1)
        s1 = make_user(db, telegram_id=2, role="support")
        s2 = make_user(db, telegram_id=3, role="support")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        client.put(f"/tickets/{ticket['id']}/assign", json={}, headers=auth_headers(s1))
        r = client.put(f"/tickets/{ticket['id']}/assign", json={}, headers=auth_headers(s2))
        assert r.status_code == 400


class TestUrgentToggle:
    def test_author_marks_urgent(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()
        r = client.put(
            f"/tickets/{ticket['id']}/urgent",
            json={"is_urgent": True},
            headers=auth_headers(user),
        )
        assert r.status_code == 200
        assert r.json()["is_urgent"] is True

    def test_unmark_urgent(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = client.post(
            "/tickets",
            json={**TICKET_PAYLOAD, "is_urgent": True},
            headers=auth_headers(user),
        ).json()
        r = client.put(
            f"/tickets/{ticket['id']}/urgent",
            json={"is_urgent": False},
            headers=auth_headers(user),
        )
        assert r.status_code == 200
        assert r.json()["is_urgent"] is False

    def test_support_can_toggle_urgent(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()
        r = client.put(
            f"/tickets/{ticket['id']}/urgent",
            json={"is_urgent": True},
            headers=auth_headers(support),
        )
        assert r.status_code == 200

    def test_other_author_cannot_toggle(self, client, db):
        owner = make_user(db, telegram_id=1)
        other = make_user(db, telegram_id=2)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(owner)).json()
        r = client.put(
            f"/tickets/{ticket['id']}/urgent",
            json={"is_urgent": True},
            headers=auth_headers(other),
        )
        assert r.status_code == 403
