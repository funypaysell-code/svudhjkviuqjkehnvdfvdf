from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account"))
    builder.row(InlineKeyboardButton(text="📋 Мои мониторинги", callback_data="my_monitors"))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats"))
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Выдать доступ", callback_data="admin_allow"))
    builder.row(InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban"))
    builder.row(InlineKeyboardButton(text="✔️ Разбанить", callback_data="admin_unban"))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить мониторинг", callback_data="admin_del_monitor"))
    builder.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


def monitors_list_kb(accounts: list) -> InlineKeyboardMarkup:
    """Keyboard listing user's monitored accounts."""
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        status = "🟢" if acc["is_active"] else "⏸"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} @{acc['target_username']}",
                callback_data=f"monitor_detail:{acc['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return builder.as_markup()


def monitor_detail_kb(account_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "⏸ Поставить на паузу" if is_active else "▶️ Возобновить"
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=f"toggle_monitor:{account_id}"))
    builder.row(InlineKeyboardButton(text="📜 История изменений", callback_data=f"monitor_log:{account_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить мониторинг", callback_data=f"delete_monitor:{account_id}"))
    builder.row(InlineKeyboardButton(text="🔙 К списку", callback_data="my_monitors"))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


def confirm_delete_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{account_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"monitor_detail:{account_id}"),
    )
    return builder.as_markup()
