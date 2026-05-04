from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def parse_admins(value: str) -> tuple[int, ...]:
    admins: list[int] = []
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if item:
            admins.append(int(item))
    return tuple(admins)


ADMINS = parse_admins(os.getenv("ADMINS", ""))


@dataclass(frozen=True)
class Config:
    bot_token: str
    admins: tuple[int, ...]
    database_path: str = "bot.db"
    tg_lion_base_url: str = "https://TG-Lion.net"
    http_timeout: int = 15
    alert_cooldown_seconds: int = 300
    max_users: int = 100
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_phone: str | None = None
    telegram_session_name: str = "monitor_session"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Create .env from .env.example")

    return Config(
        bot_token=token,
        admins=ADMINS,
        database_path=os.getenv("DATABASE_PATH", "bot.db").strip() or "bot.db",
        tg_lion_base_url=os.getenv("TG_LION_BASE_URL", "https://TG-Lion.net").strip().rstrip("/"),
        http_timeout=int(os.getenv("HTTP_TIMEOUT", "15")),
        alert_cooldown_seconds=int(os.getenv("ALERT_COOLDOWN_SECONDS", "300")),
        max_users=int(os.getenv("MAX_USERS", "100")),
        telegram_api_id=int(os.getenv("TELEGRAM_API_ID")) if os.getenv("TELEGRAM_API_ID") else None,
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", "").strip() or None,
        telegram_phone=os.getenv("TELEGRAM_PHONE", "").strip() or None,
        telegram_session_name=os.getenv("TELEGRAM_SESSION_NAME", "monitor_session").strip() or "monitor_session",
    )
