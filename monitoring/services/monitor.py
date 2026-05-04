import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

import aiohttp
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UsernameNotOccupiedError, UsernameInvalidError
from telethon.tl.functions.users import GetFullUserRequest, GetUsersRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.types import InputUserFromMessage, InputPeerEmpty

from config import config
from db import get_db

logger = logging.getLogger(__name__)

_OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]*)"', re.I)
_OG_DESC_RE  = re.compile(r'<meta\s+property="og:description"\s+content="([^"]*)"', re.I)
_OG_IMAGE_RE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]*)"', re.I)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
         .replace("&quot;", '"').replace("&#39;", "'").strip()
    )


def _url_hash(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return hashlib.md5(url.split("?")[0].encode()).hexdigest()


async def _fetch_tme_profile(username: str) -> dict:
    """Скрапит t.me/{username} — обходит privacy настройки API."""
    result = {"display_name": None, "bio": None, "photo_url": None}
    try:
        async with aiohttp.ClientSession(headers=_HTTP_HEADERS) as session:
            async with session.get(
                f"https://t.me/{username}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return result
                html = await resp.text(encoding="utf-8", errors="ignore")

        m = _OG_TITLE_RE.search(html)
        if m:
            result["display_name"] = _unescape(m.group(1)) or None
        m = _OG_DESC_RE.search(html)
        if m:
            result["bio"] = _unescape(m.group(1)) or None
        m = _OG_IMAGE_RE.search(html)
        if m:
            result["photo_url"] = m.group(1) or None

        logger.debug(
            "t.me scrape @%s -> name=%r bio=%r photo=%s",
            username, result["display_name"], result["bio"],
            "yes" if result["photo_url"] else "no",
        )
    except Exception as e:
        logger.warning("t.me scrape failed for @%s: %s", username, e)
    return result


@dataclass
class ProfileSnapshot:
    username: Optional[str]
    target_id: Optional[int]
    display_name: Optional[str]
    bio: Optional[str]
    photo_hash: Optional[str]


class MonitorClient:
    def __init__(self) -> None:
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._client = TelegramClient(config.session_name, config.api_id, config.api_hash)
        await self._client.start(phone=config.phone)
        logger.info("Telethon userbot started.")

    async def stop(self) -> None:
        if self._client:
            await self._client.disconnect()
            logger.info("Telethon userbot disconnected.")

    async def _resolve_entity(self, identifier: Union[str, int]):
        """
        Резолвит identifier в Telethon entity.
        Для int (user_id) пробует несколько способов.
        """
        if isinstance(identifier, str):
            return await self._client.get_entity(identifier.lstrip("@"))

        # --- int user_id ---
        # Способ 1: из кэша сессии (работает если видели раньше)
        try:
            return await self._client.get_entity(identifier)
        except Exception:
            pass

        # Способ 2: поиск по контактам и диалогам
        try:
            async for dialog in self._client.iter_dialogs():
                ent = dialog.entity
                if getattr(ent, "id", None) == identifier:
                    return ent
        except Exception:
            pass

        # Способ 3: поиск в участниках общих каналов/чатов
        # (работает если userbot состоит в каналах где есть этот юзер)
        try:
            from telethon.tl.functions.contacts import ResolvePhoneRequest
        except ImportError:
            pass

        raise ValueError(f"Cannot resolve user_id={identifier}. "
                         f"Userbot must share a chat with this user.")

    async def get_profile(self, identifier: Union[str, int]) -> Optional[ProfileSnapshot]:
        if not self._client:
            raise RuntimeError("MonitorClient not started.")

        async with self._lock:
            try:
                entity = await self._resolve_entity(identifier)
                full = await self._client(GetFullUserRequest(entity))
                user = full.users[0]

                # Имя
                parts = [user.first_name or "", user.last_name or ""]
                api_name = " ".join(p for p in parts if p).strip() or None

                # Bio
                api_bio = (full.full_user.about or "").strip() or None

                # Фото
                api_photo_hash: Optional[str] = None
                try:
                    photos_result = await self._client(
                        GetUserPhotosRequest(user.id, offset=0, max_id=0, limit=1)
                    )
                    if photos_result.photos:
                        api_photo_hash = hashlib.md5(
                            str(photos_result.photos[0].id).encode()
                        ).hexdigest()
                except Exception as e:
                    logger.debug("GetUserPhotosRequest failed for %r: %s", identifier, e)
                    if user.photo and hasattr(user.photo, "photo_id"):
                        api_photo_hash = hashlib.md5(
                            str(user.photo.photo_id).encode()
                        ).hexdigest()

                # t.me scraping — только если есть username
                tme = {"display_name": None, "bio": None, "photo_url": None}
                if user.username:
                    tme = await _fetch_tme_profile(user.username)

                display_name = api_name or tme["display_name"]
                bio          = api_bio  or tme["bio"]
                photo_hash   = api_photo_hash or _url_hash(tme["photo_url"])

                return ProfileSnapshot(
                    username=user.username,   # None если убрал username
                    target_id=user.id,
                    display_name=display_name,
                    bio=bio,
                    photo_hash=photo_hash,
                )

            except FloodWaitError as e:
                logger.warning("FloodWait: sleeping %d seconds", e.seconds)
                await asyncio.sleep(e.seconds)
                return None
            except (UsernameNotOccupiedError, UsernameInvalidError):
                logger.warning("Identifier %r not found or invalid.", identifier)
                return None
            except Exception as exc:
                logger.error("Error fetching profile for %r: %s", identifier, exc)
                return None


monitor_client = MonitorClient()


async def run_monitoring_loop(bot) -> None:
    logger.info("Monitoring loop started. Interval: %d seconds.", config.check_interval)
    while True:
        try:
            await _check_all_accounts(bot)
        except Exception as exc:
            logger.exception("Unhandled error in monitoring loop: %s", exc)
        await asyncio.sleep(config.check_interval)


async def _check_all_accounts(bot) -> None:
    db = await get_db()
    accounts = await db.get_all_active_monitored()
    if not accounts:
        return
    logger.info("Checking %d monitored account(s)...", len(accounts))
    for acc in accounts:
        try:
            await _check_single_account(bot, db, acc)
        except Exception as exc:
            logger.error(
                "Error checking account id=%d (%s): %s",
                acc["id"], acc["target_username"] or acc["target_id"], exc,
            )
        await asyncio.sleep(2)


async def _check_single_account(bot, db, acc) -> None:
    account_id: int  = acc["id"]
    owner_id: int    = acc["owner_id"]
    stored_username: str = acc["target_username"]  # может быть "" или "12345" (ID)

    # Предпочитаем числовой ID — он стабилен при смене username
    identifier: Union[str, int] = acc["target_id"] if acc["target_id"] else stored_username

    snapshot = await monitor_client.get_profile(identifier)
    if snapshot is None:
        logger.warning("Could not fetch snapshot for %r", identifier)
        return

    # Нормализуем: None → "" для единообразного сравнения
    new_username = (snapshot.username or "").lower()

    logger.info(
        "[DEBUG] %r | username: %r->%r | name: %r->%r | bio: %r->%r | photo: %r->%r",
        identifier,
        stored_username, new_username,
        acc["display_name"], snapshot.display_name,
        acc["bio"], snapshot.bio,
        acc["photo_hash"], snapshot.photo_hash,
    )

    changes: dict = {}

    # ── Username: сравниваем всегда, включая случай когда стал "" ────────────
    # stored_username может быть числовой строкой если добавляли по ID
    stored_is_id = stored_username.isdigit()
    if not stored_is_id:
        # Был username — проверяем изменение или удаление
        if new_username != stored_username:
            old_label = f"@{stored_username}"
            new_label = f"@{new_username}" if new_username else "(удалён)"
            changes["Username"] = (old_label, new_label)

    # ── Имя ──────────────────────────────────────────────────────────────────
    if snapshot.display_name != acc["display_name"]:
        changes["Имя"] = (acc["display_name"], snapshot.display_name)

    # ── Bio ───────────────────────────────────────────────────────────────────
    if snapshot.bio != acc["bio"]:
        changes["Bio"] = (acc["bio"], snapshot.bio)

    # ── Фото ─────────────────────────────────────────────────────────────────
    if snapshot.photo_hash != acc["photo_hash"]:
        changes["Фото профиля"] = (
            "(было)",
            "(изменено)" if snapshot.photo_hash else "(удалено)",
        )

    # Обновляем username в БД даже если он стал пустым
    final_username = new_username or stored_username

    if not changes:
        logger.info("[DEBUG] %r -- изменений нет", identifier)
        await db.update_monitored_state(
            account_id, final_username,
            snapshot.target_id, snapshot.display_name,
            snapshot.bio, snapshot.photo_hash,
        )
        return

    for field, (old_val, new_val) in changes.items():
        await db.log_change(account_id, field, str(old_val), str(new_val))

    await db.update_monitored_state(
        account_id, final_username,
        snapshot.target_id, snapshot.display_name,
        snapshot.bio, snapshot.photo_hash,
    )

    changes_lines = "\n".join(
        f"  • {field}: {old or '—'} → {new or '—'}"
        for field, (old, new) in changes.items()
    )
    display_label = f"@{stored_username}" if not stored_is_id else f"ID:{stored_username}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        "📌 <b>Изменение профиля обнаружено</b>\n\n"
        f"👤 Аккаунт: <b>{display_label}</b>\n"
        f"🔄 <b>Изменения:</b>\n{changes_lines}\n\n"
        f"⏰ Время: {timestamp}"
    )

    try:
        await bot.send_message(owner_id, text, parse_mode="HTML")
        logger.info(
            "Notified user %d about changes in %s: %s",
            owner_id, display_label, list(changes.keys()),
        )
    except Exception as exc:
        logger.error("Failed to send notification to user %d: %s", owner_id, exc)
