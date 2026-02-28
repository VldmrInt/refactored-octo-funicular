import pytest
from unittest.mock import patch
from tests.conftest import make_user


class TestTelegramAuth:
    def test_auth_creates_new_user(self, client, db):
        # Mock valid initData
        init_data = "user=%7B%22id%22%3A12345%2C%22first_name%22%3A%22Test%22%2C%22username%22%3A%22testuser%22%7D&hash=valid_hash"

        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {
                "id": 12345,
                "first_name": "Test",
                "last_name": "User",
                "username": "testuser"
            }

            r = client.post("/auth/telegram", json={"initData": init_data})
            assert r.status_code == 200
            data = r.json()
            assert "token" in data
            assert data["user"]["telegram_id"] == 12345
            assert data["user"]["username"] == "testuser"
            assert data["user"]["role"] == "author"

    def test_auth_updates_existing_user(self, client, db):
        # Create user first
        user = make_user(db, telegram_id=12345, username="oldname")

        init_data = "user=%7B%22id%22%3A12345%2C%22first_name%22%3A%22Updated%22%2C%22username%22%3A%22newname%22%7D&hash=valid_hash"

        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {
                "id": 12345,
                "first_name": "Updated",
                "username": "newname"
            }

            r = client.post("/auth/telegram", json={"initData": init_data})
            assert r.status_code == 200
            data = r.json()
            assert data["user"]["username"] == "newname"
            assert data["user"]["id"] == user.id  # Same user

    def test_auth_with_support_role(self, client, db):
        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {"id": 99999, "first_name": "Support"}

            with patch("app.auth.SUPPORT_IDS", [99999]):
                r = client.post("/auth/telegram", json={"initData": "user=...&hash=..."})
                assert r.status_code == 200
                assert r.json()["user"]["role"] == "support"

    def test_auth_with_admin_role(self, client, db):
        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {"id": 88888, "first_name": "Admin"}

            with patch("app.auth.ADMIN_IDS", [88888]):
                r = client.post("/auth/telegram", json={"initData": "user=...&hash=..."})
                assert r.status_code == 200
                assert r.json()["user"]["role"] == "admin"

    def test_auth_invalid_signature(self, client, db):
        init_data = "user=%7B%22id%22%3A12345%7D&hash=invalid_hash"

        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.side_effect = ValueError("Invalid initData signature")

            r = client.post("/auth/telegram", json={"initData": init_data})
            assert r.status_code == 401
            assert "Invalid" in r.json()["detail"]

    def test_auth_missing_user_field(self, client, db):
        init_data = "hash=some_hash"

        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.side_effect = ValueError("Missing user field in initData")

            r = client.post("/auth/telegram", json={"initData": init_data})
            assert r.status_code == 401

    def test_auth_user_without_username(self, client, db):
        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {
                "id": 12345,
                "first_name": "NoUsername",
            }

            r = client.post("/auth/telegram", json={"initData": "user=...&hash=..."})
            assert r.status_code == 200
            assert r.json()["user"]["username"] is None
            assert r.json()["user"]["full_name"] == "NoUsername"

    def test_auth_user_only_last_name(self, client, db):
        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {
                "id": 12345,
                "last_name": "OnlyLast",
            }

            r = client.post("/auth/telegram", json={"initData": "user=...&hash=..."})
            assert r.status_code == 200
            assert r.json()["user"]["full_name"] == "OnlyLast"

    def test_auth_user_empty_names(self, client, db):
        with patch("app.auth._validate_telegram_init_data") as mock_validate:
            mock_validate.return_value = {
                "id": 12345,
            }

            r = client.post("/auth/telegram", json={"initData": "user=...&hash=..."})
            assert r.status_code == 200
            assert r.json()["user"]["full_name"] == "12345"