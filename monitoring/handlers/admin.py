import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import config
from db import get_db
from states import AdminForm
from utils import admin_menu_kb, cancel_kb, back_to_main_kb

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == config.admin_id


# ── Guard filter ──────────────────────────────────────────────────────────────
# All handlers in this router only execute for the admin.
# We apply the check manually inside each handler for clarity.


# ── Allow user ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_allow")
async def cb_admin_allow(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminForm.waiting_for_user_id_allow)
    await cb.message.edit_text(
        "✅ <b>Выдать доступ</b>\n\n"
        "Введите <b>user_id</b> пользователя, которому нужно дать доступ.\n\n"
        "💡 Пользователь должен был хотя бы раз запустить бота (/start).",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AdminForm.waiting_for_user_id_allow)
async def process_allow_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный user_id. Введите число.", reply_markup=cancel_kb())
        return

    db = await get_db()
    # Auto-create a stub record if user hasn't /start'd yet
    user = await db.get_user(target_id)
    if not user:
        await message.answer(
            f"⚠️ Пользователь <code>{target_id}</code> не найден в базе.\n"
            "Попросите его запустить бота командой /start, затем повторите.",
            parse_mode="HTML",
            reply_markup=back_to_main_kb(),
        )
        await state.clear()
        return

    success = await db.set_allowed(target_id, True)
    await state.clear()

    if success:
        await message.answer(
            f"✅ Пользователь <code>{target_id}</code> получил доступ.",
            parse_mode="HTML",
            reply_markup=admin_menu_kb(),
        )
        logger.info("Admin granted access to user %d", target_id)
    else:
        await message.answer(
            "❌ Не удалось выдать доступ. Пользователь не найден.",
            reply_markup=admin_menu_kb(),
        )


# ── Ban user ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_ban")
async def cb_admin_ban(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminForm.waiting_for_user_id_ban)
    await cb.message.edit_text(
        "🚫 <b>Забанить пользователя</b>\n\nВведите user_id:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AdminForm.waiting_for_user_id_ban)
async def process_ban_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный user_id.", reply_markup=cancel_kb())
        return

    if target_id == config.admin_id:
        await message.answer("🙅 Нельзя забанить самого себя.", reply_markup=admin_menu_kb())
        await state.clear()
        return

    db = await get_db()
    success = await db.set_banned(target_id, True)
    await state.clear()
    result = (
        f"✅ Пользователь <code>{target_id}</code> забанен."
        if success
        else f"❌ Пользователь <code>{target_id}</code> не найден."
    )
    await message.answer(result, parse_mode="HTML", reply_markup=admin_menu_kb())
    if success:
        logger.info("Admin banned user %d", target_id)


# ── Unban user ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_unban")
async def cb_admin_unban(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminForm.waiting_for_user_id_unban)
    await cb.message.edit_text(
        "✔️ <b>Разбанить пользователя</b>\n\nВведите user_id:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AdminForm.waiting_for_user_id_unban)
async def process_unban_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный user_id.", reply_markup=cancel_kb())
        return

    db = await get_db()
    success = await db.set_banned(target_id, False)
    await state.clear()
    result = (
        f"✅ Пользователь <code>{target_id}</code> разбанен."
        if success
        else f"❌ Пользователь <code>{target_id}</code> не найден."
    )
    await message.answer(result, parse_mode="HTML", reply_markup=admin_menu_kb())


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return
    db = await get_db()
    active_users = await db.count_active_users()
    all_monitored = await db.count_all_monitored()
    all_users = await db.get_all_users()

    banned = sum(1 for u in all_users if u["is_banned"])
    pending = sum(1 for u in all_users if not u["is_allowed"] and not u["is_banned"])

    await cb.message.edit_text(
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {len(all_users)}\n"
        f"✅ С доступом: {active_users}\n"
        f"⏳ Ожидают доступа: {pending}\n"
        f"🚫 Забанено: {banned}\n\n"
        f"📋 Активных мониторингов: {all_monitored}",
        parse_mode="HTML",
        reply_markup=admin_menu_kb(),
    )
    await cb.answer()


# ── Users list ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return
    db = await get_db()
    users = await db.get_all_users()

    if not users:
        await cb.answer("Нет пользователей в базе.", show_alert=True)
        return

    lines = []
    for u in users[:30]:  # Cap at 30 to avoid message length limit
        flags = []
        if u["is_banned"]:
            flags.append("🚫")
        elif u["is_allowed"]:
            flags.append("✅")
        else:
            flags.append("⏳")

        name = u["first_name"] or ""
        username = f"@{u['username']}" if u["username"] else ""
        lines.append(f"{' '.join(flags)} <code>{u['id']}</code> {name} {username}")

    text = "👥 <b>Пользователи</b>\n\n" + "\n".join(lines)
    if len(users) > 30:
        text += f"\n\n…и ещё {len(users) - 30} пользователей."

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu_kb())
    await cb.answer()


# ── Delete monitor (admin) ────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_del_monitor")
async def cb_admin_del_monitor(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminForm.waiting_for_account_id_delete)
    await cb.message.edit_text(
        "🗑 <b>Удалить мониторинг</b>\n\n"
        "Введите <b>ID мониторинга</b> (числовой идентификатор из базы данных):",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AdminForm.waiting_for_account_id_delete)
async def process_admin_delete_monitor(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        account_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный ID.", reply_markup=cancel_kb())
        return

    db = await get_db()
    deleted = await db.admin_delete_monitored(account_id)
    await state.clear()
    result = (
        f"✅ Мониторинг <code>{account_id}</code> удалён."
        if deleted
        else f"❌ Мониторинг <code>{account_id}</code> не найден."
    )
    await message.answer(result, parse_mode="HTML", reply_markup=admin_menu_kb())
    if deleted:
        logger.info("Admin deleted monitoring id=%d", account_id)
