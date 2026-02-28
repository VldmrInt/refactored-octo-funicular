from tests.conftest import auth_headers, make_user


class TestAuthMe:
    def test_no_token_returns_403(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 403

    def test_invalid_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

    def test_valid_token_returns_user(self, client, db):
        user = make_user(db, telegram_id=42, role="author", username="alice")
        r = client.get("/auth/me", headers=auth_headers(user))
        assert r.status_code == 200
        data = r.json()
        assert data["telegram_id"] == 42
        assert data["username"] == "alice"
        assert data["role"] == "author"

    def test_support_role(self, client, db):
        user = make_user(db, telegram_id=99, role="support")
        r = client.get("/auth/me", headers=auth_headers(user))
        assert r.status_code == 200
        assert r.json()["role"] == "support"

    def test_admin_role(self, client, db):
        user = make_user(db, telegram_id=100, role="admin")
        r = client.get("/auth/me", headers=auth_headers(user))
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
