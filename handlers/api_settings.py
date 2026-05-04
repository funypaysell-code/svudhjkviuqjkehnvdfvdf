from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from api_client import TGLionApiError
from keyboards import api_settings_kb, back_kb
from states import ApiSettingsStates


router = Router()


def mask_key(key: str | None) -> str:
    if not key:
        return "не задан"
    if len(key) <= 8:
        return f"{key[:2]}***{key[-2:]}"
    return f"{key[:4]}***{key[-4:]}"


async def api_settings_text(db, user_id: int) -> str:
    user = await db.ensure_user(user_id)
    return (
        "🔐 <b>API настройки</b>\n\n"
        f"apiKey: <code>{mask_key(user.api_key)}</code>\n"
        f"YourID: <code>{user.your_id or 'не задан'}</code>\n\n"
        "Для проверки используется метод <code>get_balance</code>."
    )


@router.callback_query(F.data == "api_settings")
async def api_settings(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await api_settings_text(db, callback.from_user.id),
        reply_markup=api_settings_kb(bool(user.api_key and user.your_id)),
    )
    await callback.answer()


@router.callback_query(F.data == "api_set_key")
async def ask_api_key(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ApiSettingsStates.waiting_api_key)
    await callback.message.edit_text(
        "🔑 Введите <b>apiKey</b> одним сообщением.",
        reply_markup=back_kb("api_settings"),
    )
    await callback.answer()


@router.message(ApiSettingsStates.waiting_api_key)
async def save_api_key(message: Message, state: FSMContext, db) -> None:
    api_key = message.text.strip()
    if len(api_key) < 4:
        await message.answer("apiKey выглядит слишком коротким.", reply_markup=back_kb("api_settings"))
        return
    await db.set_api_key(message.from_user.id, api_key)
    await state.clear()
    await message.answer("✅ apiKey сохранен.", reply_markup=api_settings_kb(True))


@router.callback_query(F.data == "api_set_your_id")
async def ask_your_id(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ApiSettingsStates.waiting_your_id)
    await callback.message.edit_text(
        "🆔 Введите <b>YourID</b> одним сообщением.",
        reply_markup=back_kb("api_settings"),
    )
    await callback.answer()


@router.message(ApiSettingsStates.waiting_your_id)
async def save_your_id(message: Message, state: FSMContext, db) -> None:
    your_id = message.text.strip()
    if not your_id:
        await message.answer("YourID не может быть пустым.", reply_markup=back_kb("api_settings"))
        return
    await db.set_your_id(message.from_user.id, your_id)
    await state.clear()
    await message.answer("✅ YourID сохранен.", reply_markup=api_settings_kb(True))


@router.callback_query(F.data == "api_check")
async def check_api(callback: CallbackQuery, db, tg_lion) -> None:
    user = await db.ensure_user(callback.from_user.id)
    if not user.api_key or not user.your_id:
        await callback.message.edit_text(
            "⚠️ Сначала укажите apiKey и YourID.",
            reply_markup=api_settings_kb(False),
        )
        await callback.answer()
        return
    try:
        balance = await tg_lion.get_balance(user.api_key, user.your_id)
    except TGLionApiError as exc:
        await callback.message.edit_text(f"❌ Подключение не прошло: {exc}", reply_markup=api_settings_kb(True))
    else:
        await callback.message.edit_text(
            f"✅ Подключение работает.\n\n💰 Баланс: <b>{balance}</b>",
            reply_markup=api_settings_kb(True),
        )
    await callback.answer()


@router.callback_query(F.data == "api_delete")
async def delete_api(callback: CallbackQuery, db) -> None:
    await db.delete_api_settings(callback.from_user.id)
    await callback.message.edit_text(
        "🗑 API настройки удалены. Мониторинг выключен.",
        reply_markup=api_settings_kb(False),
    )
    await callback.answer()
