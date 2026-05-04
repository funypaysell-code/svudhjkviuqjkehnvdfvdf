from aiogram.fsm.state import State, StatesGroup


class AddAccountForm(StatesGroup):
    waiting_for_username = State()


class AdminForm(StatesGroup):
    waiting_for_user_id_allow = State()
    waiting_for_user_id_ban = State()
    waiting_for_user_id_unban = State()
    waiting_for_account_id_delete = State()
