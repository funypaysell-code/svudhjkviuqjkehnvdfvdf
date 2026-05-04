from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from country_utils import resolve_country
from keyboards import back_kb, critical_countries_kb, monitor_notifications_kb, monitoring_kb
from states import MonitoringStates


router = Router()
MIN_ALERT_REPEAT = 1
MAX_ALERT_REPEAT = 20
MIN_ESCALATION_INTERVAL = 15
MAX_ESCALATION_INTERVAL = 3600


async def monitoring_text(db, user_id: int) -> str:
    user = await db.ensure_user(user_id)
    countries = await db.get_user_countries(user_id)
    countries_text = "все страны" if not countries else ", ".join(c["country_code"].upper() for c in countries)
    price_text = "без лимита" if user.max_price is None else f"до {user.max_price:.2f}$"
    api_status = "настроено" if user.api_key and user.your_id else "не настроено"
    return (
        "🔎 <b>Мониторинг</b>\n\n"
        f"Статус: {'🟢 включен' if user.monitoring_enabled else '⚪ выключен'}\n"
        f"API: {api_status}\n"
        f"Страны: {countries_text}\n"
        f"Цена: {price_text}\n"
        f"Интервал: {user.interval_seconds} сек\n"
        f"Увед. страна: {'ON' if user.country_alert_enabled else 'OFF'} ×{user.alert_repeat_count}\n"
        f"Увед. автопокупка: {'ON' if user.autobuy_alert_enabled else 'OFF'} ×{user.autobuy_alert_repeat_count}\n\n"
        "Алерты по одной стране отправляются не чаще одного раза в 5 минут."
    )


@router.callback_query(F.data == "monitoring")
async def monitoring(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await monitoring_text(db, callback.from_user.id),
        reply_markup=monitoring_kb(user.monitoring_enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "monitor_toggle")
async def monitor_toggle(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    if not user.api_key or not user.your_id:
        await callback.message.edit_text(
            "⚠️ Для мониторинга сначала настройте apiKey и YourID.",
            reply_markup=monitoring_kb(False),
        )
        await callback.answer()
        return
    await db.set_monitoring(callback.from_user.id, not user.monitoring_enabled)
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await monitoring_text(db, callback.from_user.id),
        reply_markup=monitoring_kb(user.monitoring_enabled),
    )
    await callback.answer("Мониторинг включен" if user.monitoring_enabled else "Мониторинг выключен")


async def notifications_text(db, user_id: int) -> str:
    user = await db.ensure_user(user_id)
    critical = await db.get_critical_countries(user_id)
    quiet_status = "OFF"
    if user.quiet_hours_enabled:
        quiet_status = f"ON ({user.quiet_start_hour:02d}:00-{user.quiet_end_hour:02d}:00 UTC)"
    return (
        "🔔 <b>Настройки уведомлений</b>\n\n"
        f"🌍 Выход страны: <b>{'ON' if user.country_alert_enabled else 'OFF'}</b>\n"
        f"Повторы выхода страны: <b>{user.alert_repeat_count}</b>\n\n"
        f"🤖 Автопокупка: <b>{'ON' if user.autobuy_alert_enabled else 'OFF'}</b>\n"
        f"Повторы автопокупки: <b>{user.autobuy_alert_repeat_count}</b>\n\n"
        f"🌙 Тихие часы: <b>{quiet_status}</b>\n"
        f"🚨 Эскалация: <b>{'ON' if user.escalation_enabled else 'OFF'}</b> (каждые {user.escalation_interval_seconds} сек)\n"
        f"🌍 Критичные страны: <b>{len(critical)}</b>"
    )


@router.callback_query(F.data == "monitor_notifications")
async def monitor_notifications(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await notifications_text(db, callback.from_user.id),
        reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "monitor_notifications_toggle_country")
async def monitor_notifications_toggle_country(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await db.set_country_alert_enabled(callback.from_user.id, not user.country_alert_enabled)
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await notifications_text(db, callback.from_user.id),
        reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled),
    )
    await callback.answer("Настройка обновлена")


@router.callback_query(F.data == "monitor_notifications_toggle_autobuy")
async def monitor_notifications_toggle_autobuy(callback: CallbackQuery, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await db.set_autobuy_alert_enabled(callback.from_user.id, not user.autobuy_alert_enabled)
    user = await db.ensure_user(callback.from_user.id)
    await callback.message.edit_text(
        await notifications_text(db, callback.from_user.id),
        reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled),
    )
    await callback.answer("Настройка обновлена")


