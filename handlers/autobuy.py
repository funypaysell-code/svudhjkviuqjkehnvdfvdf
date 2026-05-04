from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import autobuy_kb, autobuy_limits_kb, back_kb
from states import AutobuyStates


router = Router()


def parse_float(value: str) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", value.strip())
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def parse_int(value: str) -> int | None:
    match = re.search(r"\d+", value.strip())
    if not match:
        return None
    return int(match.group(0))


async def autobuy_text(db, user_id: int) -> str:
    settings = await db.ensure_autobuy_settings(user_id)
    user = await db.ensure_user(user_id)
    countries = await db.get_user_countries(user_id)
    total = await db.count_purchases(user_id)
    today = await db.count_purchases_today(user_id)

    countries_text = "все выбранные мониторингом" if not countries else ", ".join(c["country_code"].upper() for c in countries)
    min_price = "без минимума" if settings.min_price is None else f"от {settings.min_price:.2f}$"
    max_price = "по лимиту мониторинга" if settings.max_price is None else f"до {settings.max_price:.2f}$"
    stop_balance = "не задан" if settings.stop_balance is None else f"остановить при балансе <= {settings.stop_balance:.2f}$"

    return (
        "🤖 <b>Автоскуп</b>\n\n"
        f"Статус: <b>{'включен' if settings.enabled else 'выключен'}</b>\n"
        f"Мониторинг: <b>{'включен' if user.monitoring_enabled else 'выключен'}</b>\n"
        f"Страны: <b>{countries_text}</b>\n"
        f"Цена: <b>{min_price}</b> / <b>{max_price}</b>\n"
        f"Стоп-баланс: <b>{stop_balance}</b>\n"
        f"Лимит всего: <b>{total}/{settings.max_purchases_total}</b>\n"
        f"Лимит за день: <b>{today}/{settings.max_purchases_day}</b>\n"
        f"Автополучение кода: <b>{'ON' if settings.auto_get_code else 'OFF'}</b>\n"
        f"Проверка кода: <b>{settings.code_check_seconds} сек</b>\n\n"
        "Автоскуп сработает только когда страна проходит фильтр мониторинга, цена подходит и лимиты не исчерпаны."
    )


@router.callback_query(F.data == "autobuy")
async def autobuy(callback: CallbackQuery, db) -> None:
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    await callback.message.edit_text(
        await autobuy_text(db, callback.from_user.id),
        reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code),
    )
    await callback.answer()


@router.callback_query(F.data == "autobuy_toggle")
async def autobuy_toggle(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    if not user.api_key or not user.your_id:
        await callback.message.edit_text("⚠️ Сначала настройте apiKey и YourID.", reply_markup=back_kb("api_settings"))
        await callback.answer()
        return
    if not user.monitoring_enabled and not settings.enabled:
        await db.set_monitoring(callback.from_user.id, True)
    await db.update_autobuy_setting(callback.from_user.id, "enabled", int(not settings.enabled))
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    await callback.message.edit_text(
        await autobuy_text(db, callback.from_user.id),
        reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code),
    )
    await callback.answer("Автоскуп включен" if settings.enabled else "Автоскуп выключен")


@router.callback_query(F.data == "autobuy_min_price")
async def autobuy_min_price(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_min_price)
    await callback.message.edit_text(
        "💵 Введите минимальную цену для покупки.\n\n"
        "Например <code>0.50</code>. Чтобы убрать минимум, отправьте <code>0</code>.",
        reply_markup=back_kb("autobuy"),
    )
    await callback.answer()


@router.message(AutobuyStates.waiting_min_price)
async def autobuy_min_price_save(message: Message, state: FSMContext, db) -> None:
    value = parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введите корректное число.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "min_price", None if value == 0 else value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_max_price")
async def autobuy_max_price(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_max_price)
    await callback.message.edit_text(
        "💵 Введите максимальную цену автоскупа.\n\n"
        "Например <code>1.20</code>. Отправьте <code>0</code>, чтобы использовать общий лимит цены.",
        reply_markup=back_kb("autobuy"),
    )
    await callback.answer()


@router.message(AutobuyStates.waiting_max_price)
async def autobuy_max_price_save(message: Message, state: FSMContext, db) -> None:
    value = parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введите корректное число.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "max_price", None if value == 0 else value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_stop_balance")
