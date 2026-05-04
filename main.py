import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from api_client import TGLionClient
from config import load_config
from database import Database
from handlers import setup_routers
from services.monitor import MonitorService
from services.tg_account_monitor import TgAccountMonitorService


class AppMiddleware:
    def __init__(self, db: Database, tg_lion: TGLionClient, config, tg_account_monitor: TgAccountMonitorService) -> None:
        self.db = db
        self.tg_lion = tg_lion
        self.config = config
        self.tg_account_monitor = tg_account_monitor

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        data["tg_lion"] = self.tg_lion
        data["config"] = self.config
        data["tg_account_monitor"] = self.tg_account_monitor
        return await handler(event, data)


class AccessMiddleware:
    def __init__(self, db: Database, config) -> None:
        self.db = db
        self.config = config

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)
        if user.id in self.config.admins:
            return await handler(event, data)

        banned = await self.db.is_banned_user(user.id)
        whitelist_enabled = await self.db.whitelist_enabled()
        allowed = not banned and (not whitelist_enabled or await self.db.is_allowed_user(user.id))
        if allowed:
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            await event.answer("⛔ Нет доступа. Обратитесь к администратору.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ Нет доступа.")
        return None


async def ignore_message_not_modified(handler, event, data):
    try:
        return await handler(event, data)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            if hasattr(event, "answer"):
                await event.answer()
            return None
        raise


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    config = load_config()
    db = Database(config.database_path)
    await db.init()

    tg_lion = TGLionClient(config.tg_lion_base_url, config.http_timeout)
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    tg_account_monitor = TgAccountMonitorService(bot, db, config)
    app_middleware = AppMiddleware(db, tg_lion, config, tg_account_monitor)
    access_middleware = AccessMiddleware(db, config)
    dp.update.outer_middleware(app_middleware)
    dp.message.middleware(access_middleware)
    dp.callback_query.middleware(access_middleware)
    dp.errors.middleware(ignore_message_not_modified)
    dp.include_router(setup_routers())

    monitor = MonitorService(bot, db, tg_lion, config.alert_cooldown_seconds)
    monitor.start()
    await tg_account_monitor.start()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await monitor.stop()
        await tg_account_monitor.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
