from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Required environment variable '{key}' is not set. Check your .env file.")
    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    check_interval: int
    db_path: Path


def load_config() -> Config:
    db_path = Path(os.getenv("DB_PATH", "data/monitor.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=_require("BOT_TOKEN"),
        admin_id=int(_require("ADMIN_ID")),
        api_id=int(_require("API_ID")),
        api_hash=_require("API_HASH"),
        phone=_require("PHONE"),
        session_name=os.getenv("SESSION_NAME", "monitor_session"),
        check_interval=int(os.getenv("CHECK_INTERVAL", "300")),
        db_path=db_path,
    )


config = load_config()
