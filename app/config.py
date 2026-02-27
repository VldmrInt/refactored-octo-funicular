import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_config = load_config()

BOT_TOKEN: str = _config["bot_token"]
SECRET_KEY: str = _config["secret_key"]
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