@router.callback_query(F.data == "monitor_notifications_repeat_country")
async def monitor_notifications_repeat_country(callback: CallbackQuery, state: FSMContext, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await state.set_state(MonitoringStates.waiting_country_alert_repeat)
    await callback.message.edit_text(
        "🌍 <b>Повторы уведомления о выходе страны</b>\n\n"
        f"Сейчас: <b>{user.alert_repeat_count}</b>\n"
        f"Введите число от {MIN_ALERT_REPEAT} до {MAX_ALERT_REPEAT}.",
        reply_markup=back_kb("monitor_notifications"),
    )
    await callback.answer()


@router.callback_query(F.data == "monitor_notifications_repeat_autobuy")
async def monitor_notifications_repeat_autobuy(callback: CallbackQuery, state: FSMContext, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await state.set_state(MonitoringStates.waiting_autobuy_alert_repeat)
    await callback.message.edit_text(
        "🤖 <b>Повторы уведомления об автопокупке</b>\n\n"
        f"Сейчас: <b>{user.autobuy_alert_repeat_count}</b>\n"
        f"Введите число от {MIN_ALERT_REPEAT} до {MAX_ALERT_REPEAT}.",
        reply_markup=back_kb("monitor_notifications"),
    )
    await callback.answer()


@router.message(MonitoringStates.waiting_country_alert_repeat)
async def monitor_country_alert_repeat_save(message: Message, state: FSMContext, db) -> None:
    try:
        repeat_count = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число.", reply_markup=back_kb("monitor_notifications"))
        return
    if repeat_count < MIN_ALERT_REPEAT or repeat_count > MAX_ALERT_REPEAT:
        await message.answer(
            f"Допустимо от {MIN_ALERT_REPEAT} до {MAX_ALERT_REPEAT}.",
            reply_markup=back_kb("monitor_notifications"),
        )
        return
    await db.set_alert_repeat_count(message.from_user.id, repeat_count)
    await state.clear()
    user = await db.ensure_user(message.from_user.id)
    await message.answer(
        "✅ Повторы для уведомления о выходе страны сохранены.",
        reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled),
    )


@router.message(MonitoringStates.waiting_autobuy_alert_repeat)
async def monitor_autobuy_alert_repeat_save(message: Message, state: FSMContext, db) -> None:
    try:
        repeat_count = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число.", reply_markup=back_kb("monitor_notifications"))
        return
    if repeat_count < MIN_ALERT_REPEAT or repeat_count > MAX_ALERT_REPEAT:
        await message.answer(
            f"Допустимо от {MIN_ALERT_REPEAT} до {MAX_ALERT_REPEAT}.",
            reply_markup=back_kb("monitor_notifications"),
        )
        return
    await db.set_autobuy_alert_repeat_count(message.from_user.id, repeat_count)
    await state.clear()
    user = await db.ensure_user(message.from_user.id)
    await message.answer(
        "✅ Повторы для уведомления об автопокупке сохранены.",
        reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled),
    )


@router.callback_query(F.data == "monitor_notifications_quiet_hours")
async def monitor_notifications_quiet_hours(callback: CallbackQuery, state: FSMContext, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await state.set_state(MonitoringStates.waiting_quiet_hours)
    await callback.message.edit_text(
        "🌙 <b>Тихие часы</b>\n\n"
        f"Сейчас: {'ON' if user.quiet_hours_enabled else 'OFF'} ({user.quiet_start_hour:02d}:00-{user.quiet_end_hour:02d}:00 UTC)\n\n"
        "Отправьте <code>off</code> или диапазон формата <code>23-7</code>.",
        reply_markup=back_kb("monitor_notifications"),
    )
    await callback.answer()


@router.message(MonitoringStates.waiting_quiet_hours)
async def monitor_notifications_quiet_hours_save(message: Message, state: FSMContext, db) -> None:
    text = (message.text or "").strip().lower()
    if text == "off":
        user = await db.ensure_user(message.from_user.id)
        await db.set_quiet_hours(message.from_user.id, False, user.quiet_start_hour, user.quiet_end_hour)
    else:
        parts = text.replace(":", "").split("-", 1)
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await message.answer("Формат: <code>23-7</code> или <code>off</code>.", reply_markup=back_kb("monitor_notifications"))
            return
        await db.set_quiet_hours(message.from_user.id, True, int(parts[0]) % 24, int(parts[1]) % 24)
    await state.clear()
    user = await db.ensure_user(message.from_user.id)
    await message.answer("✅ Тихие часы сохранены.", reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled))


@router.callback_query(F.data == "monitor_notifications_escalation")
async def monitor_notifications_escalation(callback: CallbackQuery, state: FSMContext, db) -> None:
    user = await db.ensure_user(callback.from_user.id)
    await db.set_escalation_enabled(callback.from_user.id, not user.escalation_enabled)
    user = await db.ensure_user(callback.from_user.id)
    await state.set_state(MonitoringStates.waiting_escalation_interval)
    await callback.message.edit_text(
        "🚨 <b>Эскалация до подтверждения</b>\n\n"
        f"Статус: {'ON' if user.escalation_enabled else 'OFF'}\n"
        f"Интервал: {user.escalation_interval_seconds} сек\n\n"
        f"Введите новый интервал ({MIN_ESCALATION_INTERVAL}-{MAX_ESCALATION_INTERVAL}) или <code>skip</code>.",
        reply_markup=back_kb("monitor_notifications"),
    )
    await callback.answer("Эскалация переключена")


