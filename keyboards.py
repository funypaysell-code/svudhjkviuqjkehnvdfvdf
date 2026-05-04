from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api_client import CountryInfo


def main_menu_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("🔎 Мониторинг", "monitoring"), ("🤖 Автоскуп", "autobuy")],
            [("👤 Мониторинг TG акков", "tg_accounts_menu")],
            [("🌍 Страны", "countries"), ("💵 Цена", "price")],
            [("⏱️ Интервал", "interval"), ("🔐 API настройки", "api_settings")],
            [("💰 Баланс", "balance"), ("📊 Статистика", "stats")],
            [("⚙️ Помощь", "help")],
        ]
    )


def api_settings_kb(has_api: bool) -> InlineKeyboardMarkup:
    rows = [
        [("🔑 Указать apiKey", "api_set_key"), ("🆔 Указать YourID", "api_set_your_id")],
        [("✅ Проверить", "api_check"), ("🗑 Удалить", "api_delete")],
        [("⬅️ Назад", "main_menu")],
    ]
    if not has_api:
        rows[1] = [("✅ Проверить", "api_check")]
    return _rows(rows)


def monitoring_kb(enabled: bool) -> InlineKeyboardMarkup:
    return _rows(
        [
            [("⏸ Выключить" if enabled else "▶️ Включить", "monitor_toggle")],
            [("🤖 Автоскуп", "autobuy"), ("🌍 Страны", "countries")],
            [("💵 Цена", "price"), ("⏱️ Интервал", "interval")],
            [("🔔 Настройки уведомлений", "monitor_notifications")],
            [("🔄 Обновить статус", "monitoring")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def monitor_notifications_kb(country_enabled: bool, autobuy_enabled: bool) -> InlineKeyboardMarkup:
    return _rows(
        [
            [("🌍 Страна: ON" if country_enabled else "🌍 Страна: OFF", "monitor_notifications_toggle_country")],
            [("🔁 Повтор страны", "monitor_notifications_repeat_country")],
            [("🤖 Автопокупка: ON" if autobuy_enabled else "🤖 Автопокупка: OFF", "monitor_notifications_toggle_autobuy")],
            [("🔁 Повтор автопокупки", "monitor_notifications_repeat_autobuy")],
            [("🌙 Тихие часы", "monitor_notifications_quiet_hours")],
            [("🚨 Эскалация до подтверждения", "monitor_notifications_escalation")],
            [("🌍 Критичные страны", "monitor_notifications_critical")],
            [("⬅️ Назад", "monitoring"), ("🏠 Главное меню", "main_menu")],
        ]
    )


def critical_countries_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("➕ Добавить/обновить", "critical_add"), ("➖ Удалить", "critical_remove")],
            [("🧹 Очистить", "critical_clear")],
            [("⬅️ Назад", "monitor_notifications")],
        ]
    )


def alert_ack_kb(country_code: str) -> InlineKeyboardMarkup:
    return _rows([[("✅ Принял, остановить", f"alert_ack:{country_code}")]])


