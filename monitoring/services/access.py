import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import config
from db import get_db

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """
    Checks every update against the whitelist.
    Admin always passes. Unregistered / banned / not-allowed users are rejected.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Admin bypasses all checks
        if user.id == config.admin_id:
            return await handler(event, data)

        db = await get_db()

        # Auto-register on first contact
        await db.upsert_user(user.id, user.username, user.first_name, user.last_name)

        allowed = await db.is_allowed(user.id)
        if not allowed:
            text = (
                "🔒 <b>Доступ закрыт.</b>\n\n"
                "Этот бот работает только по приглашению.\n"
                f"Ваш ID: <code>{user.id}</code>\n\n"
                "Обратитесь к администратору для получения доступа."
            )
            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("🔒 Доступ закрыт.", show_alert=True)
            return  # stop propagation

        return await handler(event, data)
