from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import back_kb, interval_kb
from states import IntervalStates


router = Router()
MIN_INTERVAL = 5
MAX_INTERVAL = 3600


async def interval_text(db, user_id: int) -> str:
    user = await db.ensure_user(user_id)
    return "⏱️ <b>Интервал</b>\n\n" f"Текущий интервал: <b>{user.interval_seconds} сек</b>"


@router.callback_query(F.data == "interval")
async def interval(callback: CallbackQuery, db) -> None:
    await callback.message.edit_text(await interval_text(db, callback.from_user.id), reply_markup=interval_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("interval_set:"))
async def interval_set(callback: CallbackQuery, db) -> None:
    seconds = int(callback.data.split(":", 1)[1])
    await db.set_interval(callback.from_user.id, seconds)
    await callback.message.edit_text(await interval_text(db, callback.from_user.id), reply_markup=interval_kb())
    await callback.answer("Интервал обновлен")


@router.callback_query(F.data == "interval_manual")
async def interval_manual(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(IntervalStates.waiting_interval)
    await callback.message.edit_text(
        f"⏱️ Введите интервал в секундах от {MIN_INTERVAL} до {MAX_INTERVAL}.",
        reply_markup=back_kb("interval"),
    )
    await callback.answer()


@router.message(IntervalStates.waiting_interval)
async def interval_save(message: Message, state: FSMContext, db) -> None:
    try:
        seconds = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число секунд.", reply_markup=back_kb("interval"))
        return
    if seconds < MIN_INTERVAL or seconds > MAX_INTERVAL:
        await message.answer(f"Допустимо от {MIN_INTERVAL} до {MAX_INTERVAL} секунд.", reply_markup=back_kb("interval"))
        return
    await db.set_interval(message.from_user.id, seconds)
    await state.clear()
    await message.answer(await interval_text(db, message.from_user.id), reply_markup=interval_kb())
