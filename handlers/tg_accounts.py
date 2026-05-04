from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import (
    back_kb,
    tg_account_detail_kb,
    tg_accounts_list_kb,
    tg_accounts_menu_kb,
)
from states import TgAccountsStates

router = Router()
MIN_INTERVAL = 15
MAX_INTERVAL = 3600


def _account_text(account: dict) -> str:
    return (
        f"👤 <b>{account['target_label']}</b>\n\n"
        f"Имя: {account['display_name'] or '—'}\n"
        f"ID: {account['target_id'] or '—'}\n"
        f"Bio: {(account['bio'] or '—')[:120]}\n"
        f"Статус: {'🟢 активен' if account['is_active'] else '⏸ пауза'}\n"
        f"Последняя проверка: {account['last_checked_at'] or 'ещё не проверялся'}"
    )


async def _menu_text(db, user_id: int) -> str:
    interval = await db.get_user_tg_accounts_interval(user_id)
    accounts = await db.get_user_tg_monitored_accounts(user_id)
    active = sum(1 for item in accounts if item["is_active"])
    return (
        "👤 <b>Мониторинг TG акков</b>\n\n"
        f"Всего аккаунтов: <b>{len(accounts)}</b>\n"
        f"Активных: <b>{active}</b>\n"
        f"Задержка проверки: <b>{interval} сек</b>\n\n"
        "Здесь можно добавить username/ID и управлять мониторингом профилей."
    )


@router.callback_query(F.data == "tg_accounts_menu")
async def tg_accounts_menu(callback: CallbackQuery, db, tg_account_monitor) -> None:
    if not tg_account_monitor.enabled:
        missing = ", ".join(tg_account_monitor.missing_config_fields()) or "unknown"
        await callback.message.edit_text(
            "⚠️ Мониторинг TG-аккаунтов недоступен.\n\n"
            "Добавьте в .env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE.\n\n"
            f"Не найдено на сервере: <code>{missing}</code>",
            reply_markup=back_kb("main_menu"),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        await _menu_text(db, callback.from_user.id),
        reply_markup=tg_accounts_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "tg_accounts_add")
async def tg_accounts_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TgAccountsStates.waiting_identifier)
    await callback.message.edit_text(
        "➕ Введите @username или числовой user_id.\n\n"
        "Примеры: <code>@durov</code>, <code>durov</code>, <code>777000</code>",
        reply_markup=back_kb("tg_accounts_menu"),
    )
    await callback.answer()


@router.message(TgAccountsStates.waiting_identifier)
async def tg_accounts_add_save(message: Message, state: FSMContext, db, tg_account_monitor) -> None:
    identifier, label = tg_account_monitor.parse_identifier(message.text or "")
    if identifier is None:
        await message.answer("Неверный формат. Введите @username или числовой ID.", reply_markup=back_kb("tg_accounts_menu"))
        return

    status = await message.answer(f"🔍 Ищу аккаунт <b>{label}</b>...")
    snapshot = await tg_account_monitor.get_profile(identifier)
    if snapshot is None:
        await status.edit_text(
            "❌ Аккаунт не найден/недоступен.\n\n"
            "Проверьте username/ID и что userbot видит этот аккаунт.",
            reply_markup=back_kb("tg_accounts_menu"),
        )
        return

    target_username = snapshot.username
    target_label = f"@{target_username}" if target_username else f"ID:{snapshot.target_id}"
    created_id = await db.add_tg_monitored_account(
        owner_id=message.from_user.id,
        target_label=target_label,
        target_username=target_username,
        target_id=snapshot.target_id,
        display_name=snapshot.display_name,
        bio=snapshot.bio,
        photo_hash=snapshot.photo_hash,
    )
    await state.clear()
    if created_id is None:
        await status.edit_text("⚠️ Этот аккаунт уже есть в вашем мониторинге.", reply_markup=back_kb("tg_accounts_menu"))
        return

    await status.edit_text(
        "✅ Аккаунт добавлен в мониторинг.\n\n"
        f"Аккаунт: <b>{target_label}</b>\n"
        f"Имя: {snapshot.display_name or '—'}\n"
        f"ID: {snapshot.target_id or '—'}",
        reply_markup=back_kb("tg_accounts_menu"),
    )


@router.callback_query(F.data == "tg_accounts_list")
async def tg_accounts_list(callback: CallbackQuery, db) -> None:
    accounts = await db.get_user_tg_monitored_accounts(callback.from_user.id)
    if not accounts:
        await callback.message.edit_text("Список пуст. Добавьте аккаунт через меню.", reply_markup=back_kb("tg_accounts_menu"))
        await callback.answer()
        return
    await callback.message.edit_text(
        "📋 <b>Ваши TG-аккаунты</b>\n\nВыберите аккаунт:",
        reply_markup=tg_accounts_list_kb(accounts),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tg_accounts_open:"))
async def tg_accounts_open(callback: CallbackQuery, db) -> None:
    account_id = int(callback.data.split(":")[1])
    account = await db.get_tg_monitored_account(callback.from_user.id, account_id)
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return
    await callback.message.edit_text(_account_text(account), reply_markup=tg_account_detail_kb(account_id, bool(account["is_active"])))
    await callback.answer()


@router.callback_query(F.data.startswith("tg_accounts_toggle:"))
async def tg_accounts_toggle(callback: CallbackQuery, db) -> None:
    account_id = int(callback.data.split(":")[1])
    new_state = await db.toggle_tg_monitored_account(callback.from_user.id, account_id)
    if new_state is None:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return
    account = await db.get_tg_monitored_account(callback.from_user.id, account_id)
    if account:
        await callback.message.edit_text(_account_text(account), reply_markup=tg_account_detail_kb(account_id, bool(account["is_active"])))
    await callback.answer("Включено" if new_state else "Поставлено на паузу")


@router.callback_query(F.data.startswith("tg_accounts_delete:"))
async def tg_accounts_delete(callback: CallbackQuery, db) -> None:
    account_id = int(callback.data.split(":")[1])
    deleted = await db.delete_tg_monitored_account(callback.from_user.id, account_id)
    if not deleted:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return
    await callback.message.edit_text("🗑 Аккаунт удален из мониторинга.", reply_markup=back_kb("tg_accounts_menu"))
    await callback.answer()


@router.callback_query(F.data == "tg_accounts_interval")
async def tg_accounts_interval(callback: CallbackQuery, state: FSMContext, db) -> None:
    current = await db.get_user_tg_accounts_interval(callback.from_user.id)
    await state.set_state(TgAccountsStates.waiting_interval)
    await callback.message.edit_text(
        "⏱️ Введите задержку проверки TG-акков в секундах.\n\n"
        f"Текущая: <b>{current} сек</b>\n"
        f"Диапазон: {MIN_INTERVAL}-{MAX_INTERVAL}.",
        reply_markup=back_kb("tg_accounts_menu"),
    )
    await callback.answer()


@router.message(TgAccountsStates.waiting_interval)
async def tg_accounts_interval_save(message: Message, state: FSMContext, db) -> None:
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число секунд.", reply_markup=back_kb("tg_accounts_menu"))
        return
    if value < MIN_INTERVAL or value > MAX_INTERVAL:
        await message.answer(
            f"Допустимо от {MIN_INTERVAL} до {MAX_INTERVAL} секунд.",
            reply_markup=back_kb("tg_accounts_menu"),
        )
        return
    await db.set_user_tg_accounts_interval(message.from_user.id, value)
    await state.clear()
    await message.answer(
        f"✅ Задержка проверки обновлена: <b>{value} сек</b>.",
        reply_markup=tg_accounts_menu_kb(),
    )
