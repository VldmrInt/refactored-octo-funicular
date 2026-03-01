import secrets

import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found: {_CONFIG_PATH}\n"
            "Run: cp config.example.yaml config.yaml  and fill in your values,\n"
            "or run setup_config.sh to generate it interactively."
        )
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ensure_secret_key(config: dict) -> str:
    key = config.get("secret_key") or ""
    if key:
        return key
    key = secrets.token_hex(24)
    config["secret_key"] = key
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    return key


_config = load_config()

BOT_TOKEN: str = _config["bot_token"]
SECRET_KEY: str = _ensure_secret_key(_config)
ADMIN_IDS: list[int] = _config["roles"].get("admins", [])
SUPPORT_IDS: list[int] = _config["roles"].get("support", [])

ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
FORBIDDEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".msi",
    ".ps1", ".vbs", ".app", ".bin", ".dll", ".com",
}
