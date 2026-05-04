import logging
import re

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from db import get_db
from services.monitor import monitor_client
from states import AddAccountForm
from utils import (
    main_menu_kb,
    monitors_list_kb,
    monitor_detail_kb,
    cancel_kb,
    back_to_main_kb,
    confirm_delete_kb,
)

logger = logging.getLogger(__name__)
router = Router()

USERNAME_RE = re.compile(r"^@?[a-zA-Z0-9_]{3,32}$")
USERID_RE   = re.compile(r"^\d{5,12}$")


def _parse_identifier(text: str):
    """
    Возвращает (identifier, label):
      identifier — str username (без @) или int user_id
      label      — строка для отображения (@username или ID:12345)
    Возвращает (None, None) если не распознано.
    """
    text = text.strip()
    if USERID_RE.match(text):
        uid = int(text)
        return uid, f"ID:{uid}"
    if USERNAME_RE.match(text):
        uname = text.lstrip("@").lower()
        return uname, f"@{uname}"
    return None, None


# ── Add account ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "add_account")
async def cb_add_account(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddAccountForm.waiting_for_username)
    await cb.message.edit_text(
        "➕ <b>Добавить аккаунт в мониторинг</b>\n\n"
        "Введите <b>username</b> или <b>user_id</b>:\n\n"
        "  • <code>@durov</code> — по username\n"
        "  • <code>durov</code> — без @\n"
        "  • <code>123456789</code> — по числовому ID\n\n"
        "💡 По user_id работает даже если аккаунт сменит username.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AddAccountForm.waiting_for_username)
async def process_username(message: Message, state: FSMContext) -> None:
    identifier, label = _parse_identifier(message.text or "")

    if identifier is None:
        await message.answer(
            "❌ Не распознано. Введите <code>@username</code> или числовой <code>user_id</code>.",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        return

    status_msg = await message.answer(f"🔍 Ищу аккаунт <b>{label}</b>…", parse_mode="HTML")

    snapshot = await monitor_client.get_profile(identifier)
    if snapshot is None:
        await status_msg.edit_text(
            f"❌ Аккаунт <b>{label}</b> не найден или недоступен.\n\n"
            "Убедитесь что:\n"
            "• username/ID указан верно\n"
            "• аккаунт существует\n"
            "• userbot состоит в общем чате с этим пользователем (для ID без username)",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        return

    # Для хранения используем username если есть, иначе строку из ID
    stored_username = (snapshot.username or "").lower() or str(snapshot.target_id)

    db = await get_db()
    account_id = await db.add_monitored(
        owner_id=message.from_user.id,
        target_username=stored_username,
        target_id=snapshot.target_id,
        display_name=snapshot.display_name,
        bio=snapshot.bio,
        photo_hash=snapshot.photo_hash,
    )

    await state.clear()

    if account_id is None:
        await status_msg.edit_text(
            f"⚠️ Аккаунт <b>{label}</b> уже добавлен в ваш мониторинг.",
            parse_mode="HTML",
            reply_markup=back_to_main_kb(),
        )
        return

    username_str = f"@{snapshot.username}" if snapshot.username else f"ID:{snapshot.target_id}"
    details = (
        f"  👤 Имя: {snapshot.display_name or '—'}\n"
        f"  📝 Bio: {(snapshot.bio or '—')[:80]}\n"
        f"  🆔 ID: {snapshot.target_id or '—'}"
    )

    await status_msg.edit_text(
        f"✅ <b>{username_str}</b> добавлен в мониторинг!\n\n"
        f"{details}\n\n"
        "Бот будет уведомлять вас об изменениях профиля.",
        parse_mode="HTML",
        reply_markup=back_to_main_kb(),
    )
    logger.info(
        "User %d added %s to monitoring (account_id=%d)",
        message.from_user.id, label, account_id,
    )


# ── List monitors ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_monitors")
async def cb_my_monitors(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    db = await get_db()
    accounts = await db.get_user_monitored(cb.from_user.id)

    if not accounts:
        await cb.message.edit_text(
            "📋 У вас нет активных мониторингов.\n\nДобавьте аккаунт через кнопку ниже.",
            reply_markup=back_to_main_kb(),
        )
        await cb.answer()
        return

    await cb.message.edit_text(
        f"📋 <b>Ваши мониторинги</b> ({len(accounts)}):\n\n"
        "🟢 — активен  |  ⏸ — на паузе\n\n"
        "Выберите аккаунт для управления:",
        parse_mode="HTML",
        reply_markup=monitors_list_kb(accounts),
    )
    await cb.answer()


# ── Monitor detail ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("monitor_detail:"))
async def cb_monitor_detail(cb: CallbackQuery) -> None:
    account_id = int(cb.data.split(":")[1])
    db = await get_db()
    acc = await db.get_monitored(account_id)

    if not acc or acc["owner_id"] != cb.from_user.id:
        await cb.answer("❌ Мониторинг не найден.", show_alert=True)
        return

    status = "🟢 Активен" if acc["is_active"] else "⏸ На паузе"
    checked = acc["last_checked"] or "ещё не проверялся"
    bio_short = (acc["bio"] or "—")[:100]
    label = f"@{acc['target_username']}" if not acc["target_username"].isdigit() else f"ID:{acc['target_username']}"

    text = (
        f"📌 <b>{label}</b>\n\n"
        f"📛 Имя: {acc['display_name'] or '—'}\n"
        f"🆔 Telegram ID: {acc['target_id'] or '—'}\n"
        f"📝 Bio: {bio_short}\n"
        f"🔄 Статус: {status}\n"
        f"🕐 Последняя проверка: {checked}"
    )

    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=monitor_detail_kb(account_id, bool(acc["is_active"])),
    )
    await cb.answer()


# ── Toggle ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("toggle_monitor:"))
async def cb_toggle_monitor(cb: CallbackQuery) -> None:
    account_id = int(cb.data.split(":")[1])
    db = await get_db()
    new_state = await db.toggle_monitored(account_id, cb.from_user.id)

    if new_state is None:
        await cb.answer("❌ Мониторинг не найден.", show_alert=True)
        return

    state_text = "▶️ Возобновлён" if new_state else "⏸ Поставлен на паузу"
    await cb.answer(f"✅ Мониторинг {state_text}.")

    acc = await db.get_monitored(account_id)
    if acc:
        await cb.message.edit_reply_markup(
            reply_markup=monitor_detail_kb(account_id, bool(acc["is_active"]))
        )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("delete_monitor:"))
async def cb_delete_confirm(cb: CallbackQuery) -> None:
    account_id = int(cb.data.split(":")[1])
    db = await get_db()
    acc = await db.get_monitored(account_id)

    if not acc or acc["owner_id"] != cb.from_user.id:
        await cb.answer("❌ Мониторинг не найден.", show_alert=True)
        return

    label = f"@{acc['target_username']}" if not acc["target_username"].isdigit() else f"ID:{acc['target_username']}"
    await cb.message.edit_text(
        f"🗑 Удалить мониторинг <b>{label}</b>?\n\nЭто действие необратимо.",
        parse_mode="HTML",
        reply_markup=confirm_delete_kb(account_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_delete_confirmed(cb: CallbackQuery) -> None:
    account_id = int(cb.data.split(":")[1])
    db = await get_db()
    deleted = await db.delete_monitored(account_id, cb.from_user.id)

    if deleted:
        await cb.message.edit_text("✅ Мониторинг удалён.", reply_markup=back_to_main_kb())
    else:
        await cb.answer("❌ Не удалось удалить.", show_alert=True)


# ── Change log ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("monitor_log:"))
async def cb_monitor_log(cb: CallbackQuery) -> None:
    account_id = int(cb.data.split(":")[1])
    db = await get_db()
    acc = await db.get_monitored(account_id)

    if not acc or acc["owner_id"] != cb.from_user.id:
        await cb.answer("❌ Мониторинг не найден.", show_alert=True)
        return

    logs = await db.get_change_log(account_id, limit=15)
    if not logs:
        await cb.answer("📜 История изменений пуста.", show_alert=True)
        return

    lines = [
        f"  [{e['changed_at'][:16]}] <b>{e['field']}</b>:\n"
        f"    {e['old_value'] or '—'} → {e['new_value'] or '—'}"
        for e in logs
    ]
    label = f"@{acc['target_username']}" if not acc["target_username"].isdigit() else f"ID:{acc['target_username']}"

    await cb.message.edit_text(
        f"📜 <b>История изменений {label}</b>\n(последние {len(logs)})\n\n" + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=monitor_detail_kb(account_id, bool(acc["is_active"])),
    )
    await cb.answer()


# ── User stats ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_stats")
async def cb_my_stats(cb: CallbackQuery) -> None:
    db = await get_db()
    accounts = await db.get_user_monitored(cb.from_user.id)
    active = sum(1 for a in accounts if a["is_active"])

    await cb.message.edit_text(
        f"📊 <b>Ваша статистика</b>\n\n"
        f"📋 Всего мониторингов: {len(accounts)}\n"
        f"🟢 Активных: {active}\n"
        f"⏸ На паузе: {len(accounts) - active}",
        parse_mode="HTML",
        reply_markup=back_to_main_kb(),
    )
    await cb.answer()