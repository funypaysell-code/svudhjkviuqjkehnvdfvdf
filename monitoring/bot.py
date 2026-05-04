"""
Telegram Monitor Bot
Entry point — wires together Aiogram dispatcher, database, Telethon userbot
and the background monitoring loop.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from db.database import Database
from handlers import common_router, user_router, admin_router
from services.access import AccessMiddleware
from services.monitor import monitor_client, run_monitoring_loop

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

async def on_startup(bot: Bot, db: Database) -> None:
    await db.init()
    await monitor_client.start()
    logger.info("Bot started. Admin ID: %d", config.admin_id)

    # Notify admin on startup
    try:
        await bot.send_message(
            config.admin_id,
            "🟢 <b>Бот запущен!</b>\n\n"
            f"⏱ Интервал мониторинга: {config.check_interval // 60} мин.",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Could not send startup notification: %s", exc)


async def on_shutdown(bot: Bot, db: Database) -> None:
    logger.info("Shutting down…")
    await monitor_client.stop()
    await db.close()

    try:
        await bot.send_message(config.admin_id, "🔴 <b>Бот остановлен.</b>", parse_mode="HTML")
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware (runs before every handler)
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    # Routers (order matters: more specific first)
    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    db = Database(config.db_path)

    await on_startup(bot, db)

    # Start monitoring loop as a background task
    monitor_task = asyncio.create_task(run_monitoring_loop(bot))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        await on_shutdown(bot, db)


if __name__ == "__main__":
    asyncio.run(main())