def countries_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("📋 Доступные", "countries_available"), ("🔍 Поиск", "country_search")],
            [("➕ Добавить страну", "country_add"), ("➖ Удалить страну", "country_remove")],
            [("🧹 Очистить", "countries_clear")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def country_list_kb(countries: list[CountryInfo], prefix: str = "country_pick") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for country in countries[:30]:
        label = f"{country.name} · {country.code.upper()}"
        builder.button(text=label[:60], callback_data=f"{prefix}:{country.code}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="countries"))
    return builder.as_markup()


def country_remove_kb(countries: list[dict[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for country in countries[:40]:
        builder.button(
            text=f"{country['country_name']} · {country['country_code'].upper()}",
            callback_data=f"country_remove_pick:{country['country_code']}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="countries"))
    return builder.as_markup()


def price_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("✏️ Задать лимит", "price_set"), ("♻️ Сбросить", "price_reset")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def interval_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("5 сек", "interval_set:5"), ("10 сек", "interval_set:10"), ("30 сек", "interval_set:30")],
            [("1 мин", "interval_set:60"), ("5 мин", "interval_set:300")],
            [("✏️ Ввести вручную", "interval_manual")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def balance_kb() -> InlineKeyboardMarkup:
    return _rows([[("🔄 Обновить", "balance")], [("⬅️ Назад", "main_menu")]])


def autobuy_kb(enabled: bool, auto_code: bool) -> InlineKeyboardMarkup:
    return _rows(
        [
            [("⏸ Выключить автоскуп" if enabled else "▶️ Включить автоскуп", "autobuy_toggle")],
            [("💵 Цена от", "autobuy_min_price"), ("💵 Цена до", "autobuy_max_price")],
            [("💰 Стоп-баланс", "autobuy_stop_balance"), ("🎯 Лимиты", "autobuy_limits")],
            [("🔑 Автокод: ON" if auto_code else "🔑 Автокод: OFF", "autobuy_toggle_code")],
            [("📦 Покупки", "autobuy_purchases"), ("♻️ Сбросить", "autobuy_reset")],
            [("🌍 Страны", "countries"), ("⏱️ Интервал", "interval")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def autobuy_limits_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("Всего покупок", "autobuy_total_limit"), ("В день", "autobuy_daily_limit")],
            [("Интервал кода", "autobuy_code_interval")],
            [("⬅️ Назад", "autobuy"), ("🏠 Главное меню", "main_menu")],
        ]
    )


def back_kb(target: str = "main_menu") -> InlineKeyboardMarkup:
    return _rows([[("⬅️ Назад", target), ("🏠 Главное меню", "main_menu")]])


def tg_accounts_menu_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("➕ Добавить аккаунт", "tg_accounts_add"), ("📋 Список", "tg_accounts_list")],
            [("⏱️ Задержка проверки", "tg_accounts_interval")],
            [("⬅️ Назад", "main_menu")],
        ]
    )


def tg_accounts_list_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts[:40]:
        status = "🟢" if account["is_active"] else "⏸"
        label = account["target_label"]
        builder.button(text=f"{status} {label}"[:64], callback_data=f"tg_accounts_open:{account['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="tg_accounts_menu"))
    return builder.as_markup()


def tg_account_detail_kb(account_id: int, is_active: bool) -> InlineKeyboardMarkup:
    return _rows(
        [
            [("⏸ Пауза" if is_active else "▶️ Возобновить", f"tg_accounts_toggle:{account_id}")],
            [("🗑 Удалить", f"tg_accounts_delete:{account_id}")],
            [("⬅️ К списку", "tg_accounts_list"), ("🏠 Главное меню", "main_menu")],
        ]
    )


def admin_menu_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("👥 Пользователи", "admin_users"), ("📊 Общая статистика", "admin_stats")],
            [("🔐 Управление доступом", "admin_access"), ("📈 Логи / Активность", "admin_logs")],
            [("⚙️ Настройки", "admin_settings")],
            [("🏠 В главное меню", "main_menu")],
        ]
    )


def admin_users_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("➕ Добавить", "admin_user_add"), ("➖ Удалить", "admin_user_delete")],
            [("📋 Список", "admin_user_list"), ("🔎 Найти", "admin_user_view")],
            [("⛔ Забанить", "admin_user_ban"), ("✅ Разбанить", "admin_user_unban")],
            [("⬅️ Назад", "admin_menu"), ("🏠 В главное меню", "main_menu")],
        ]
    )


def admin_access_kb(whitelist_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔓 Выключить whitelist" if whitelist_enabled else "🔒 Включить whitelist"
    return _rows(
        [
            [(toggle_text, "admin_whitelist_toggle")],
            [("📣 Broadcast", "admin_broadcast")],
            [("⬅️ Назад", "admin_menu"), ("🏠 В главное меню", "main_menu")],
        ]
    )


def admin_logs_kb() -> InlineKeyboardMarkup:
    return _rows(
        [
            [("👤 Действия", "admin_logs_actions"), ("🔥 Алерты", "admin_logs_alerts")],
            [("🤖 Автоскуп", "admin_logs_autobuy"), ("⚠️ Ошибки API", "admin_logs_api_errors")],
            [("⬅️ Назад", "admin_menu"), ("🏠 В главное меню", "main_menu")],
        ]
    )


def admin_back_kb(target: str = "admin_menu") -> InlineKeyboardMarkup:
    return _rows([[("⬅️ Назад", target), ("🏠 В главное меню", "main_menu")]])


def _rows(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback) for text, callback in row]
            for row in rows
        ]
    )
