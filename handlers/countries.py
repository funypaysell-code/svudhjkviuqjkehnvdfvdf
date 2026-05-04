from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from api_client import CountryInfo, TGLionApiError
from country_utils import resolve_country, normalize_code
from keyboards import back_kb, countries_kb, country_list_kb, country_remove_kb
from states import CountriesStates


router = Router()


async def countries_text(db, user_id: int) -> str:
    selected = await db.get_user_countries(user_id)
    if selected:
        countries = "\n".join(
            f"• {c['country_name']} · <code>{c['country_code'].upper()}</code>"
            for c in selected[:60]
        )
    else:
        countries = "не выбраны, мониторятся все страны"
    return "🌍 <b>Страны</b>\n\n" f"Сейчас: {countries}"


async def get_available_or_message(callback: CallbackQuery, db, tg_lion) -> list[CountryInfo] | None:
    user = await db.ensure_user(callback.from_user.id)
    if not user.api_key or not user.your_id:
        await callback.message.edit_text("⚠️ Сначала настройте API.", reply_markup=back_kb("countries"))
        await callback.answer()
        return None
    try:
        return await tg_lion.available_countries(user.api_key, user.your_id)
    except TGLionApiError as exc:
        await callback.message.edit_text(f"❌ Не удалось получить страны: {exc}", reply_markup=back_kb("countries"))
        await callback.answer()
        return None


@router.callback_query(F.data == "countries")
async def countries(callback: CallbackQuery, db) -> None:
    await callback.message.edit_text(await countries_text(db, callback.from_user.id), reply_markup=countries_kb())
    await callback.answer()


@router.callback_query(F.data == "countries_available")
async def countries_available(callback: CallbackQuery, db, tg_lion) -> None:
    available = await get_available_or_message(callback, db, tg_lion)
    if available is None:
        return
    text = "📋 <b>Доступные страны</b>\n\nВыберите страну для добавления в мониторинг."
    await callback.message.edit_text(text, reply_markup=country_list_kb(available))
    await callback.answer()


@router.callback_query(F.data.startswith("country_pick:"))
async def country_pick(callback: CallbackQuery, db, tg_lion) -> None:
    code = normalize_code(callback.data.split(":", 1)[1])
    available = await get_available_or_message(callback, db, tg_lion)
    if available is None:
        return
    country = next((item for item in available if normalize_code(item.code) == code), None)
    await db.add_country(callback.from_user.id, code, country.name if country else code.upper())
    await callback.message.edit_text(await countries_text(db, callback.from_user.id), reply_markup=countries_kb())
    await callback.answer("Страна добавлена")


@router.callback_query(F.data == "country_search")
async def country_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CountriesStates.waiting_search)
    await callback.message.edit_text(
        "🔍 Введите название или код страны.\n\n"
        "Если страны нет в наличии, можно добавить ее вручную: например <code>Uzbekistan</code>, "
        "<code>Узбекистан</code>, <code>Niue</code>, <code>+500</code>, <code>+683</code> или <code>uz Uzbekistan</code>.",
        reply_markup=back_kb("countries"),
    )
    await callback.answer()


@router.message(CountriesStates.waiting_search)
async def country_search_result(message: Message, state: FSMContext, db, tg_lion) -> None:
    user = await db.ensure_user(message.from_user.id)
    query = message.text.strip()
    available: list[CountryInfo] = []

    if user.api_key and user.your_id:
        try:
            available = await tg_lion.available_countries(user.api_key, user.your_id)
        except TGLionApiError:
            available = []

    lowered = query.lower()
    found = [c for c in available if lowered in c.code.lower() or lowered in c.name.lower()]
    await state.clear()
    if found:
        await message.answer("🔍 Результаты поиска:", reply_markup=country_list_kb(found))
        return

    resolved = resolve_country(query)
    if resolved:
        await db.add_country(message.from_user.id, resolved.code, resolved.name)
        await message.answer(
            "✅ Страна не найдена в текущем наличии, но добавлена вручную.\n\n"
            f"🌍 {resolved.name} · <code>{resolved.code.upper()}</code>",
            reply_markup=countries_kb(),
        )
        return

    await message.answer(
        "Не смог определить код страны по названию.\n\n"
        "Введите название, телефонный код или формат <code>код название</code>, например <code>Niue</code>, <code>+500</code>, <code>+683</code> или <code>uz Uzbekistan</code>.",
        reply_markup=back_kb("countries"),
    )


