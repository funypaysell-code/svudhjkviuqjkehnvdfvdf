from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp
from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.functions.users import GetFullUserRequest

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^@?[a-zA-Z0-9_]{3,32}$")
USERID_RE = re.compile(r"^\d{5,15}$")

_OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]*)"', re.I)
_OG_DESC_RE = re.compile(r'<meta\s+property="og:description"\s+content="([^"]*)"', re.I)
_OG_IMAGE_RE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]*)"', re.I)
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(slots=True)
class ProfileSnapshot:
    target_id: int | None
    username: str | None
    display_name: str | None
    bio: str | None
    photo_hash: str | None


def parse_identifier(raw: str) -> tuple[str | int | None, str]:
    text = (raw or "").strip()
    if USERID_RE.match(text):
        identifier = int(text)
        return identifier, f"ID:{identifier}"
    if USERNAME_RE.match(text):
        username = text.lstrip("@").lower()
        return username, f"@{username}"
    return None, text


def _unescape_html(value: str) -> str:
    return (
        value.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .strip()
    )


def _url_hash(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return hashlib.md5(url.split("?")[0].encode()).hexdigest()


class TgAccountMonitorService:
    def __init__(self, bot: Bot, db, config) -> None:
        self.bot = bot
        self.db = db
        self.config = config
        self._client: TelegramClient | None = None
        self._task: asyncio.Task | None = None
        self._next_check: dict[int, float] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.config.telegram_api_id and self.config.telegram_api_hash and self.config.telegram_phone)

    def missing_config_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.config.telegram_api_id:
            missing.append("TELEGRAM_API_ID")
        if not self.config.telegram_api_hash:
            missing.append("TELEGRAM_API_HASH")
        if not self.config.telegram_phone:
            missing.append("TELEGRAM_PHONE")
        return missing

    @staticmethod
    def parse_identifier(raw: str) -> tuple[str | int | None, str]:
        return parse_identifier(raw)

    async def start(self) -> None:
        if not self.enabled:
            missing = ",".join(self.missing_config_fields()) or "unknown"
            logger.warning("TG account monitor disabled. Missing env: %s", missing)
            return
        self._client = TelegramClient(
            self.config.telegram_session_name,
            self.config.telegram_api_id,
            self.config.telegram_api_hash,
        )
        await self._client.start(phone=self.config.telegram_phone)
        self._task = asyncio.create_task(self._run(), name="tg-account-monitor")
        logger.info("TG account monitor started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.disconnect()

    async def get_profile(self, identifier: str | int) -> ProfileSnapshot | None:
        if not self._client:
            return None
        async with self._lock:
            try:
                entity = await self._client.get_entity(identifier)
                full = await self._client(GetFullUserRequest(entity))
                user = full.users[0]
                username = user.username.lower() if user.username else None

                parts = [user.first_name or "", user.last_name or ""]
                api_name = " ".join(p for p in parts if p).strip() or None
                api_bio = (full.full_user.about or "").strip() or None

                photo_hash = None
                try:
                    photos = await self._client(GetUserPhotosRequest(user.id, offset=0, max_id=0, limit=1))
                    if photos.photos:
                        photo_hash = hashlib.md5(str(photos.photos[0].id).encode()).hexdigest()
                except Exception:
                    if user.photo and hasattr(user.photo, "photo_id"):
                        photo_hash = hashlib.md5(str(user.photo.photo_id).encode()).hexdigest()

                tme_name = None
                tme_bio = None
                tme_photo_hash = None
                if username:
                    tme_name, tme_bio, tme_photo_hash = await self._fetch_tme_data(username)

                return ProfileSnapshot(
                    target_id=user.id,
                    username=username,
                    display_name=api_name or tme_name,
                    bio=api_bio or tme_bio,
                    photo_hash=photo_hash or tme_photo_hash,
                )
            except FloodWaitError as exc:
                await asyncio.sleep(exc.seconds)
                return None
            except (UsernameInvalidError, UsernameNotOccupiedError, ValueError):
                return None
            except Exception:
                logger.exception("Failed to get profile for %r", identifier)
                return None

    async def _fetch_tme_data(self, username: str) -> tuple[str | None, str | None, str | None]:
        try:
            async with aiohttp.ClientSession(headers=_HTTP_HEADERS) as session:
                async with session.get(
                    f"https://t.me/{username}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return None, None, None
                    html = await response.text(encoding="utf-8", errors="ignore")
        except Exception:
            return None, None, None

        name_match = _OG_TITLE_RE.search(html)
        bio_match = _OG_DESC_RE.search(html)
        image_match = _OG_IMAGE_RE.search(html)
        name = _unescape_html(name_match.group(1)) if name_match else None
        bio = _unescape_html(bio_match.group(1)) if bio_match else None
        photo_hash = _url_hash(image_match.group(1) if image_match else None)
        return name, bio, photo_hash

    async def _run(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("TG account monitor tick failed")
            await asyncio.sleep(1)

    async def _tick(self) -> None:
        now = asyncio.get_running_loop().time()
        accounts = await self.db.get_all_active_tg_monitored_accounts()
        active_ids = {item["id"] for item in accounts}
        for account_id in list(self._next_check):
            if account_id not in active_ids:
                self._next_check.pop(account_id, None)

        for account in accounts:
            account_id = account["id"]
            if now < self._next_check.get(account_id, 0):
                continue
            interval = max(15, int(account.get("tg_accounts_interval_seconds") or 60))
            self._next_check[account_id] = now + interval
            await self._check_account(account)

    async def _check_account(self, account: dict) -> None:
        identifier = account.get("target_id") or account.get("target_username") or account["target_label"]
        snapshot = await self.get_profile(identifier)
        if snapshot is None:
            return

        old_username = account.get("target_username") or None
        old_name = account.get("display_name")
        old_bio = account.get("bio")
        old_photo = account.get("photo_hash")

        new_username = snapshot.username
        new_label = f"@{new_username}" if new_username else f"ID:{snapshot.target_id}" if snapshot.target_id else account["target_label"]
        changes: list[tuple[str, str | None, str | None]] = []

        if old_username != new_username and old_username:
            changes.append(("Username", f"@{old_username}", f"@{new_username}" if new_username else "(удален)"))
        if old_name != snapshot.display_name:
            changes.append(("Имя", old_name, snapshot.display_name))
        if old_bio != snapshot.bio:
            changes.append(("Bio", old_bio, snapshot.bio))
        if old_photo != snapshot.photo_hash:
            changes.append(("Фото", "(было)", "(изменено)" if snapshot.photo_hash else "(удалено)"))

        await self.db.update_tg_monitored_snapshot(
            account_id=account["id"],
            target_label=new_label,
            target_username=new_username,
            target_id=snapshot.target_id,
            display_name=snapshot.display_name,
            bio=snapshot.bio,
            photo_hash=snapshot.photo_hash,
        )
        if not changes:
            return

        for field, old, new in changes:
            await self.db.add_tg_change_log(account["id"], field, old, new)

        lines = "\n".join(f"• {field}: {old or '—'} → {new or '—'}" for field, old, new in changes)
        await self.bot.send_message(
            account["owner_id"],
            "📌 <b>Изменение TG-аккаунта</b>\n\n"
            f"Аккаунт: <b>{new_label}</b>\n"
            f"{lines}",
        )
