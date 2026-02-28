import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from jose import JWTError, jwt

from app.config import ADMIN_IDS, ALGORITHM, JWT_EXPIRE_HOURS, SECRET_KEY, SUPPORT_IDS


def _validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram WebApp initData via HMAC-SHA256.
    Returns parsed user dict if valid, raises ValueError otherwise.
    """
    # Parse raw pairs without URL-decoding values (required for correct HMAC)
    raw_params: dict[str, str] = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, _, v = part.partition("=")
            raw_params[k] = v

    received_hash = raw_params.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash in initData")

    if "user" not in raw_params:
        raise ValueError("Missing user field in initData")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(raw_params.items())
    )

    secret = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()

    expected_hash = hmac.new(
        secret,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid initData signature")

    return json.loads(unquote(raw_params["user"]))


def determine_role(telegram_id: int) -> str:
    if telegram_id in ADMIN_IDS:
        return "admin"
    if telegram_id in SUPPORT_IDS:
        return "support"
    return "author"


def create_jwt(user_id: int, telegram_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def validate_init_data(init_data: str) -> dict:
    from app.config import BOT_TOKEN
    return _validate_telegram_init_data(init_data, BOT_TOKEN)
