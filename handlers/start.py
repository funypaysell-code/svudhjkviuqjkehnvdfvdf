from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from keyboards import main_menu_kb


router = Router()


def main_menu_text() -> str:
    return (
        "🦁 <b>Monitor</b>\n\n"
        "Выберите раздел. Бот мониторит страны, цены и количество, "
        "умеет отправлять алерты и автоматически скупать подходящие номера."
    )


@router.message(CommandStart())
async def start(message: Message, db) -> None:
    await db.ensure_user(message.from_user.id)
    await message.answer(main_menu_text(), reply_markup=main_menu_kb())


@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery, db) -> None:
    await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(main_menu_text(), reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Помощь</b>\n\n"
        "1. Введите apiKey и YourID в API настройках.\n"
        "2. Выберите страны или оставьте список пустым для мониторинга всех стран.\n"
        "3. Настройте цену, интервал и при необходимости автоскуп.\n"
        "4. Включите мониторинг. Автоскуп сам включит мониторинг, если он был выключен.\n\n"
        "5. Для мониторинга TG-профилей откройте «Мониторинг TG акков» и добавьте username/ID.\n\n"
        "В автоскупе есть стоп-баланс, лимиты покупок, диапазон цены и автополучение кода.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