@router.message(MonitoringStates.waiting_escalation_interval)
async def monitor_notifications_escalation_interval_save(message: Message, state: FSMContext, db) -> None:
    text = (message.text or "").strip().lower()
    if text != "skip":
        try:
            seconds = int(text)
        except ValueError:
            await message.answer("Введите число секунд или skip.", reply_markup=back_kb("monitor_notifications"))
            return
        if seconds < MIN_ESCALATION_INTERVAL or seconds > MAX_ESCALATION_INTERVAL:
            await message.answer(
                f"Допустимо от {MIN_ESCALATION_INTERVAL} до {MAX_ESCALATION_INTERVAL}.",
                reply_markup=back_kb("monitor_notifications"),
            )
            return
        await db.set_escalation_interval(message.from_user.id, seconds)
    await state.clear()
    user = await db.ensure_user(message.from_user.id)
    await message.answer("✅ Эскалация сохранена.", reply_markup=monitor_notifications_kb(user.country_alert_enabled, user.autobuy_alert_enabled))


@router.callback_query(F.data == "monitor_notifications_critical")
async def monitor_notifications_critical(callback: CallbackQuery, db) -> None:
    critical = await db.get_critical_countries(callback.from_user.id)
    body = "Список пуст." if not critical else "\n".join(
        f"• <code>{item['country_code'].upper()}</code> ×{item['repeat_count']}" for item in critical[:50]
    )
    await callback.message.edit_text(
        "🌍 <b>Критичные страны</b>\n\n"
        "Укажите страны, для которых повторов будет больше.\n\n"
        f"{body}",
        reply_markup=critical_countries_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "critical_add")
async def critical_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MonitoringStates.waiting_critical_country_add)
    await callback.message.edit_text(
        "Введите страну и число повторов, например:\n<code>us 12</code> или <code>узбекистан 8</code>",
        reply_markup=back_kb("monitor_notifications_critical"),
    )
    await callback.answer()


@router.message(MonitoringStates.waiting_critical_country_add)
async def critical_add_save(message: Message, state: FSMContext, db) -> None:
    raw = (message.text or "").strip()
    parts = raw.rsplit(" ", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: <code>страна повторы</code>, пример <code>us 12</code>.", reply_markup=back_kb("monitor_notifications_critical"))
        return
    resolved = resolve_country(parts[0].strip())
    if not resolved:
        await message.answer("Не смог определить страну.", reply_markup=back_kb("monitor_notifications_critical"))
        return
    repeat_count = int(parts[1])
    if repeat_count < MIN_ALERT_REPEAT or repeat_count > MAX_ALERT_REPEAT:
        await message.answer(f"Повторы от {MIN_ALERT_REPEAT} до {MAX_ALERT_REPEAT}.", reply_markup=back_kb("monitor_notifications_critical"))
        return
    await db.upsert_critical_country(message.from_user.id, resolved.code, repeat_count)
    await state.clear()
    await message.answer(f"✅ Критичная страна сохранена: <b>{resolved.name}</b> ×{repeat_count}.", reply_markup=critical_countries_kb())


@router.callback_query(F.data == "critical_remove")
async def critical_remove(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MonitoringStates.waiting_critical_country_remove)
    await callback.message.edit_text(
        "Введите страну или код для удаления из критичных.",
        reply_markup=back_kb("monitor_notifications_critical"),
    )
    await callback.answer()


@router.message(MonitoringStates.waiting_critical_country_remove)
async def critical_remove_save(message: Message, state: FSMContext, db) -> None:
    resolved = resolve_country((message.text or "").strip())
    if not resolved:
        await message.answer("Не смог определить страну.", reply_markup=back_kb("monitor_notifications_critical"))
        return
    removed = await db.remove_critical_country(message.from_user.id, resolved.code)
    await state.clear()
    if removed:
        await message.answer("✅ Страна удалена из критичных.", reply_markup=critical_countries_kb())
    else:
        await message.answer("Страны не было в списке.", reply_markup=critical_countries_kb())


@router.callback_query(F.data == "critical_clear")
async def critical_clear(callback: CallbackQuery, db) -> None:
    await db.clear_critical_countries(callback.from_user.id)
    await callback.message.edit_text("🧹 Критичные страны очищены.", reply_markup=critical_countries_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("alert_ack:"))
async def alert_ack(callback: CallbackQuery, db) -> None:
    country_code = callback.data.split(":", 1)[1]
    await db.remove_pending_country_alert(callback.from_user.id, country_code)
    await callback.answer("Эскалация остановлена")