async def autobuy_stop_balance(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_stop_balance)
    await callback.message.edit_text(
        "💰 До какого баланса скупать?\n\n"
        "Например <code>5</code>: бот остановит покупки, когда баланс будет <= 5$.\n"
        "Отправьте <code>0</code>, чтобы убрать стоп-баланс.",
        reply_markup=back_kb("autobuy"),
    )
    await callback.answer()


@router.message(AutobuyStates.waiting_stop_balance)
async def autobuy_stop_balance_save(message: Message, state: FSMContext, db) -> None:
    value = parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введите корректное число.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "stop_balance", None if value == 0 else value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_limits")
async def autobuy_limits(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🎯 <b>Лимиты автоскупа</b>\n\nВыберите, что настроить.", reply_markup=autobuy_limits_kb())
    await callback.answer()


@router.callback_query(F.data == "autobuy_total_limit")
async def autobuy_total_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_total_limit)
    await callback.message.edit_text("🎯 Введите общий лимит покупок, например <code>10</code>.", reply_markup=back_kb("autobuy_limits"))
    await callback.answer()


@router.message(AutobuyStates.waiting_total_limit)
async def autobuy_total_limit_save(message: Message, state: FSMContext, db) -> None:
    value = parse_int(message.text)
    if value is None or value < 1 or value > 1000:
        await message.answer("Введите число от 1 до 1000.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "max_purchases_total", value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_daily_limit")
async def autobuy_daily_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_daily_limit)
    await callback.message.edit_text("🎯 Введите лимит покупок в день, например <code>3</code>.", reply_markup=back_kb("autobuy_limits"))
    await callback.answer()


@router.message(AutobuyStates.waiting_daily_limit)
async def autobuy_daily_limit_save(message: Message, state: FSMContext, db) -> None:
    value = parse_int(message.text)
    if value is None or value < 1 or value > 500:
        await message.answer("Введите число от 1 до 500.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "max_purchases_day", value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_code_interval")
async def autobuy_code_interval(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AutobuyStates.waiting_code_interval)
    await callback.message.edit_text("🔑 Введите интервал проверки кода от 10 до 300 секунд.", reply_markup=back_kb("autobuy_limits"))
    await callback.answer()


@router.message(AutobuyStates.waiting_code_interval)
async def autobuy_code_interval_save(message: Message, state: FSMContext, db) -> None:
    value = parse_int(message.text)
    if value is None or value < 10 or value > 300:
        await message.answer("Введите число от 10 до 300.", reply_markup=back_kb("autobuy"))
        return
    await db.update_autobuy_setting(message.from_user.id, "code_check_seconds", value)
    await state.clear()
    settings = await db.ensure_autobuy_settings(message.from_user.id)
    await message.answer(await autobuy_text(db, message.from_user.id), reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code))


@router.callback_query(F.data == "autobuy_toggle_code")
async def autobuy_toggle_code(callback: CallbackQuery, db) -> None:
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    await db.update_autobuy_setting(callback.from_user.id, "auto_get_code", int(not settings.auto_get_code))
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    await callback.message.edit_text(
        await autobuy_text(db, callback.from_user.id),
        reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code),
    )
    await callback.answer()


@router.callback_query(F.data == "autobuy_reset")
async def autobuy_reset(callback: CallbackQuery, db) -> None:
    await db.reset_autobuy_limits(callback.from_user.id)
    settings = await db.ensure_autobuy_settings(callback.from_user.id)
    await callback.message.edit_text(
        await autobuy_text(db, callback.from_user.id),
        reply_markup=autobuy_kb(settings.enabled, settings.auto_get_code),
    )
    await callback.answer("Настройки сброшены")


@router.callback_query(F.data == "autobuy_purchases")
async def autobuy_purchases(callback: CallbackQuery, db) -> None:
    purchases = await db.get_recent_purchases(callback.from_user.id, 10)
    if not purchases:
        body = "Покупок пока нет."
    else:
        rows = []
        for item in purchases:
            price = "?" if item["price"] is None else f"{item['price']:.2f}$"
            code = item["login_code"] or "код ждем"
            rows.append(f"• <code>{item['number']}</code> · {item['country_code'].upper()} · {price} · {code}")
        body = "\n".join(rows)
    await callback.message.edit_text(f"📦 <b>Покупки</b>\n\n{body}", reply_markup=back_kb("autobuy"))
    await callback.answer()
