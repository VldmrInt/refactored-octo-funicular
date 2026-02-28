import pytest
from datetime import datetime, timedelta, timezone
from app.auth import create_jwt, decode_jwt, determine_role


class TestCreateJWT:
    def test_create_jwt_basic(self):
        token = create_jwt(1, 12345, "author")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_jwt_decode_success(self):
        token = create_jwt(1, 12345, "support")
        payload = decode_jwt(token)
        assert payload["sub"] == "1"
        assert payload["telegram_id"] == 12345
        assert payload["role"] == "support"
        assert "exp" in payload

    def test_jwt_expiration_future(self):
        token = create_jwt(1, 12345, "author")
        payload = decode_jwt(token)
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        assert exp_time > now
        assert exp_time <= now + timedelta(hours=25)  # Should be ~24h

    def test_jwt_different_roles(self):
        for role in ["author", "support", "admin"]:
            token = create_jwt(1, 12345, role)
            payload = decode_jwt(token)
            assert payload["role"] == role


class TestDecodeJWT:
    def test_decode_invalid_token(self):
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_jwt("invalid.token.here")

    def test_decode_empty_token(self):
        with pytest.raises(ValueError):
            decode_jwt("")

    def test_decode_malformed_token(self):
        with pytest.raises(ValueError):
            decode_jwt("not.a.jwt")


class TestDetermineRole:
    def test_role_admin(self):
        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.auth.ADMIN_IDS", [100, 200])
            m.setattr("app.auth.SUPPORT_IDS", [300, 400])
            assert determine_role(100) == "admin"
            assert determine_role(200) == "admin"

    def test_role_support(self):
        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.auth.ADMIN_IDS", [100, 200])
            m.setattr("app.auth.SUPPORT_IDS", [300, 400])
            assert determine_role(300) == "support"
            assert determine_role(400) == "support"

    def test_role_author_default(self):
        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.auth.ADMIN_IDS", [100, 200])
            m.setattr("app.auth.SUPPORT_IDS", [300, 400])
            assert determine_role(999) == "author"
            assert determine_role(1) == "author"


class TestValidateTelegramInitData:
    def test_missing_hash_raises_error(self):
        from app.auth import _validate_telegram_init_data

        with pytest.raises(ValueError, match="Missing hash"):
            _validate_telegram_init_data("user=data", "bot_token")

    def test_missing_user_field_raises_error(self):
        from app.auth import _validate_telegram_init_data

        with pytest.raises(ValueError, match="Missing user field"):
            _validate_telegram_init_data("hash=abc123", "bot_token")

    def test_valid_data_parses_user(self):
        from app.auth import _validate_telegram_init_data
        from urllib.parse import quote
        import hmac
        import hashlib
        import json

        bot_token = "test_bot_token"
        user_data = {"id": 12345, "first_name": "Test", "username": "testuser"}
        user_json = quote(json.dumps(user_data))

        # Create valid hash
        params = {"user": user_json, "auth_date": "1234567890"}
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_value = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()

        init_data = f"user={user_json}&auth_date=1234567890&hash={hash_value}"

        result = _validate_telegram_init_data(init_data, bot_token)
        assert result["id"] == 12345
        assert result["first_name"] == "Test"
        assert result["username"] == "testuser"

    def test_invalid_hash_raises_error(self):
        from app.auth import _validate_telegram_init_data

        init_data = "user=%7B%22id%22%3A12345%7D&hash=wrong_hash"
        with pytest.raises(ValueError, match="Invalid initData signature"):
            _validate_telegram_init_data(init_data, "bot_token")