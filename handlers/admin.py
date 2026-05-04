from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import admin_access_kb, admin_back_kb, admin_logs_kb, admin_menu_kb, admin_users_kb
from states import AdminStates


router = Router()


def is_admin(user_id: int, config) -> bool:
    return user_id in config.admins


def parse_id(text: str) -> int | None:
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return None


async def deny_if_not_admin(event, config) -> bool:
    user = getattr(event, "from_user", None)
    if not user or not is_admin(user.id, config):
        return True
    return False


def admin_menu_text() -> str:
    return "🛡 <b>Админ-панель</b>\n\nВыберите раздел управления."


@router.message(Command("admin"))
async def admin_cmd(message: Message, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    await db.add_log(message.from_user.id, "admin_opened")
    await message.answer(admin_menu_text(), reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await db.add_log(callback.from_user.id, "admin_opened")
    await callback.message.edit_text(admin_menu_text(), reply_markup=admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await callback.message.edit_text("👥 <b>Пользователи</b>\n\nУправление доступом и карточками пользователей.", reply_markup=admin_users_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_user_add")
async def admin_user_add(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_add_user)
    await callback.message.edit_text("➕ Введите user_id для добавления.", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.message(AdminStates.waiting_add_user)
async def admin_user_add_save(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    user_id = parse_id(message.text)
    if user_id is None:
        await message.answer("Введите числовой user_id.", reply_markup=admin_back_kb("admin_users"))
        return
    if await db.count_allowed_users() >= config.max_users and not await db.is_allowed_user(user_id):
        await message.answer(f"Лимит пользователей достигнут: {config.max_users}.", reply_markup=admin_back_kb("admin_users"))
        await state.clear()
        return
    await db.add_allowed_user(user_id)
    await db.add_log(message.from_user.id, f"admin_add_user:{user_id}")
    await state.clear()
    await message.answer(f"✅ Пользователь <code>{user_id}</code> добавлен.", reply_markup=admin_users_kb())


@router.message(Command("adduser"))
async def adduser_cmd(message: Message, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    parts = message.text.split(maxsplit=1)
    user_id = parse_id(parts[1]) if len(parts) > 1 else None
    if user_id is None:
        await message.answer("Использование: <code>/adduser ID</code>")
        return
    if await db.count_allowed_users() >= config.max_users and not await db.is_allowed_user(user_id):
        await message.answer(f"Лимит пользователей достигнут: {config.max_users}.")
        return
    await db.add_allowed_user(user_id)
    await db.add_log(message.from_user.id, f"admin_add_user:{user_id}")
    await message.answer(f"✅ Пользователь <code>{user_id}</code> добавлен.")


@router.callback_query(F.data == "admin_user_delete")
async def admin_user_delete(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_delete_user)
    await callback.message.edit_text("➖ Введите user_id для удаления из доступа.", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.message(AdminStates.waiting_delete_user)
async def admin_user_delete_save(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    user_id = parse_id(message.text)
    if user_id is None:
        await message.answer("Введите числовой user_id.", reply_markup=admin_back_kb("admin_users"))
        return
    await db.delete_allowed_user(user_id)
    await db.add_log(message.from_user.id, f"admin_delete_user:{user_id}")
    await state.clear()
    await message.answer(f"🗑 Пользователь <code>{user_id}</code> удален из доступа.", reply_markup=admin_users_kb())


@router.message(Command("deluser"))
async def deluser_cmd(message: Message, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    parts = message.text.split(maxsplit=1)
    user_id = parse_id(parts[1]) if len(parts) > 1 else None
    if user_id is None:
        await message.answer("Использование: <code>/deluser ID</code>")
        return
    await db.delete_allowed_user(user_id)
    await db.add_log(message.from_user.id, f"admin_delete_user:{user_id}")
    await message.answer(f"🗑 Пользователь <code>{user_id}</code> удален из доступа.")


@router.callback_query(F.data == "admin_user_list")
async def admin_user_list(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    users = await db.get_allowed_users()
    if not users:
        body = "Список доступа пуст."
    else:
        rows = []
        for user in users[:50]:
            status = "⛔ ban" if user["is_banned"] else "✅ ok"
            mon = "🟢" if user["monitoring_enabled"] else "⚪"
            rows.append(f"{status} {mon} <code>{user['user_id']}</code>")
        body = "\n".join(rows)
    await callback.message.edit_text(f"📋 <b>Список пользователей</b>\n\n{body}", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.callback_query(F.data == "admin_user_view")
async def admin_user_view(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_view_user)
    await callback.message.edit_text("🔎 Введите user_id для просмотра.", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.message(AdminStates.waiting_view_user)
async def admin_user_view_show(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    user_id = parse_id(message.text)
    if user_id is None:
        await message.answer("Введите числовой user_id.", reply_markup=admin_back_kb("admin_users"))
        return
    await state.clear()
    await message.answer(await user_card_text(db, user_id), reply_markup=admin_users_kb())


async def user_card_text(db, user_id: int) -> str:
    user = await db.get_user_details(user_id)
    if not user:
        return f"Пользователь <code>{user_id}</code> еще не запускал бота."
    price = "без лимита" if user["max_price"] is None else f"{user['max_price']:.2f}$"
    return (
        "👤 <b>Пользователь</b>\n\n"
        f"user_id: <code>{user['user_id']}</code>\n"
        f"Доступ: <b>{'забанен' if user['is_banned'] else 'разрешен' if user['allowed_at'] else 'не в whitelist'}</b>\n"
        f"Мониторинг: <b>{'включен' if user['monitoring_enabled'] else 'выключен'}</b>\n"
        f"Max price: <b>{price}</b>\n"
        f"Интервал: <b>{user['interval_seconds']} сек</b>\n"
        f"Стран выбрано: <b>{user['countries_count']}</b>\n"
        f"Алертов получил: <b>{user['alerts_count']}</b>\n"
        f"Дата регистрации: <b>{user['created_at']}</b>"
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    stat = await db.get_global_stats()
    top = await db.get_top_alert_users()
    top_text = "\n".join(f"{i}. <code>{u['user_id']}</code> — {u['alerts_count']}" for i, u in enumerate(top, 1)) or "пока пусто"
    await callback.message.edit_text(
        "📊 <b>Общая статистика</b>\n\n"
        f"Всего пользователей: <b>{stat['total_users']}</b>\n"
        f"Активных: <b>{stat['active_users']}</b>\n"
        f"Проверок всего: <b>{stat['total_checks']}</b>\n"
        f"Алертов всего: <b>{stat['total_alerts']}</b>\n\n"
        f"<b>Топ по алертам</b>\n{top_text}",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_access")
async def admin_access(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    enabled = await db.whitelist_enabled()
    count = await db.count_allowed_users()
    await callback.message.edit_text(
        "🔐 <b>Управление доступом</b>\n\n"
        f"Whitelist: <b>{'включен' if enabled else 'выключен'}</b>\n"
        f"Разрешенных пользователей: <b>{count}/{config.max_users}</b>",
        reply_markup=admin_access_kb(enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_whitelist_toggle")
async def admin_whitelist_toggle(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    enabled = not await db.whitelist_enabled()
    await db.set_whitelist_enabled(enabled)
    await db.add_log(callback.from_user.id, f"admin_whitelist:{'on' if enabled else 'off'}")
    await admin_access(callback, config, db)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_ask(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text("📣 Введите сообщение для рассылки.", reply_markup=admin_back_kb("admin_access"))
    await callback.answer()


@router.message(Command("broadcast"))
async def broadcast_cmd(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    text = message.text.split(maxsplit=1)
    if len(text) > 1:
        await run_broadcast(message, text[1], db)
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await message.answer("📣 Введите сообщение для рассылки.", reply_markup=admin_back_kb("admin_access"))


@router.message(AdminStates.waiting_broadcast)
async def broadcast_save(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    await state.clear()
    await run_broadcast(message, message.html_text, db)


async def run_broadcast(message: Message, text: str, db) -> None:
    sent = 0
    failed = 0
    users = await db.get_broadcast_users()
    for user_id in users:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await db.add_log(message.from_user.id, f"admin_broadcast:sent={sent}:failed={failed}")
    await message.answer(f"📣 Рассылка завершена.\n\nОтправлено: <b>{sent}</b>\nОшибок: <b>{failed}</b>", reply_markup=admin_access_kb(await db.whitelist_enabled()))


@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await callback.message.edit_text("📈 <b>Логи / Активность</b>\n\nВыберите тип журнала.", reply_markup=admin_logs_kb())
    await callback.answer()


@router.callback_query(F.data.in_({"admin_logs_actions", "admin_logs_alerts", "admin_logs_autobuy", "admin_logs_api_errors"}))
async def admin_logs_show(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    patterns = {
        "admin_logs_actions": None,
        "admin_logs_alerts": "alert_sent:%",
        "admin_logs_autobuy": "autobuy_%",
        "admin_logs_api_errors": "api_error:%",
    }
    logs = await db.get_logs(20, patterns[callback.data])
    body = "\n".join(f"{log['created_at']} · <code>{log['user_id']}</code> · {log['action']}" for log in logs) or "Записей пока нет."
    await callback.message.edit_text(f"📈 <b>Последние записи</b>\n\n{body}", reply_markup=admin_logs_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery, config, db) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    enabled = await db.whitelist_enabled()
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\n"
        f"Whitelist: <b>{'включен' if enabled else 'выключен'}</b>\n"
        f"Лимит пользователей: <b>{config.max_users}</b>\n"
        f"Админов: <b>{len(config.admins)}</b>",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_user_ban")
async def admin_user_ban(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_ban_user)
    await callback.message.edit_text("⛔ Введите user_id для бана.", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.message(AdminStates.waiting_ban_user)
async def admin_user_ban_save(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    user_id = parse_id(message.text)
    if user_id is None:
        await message.answer("Введите числовой user_id.", reply_markup=admin_back_kb("admin_users"))
        return
    await db.ban_user(user_id)
    await db.add_log(message.from_user.id, f"admin_ban_user:{user_id}")
    await state.clear()
    await message.answer(f"⛔ Пользователь <code>{user_id}</code> заблокирован.", reply_markup=admin_users_kb())


@router.callback_query(F.data == "admin_user_unban")
async def admin_user_unban(callback: CallbackQuery, state: FSMContext, config) -> None:
    if await deny_if_not_admin(callback, config):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_unban_user)
    await callback.message.edit_text("✅ Введите user_id для разбана.", reply_markup=admin_back_kb("admin_users"))
    await callback.answer()


@router.message(AdminStates.waiting_unban_user)
async def admin_user_unban_save(message: Message, state: FSMContext, config, db) -> None:
    if await deny_if_not_admin(message, config):
        return
    user_id = parse_id(message.text)
    if user_id is None:
        await message.answer("Введите числовой user_id.", reply_markup=admin_back_kb("admin_users"))
        return
    await db.unban_user(user_id)
    await db.add_log(message.from_user.id, f"admin_unban_user:{user_id}")
    await state.clear()
    await message.answer(f"✅ Пользователь <code>{user_id}</code> разблокирован.", reply_markup=admin_users_kb())