@router.callback_query(F.data == "country_add")
async def country_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CountriesStates.waiting_add_code)
    await callback.message.edit_text(
        "➕ Введите код или название страны.\n\n"
        "Можно добавить страну даже если ее сейчас нет в наличии: "
        "<code>uz</code>, <code>Uzbekistan</code>, <code>Узбекистан</code>, "
        "<code>Niue</code>, <code>+500</code>, <code>+683</code> или <code>uz Uzbekistan</code>.",
        reply_markup=back_kb("countries"),
    )
    await callback.answer()


@router.message(CountriesStates.waiting_add_code)
async def country_add_code(message: Message, state: FSMContext, db, tg_lion) -> None:
    user = await db.ensure_user(message.from_user.id)
    raw_value = message.text.strip()
    resolved = resolve_country(raw_value)

    if not resolved:
        await message.answer(
            "Не смог определить страну.\n\n"
            "Введите 2-буквенный код, название, телефонный код или формат <code>код название</code>, "
            "например <code>Niue</code>, <code>+500</code>, <code>+683</code> или <code>uz Uzbekistan</code>.",
            reply_markup=back_kb("countries"),
        )
        return

    code = resolved.code
    name = resolved.name
    if user.api_key and user.your_id:
        try:
            info = await tg_lion.country_info(user.api_key, user.your_id, code)
            name = info.name or name
        except TGLionApiError:
            pass

    await db.add_country(message.from_user.id, code, name)
    await state.clear()
    await message.answer(
        "✅ Страна добавлена в мониторинг.\n\n"
        f"🌍 {name} · <code>{code.upper()}</code>",
        reply_markup=countries_kb(),
    )


@router.callback_query(F.data == "country_remove")
async def country_remove(callback: CallbackQuery, db, state: FSMContext) -> None:
    selected = await db.get_user_countries(callback.from_user.id)
    if selected:
        await callback.message.edit_text("➖ Выберите страну для удаления.", reply_markup=country_remove_kb(selected))
    else:
        await state.set_state(CountriesStates.waiting_remove_code)
        await callback.message.edit_text("Список пуст. Можно ввести код для удаления вручную.", reply_markup=back_kb("countries"))
    await callback.answer()


@router.callback_query(F.data.startswith("country_remove_pick:"))
async def country_remove_pick(callback: CallbackQuery, db) -> None:
    code = normalize_code(callback.data.split(":", 1)[1])
    await db.remove_country(callback.from_user.id, code)
    await callback.message.edit_text(await countries_text(db, callback.from_user.id), reply_markup=countries_kb())
    await callback.answer("Страна удалена")


@router.message(CountriesStates.waiting_remove_code)
async def country_remove_code(message: Message, state: FSMContext, db) -> None:
    resolved = resolve_country(message.text.strip())
    code = normalize_code(resolved.code if resolved else message.text.strip())
    await db.remove_country(message.from_user.id, code)
    await state.clear()
    await message.answer(await countries_text(db, message.from_user.id), reply_markup=countries_kb())


@router.callback_query(F.data == "countries_clear")
async def countries_clear(callback: CallbackQuery, db) -> None:
    await db.clear_countries(callback.from_user.id)
    await callback.message.edit_text("🧹 Список стран очищен. Теперь мониторятся все страны.", reply_markup=countries_kb())
    await callback.answer()
