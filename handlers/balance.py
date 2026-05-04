from aiogram import F, Router
from aiogram.types import CallbackQuery

from api_client import TGLionApiError
from keyboards import balance_kb, back_kb


router = Router()


@router.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery, db, tg_lion) -> None:
    user = await db.ensure_user(callback.from_user.id)
    if not user.api_key or not user.your_id:
        await callback.message.edit_text("⚠️ Сначала настройте apiKey и YourID.", reply_markup=back_kb("api_settings"))
        await callback.answer()
        return
    try:
        value = await tg_lion.get_balance(user.api_key, user.your_id)
    except TGLionApiError as exc:
        await callback.message.edit_text(f"❌ Не удалось получить баланс: {exc}", reply_markup=balance_kb())
    else:
        await callback.message.edit_text(f"💰 <b>Баланс</b>\n\nТекущий баланс: <b>{value}</b>", reply_markup=balance_kb())
    await callback.answer()
