import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import config
from db import get_db
from utils import main_menu_kb, admin_menu_kb, back_to_main_kb

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "👋 <b>Привет, {name}!</b>\n\n"
    "Этот бот позволяет отслеживать изменения в профилях Telegram-аккаунтов:\n"
    "• Username\n• Имя и фамилия\n• Bio\n• Фото профиля\n\n"
    "Используйте меню ниже для управления мониторингами."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    db = await get_db()
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )

    is_admin = message.from_user.id == config.admin_id
    if is_admin:
        await db.set_allowed(message.from_user.id, True)

    name = message.from_user.first_name or "пользователь"
    kb = admin_menu_kb() if is_admin else main_menu_kb()

    await message.answer(
        WELCOME_TEXT.format(name=name),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if message.from_user.id != config.admin_id:
        return
    await state.clear()
    await message.answer("👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = cb.from_user.id == config.admin_id
    kb = admin_menu_kb() if is_admin else main_menu_kb()
    try:
        await cb.message.edit_text("📋 <b>Главное меню</b>", parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass  # сообщение уже такое же — игнорируем
    await cb.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = cb.from_user.id == config.admin_id
    kb = admin_menu_kb() if is_admin else main_menu_kb()
    try:
        await cb.message.edit_text("❌ Действие отменено.\n\n📋 <b>Главное меню</b>", parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await cb.answer()