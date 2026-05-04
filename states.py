from aiogram.fsm.state import State, StatesGroup


class ApiSettingsStates(StatesGroup):
    waiting_api_key = State()
    waiting_your_id = State()


class PriceStates(StatesGroup):
    waiting_max_price = State()


class IntervalStates(StatesGroup):
    waiting_interval = State()


class MonitoringStates(StatesGroup):
    waiting_alert_repeat = State()
    waiting_country_alert_repeat = State()
    waiting_autobuy_alert_repeat = State()
    waiting_quiet_hours = State()
    waiting_escalation_interval = State()
    waiting_critical_country_add = State()
    waiting_critical_country_remove = State()


class CountriesStates(StatesGroup):
    waiting_search = State()
    waiting_add_code = State()
    waiting_remove_code = State()


class AdminStates(StatesGroup):
    waiting_add_user = State()
    waiting_delete_user = State()
    waiting_view_user = State()
    waiting_ban_user = State()
    waiting_unban_user = State()
    waiting_broadcast = State()


class AutobuyStates(StatesGroup):
    waiting_min_price = State()
    waiting_max_price = State()
    waiting_stop_balance = State()
    waiting_total_limit = State()
    waiting_daily_limit = State()
    waiting_code_interval = State()


class TgAccountsStates(StatesGroup):
    waiting_identifier = State()
    waiting_interval = State()
