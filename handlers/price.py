from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import back_kb, price_kb
from states import PriceStates


router = Router()


async def price_text(db, user_id: int) -> str:
    user = await db.ensure_user(user_id)
    current = "без лимита" if user.max_price is None else f"до {user.max_price:.2f}$"
    return "💵 <b>Цена</b>\n\n" f"Текущий лимит: <b>{current}</b>"


@router.callback_query(F.data == "price")
async def price(callback: CallbackQuery, db) -> None:
    await callback.message.edit_text(await price_text(db, callback.from_user.id), reply_markup=price_kb())
    await callback.answer()


@router.callback_query(F.data == "price_set")
async def price_set(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PriceStates.waiting_max_price)
    await callback.message.edit_text("💵 Введите max_price в USD, например <code>1.00</code>.", reply_markup=back_kb("price"))
    await callback.answer()


@router.message(PriceStates.waiting_max_price)
async def price_save(message: Message, state: FSMContext, db) -> None:
    try:
        price = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введите число, например 0.80.", reply_markup=back_kb("price"))
        return
    if price < 0:
        await message.answer("Цена не может быть отрицательной.", reply_markup=back_kb("price"))
        return
    await db.set_max_price(message.from_user.id, price)
    await state.clear()
    await message.answer(await price_text(db, message.from_user.id), reply_markup=price_kb())


@router.callback_query(F.data == "price_reset")
async def price_reset(callback: CallbackQuery, db) -> None:
    await db.set_max_price(callback.from_user.id, None)
    await callback.message.edit_text(await price_text(db, callback.from_user.id), reply_markup=price_kb())
    await callback.answer("Лимит сброшен")
