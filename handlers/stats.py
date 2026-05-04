from aiogram import F, Router
from aiogram.types import CallbackQuery

from keyboards import main_menu_kb


router = Router()


@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    stat = await db.get_stats(callback.from_user.id)
    countries = await db.get_user_countries(callback.from_user.id)
    tracked = "все" if not countries else str(len(countries))
    price = "без лимита" if user.max_price is None else f"до {user.max_price:.2f}$"
    last_alert = stat["last_alert_at"] or "еще не было"

    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        f"Всего алертов: <b>{stat['alerts_count']}</b>\n"
        f"Последний алерт: <b>{last_alert}</b>\n"
        f"Проверок: <b>{stat['checks_count']}</b>\n"
        f"Мониторинг: <b>{'активен' if user.monitoring_enabled else 'выключен'}</b>\n"
        f"Стран отслеживается: <b>{tracked}</b>\n"
        f"Max price: <b>{price}</b>\n"
        f"Интервал: <b>{user.interval_seconds} сек</b>",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
