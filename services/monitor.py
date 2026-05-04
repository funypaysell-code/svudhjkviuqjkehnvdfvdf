from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re

from aiogram import Bot

from api_client import CountryInfo, TGLionApiError
from country_utils import normalize_code
from database import Database, User
from keyboards import alert_ack_kb


logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(self, bot: Bot, db: Database, tg_lion, alert_cooldown_seconds: int = 300) -> None:
        self.bot = bot
        self.db = db
        self.tg_lion = tg_lion
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self._task: asyncio.Task | None = None
        self._next_check: dict[int, float] = {}
        self._next_code_check: dict[int, float] = {}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="tg-lion-monitor")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        logger.info("Monitor service started")
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("Monitor tick failed")
            await asyncio.sleep(1)

    async def _tick(self) -> None:
        now = asyncio.get_running_loop().time()
        users = await self.db.get_enabled_users()
        active_ids = {user.user_id for user in users}
        for user_id in list(self._next_check):
            if user_id not in active_ids:
                self._next_check.pop(user_id, None)

        for user in users:
            if now < self._next_check.get(user.user_id, 0):
                continue
            self._next_check[user.user_id] = now + max(5, user.interval_seconds)
            await self._check_user(user)
        await self._process_escalations()
        await self._poll_codes(now)

    async def _check_user(self, user: User) -> None:
        if not user.api_key or not user.your_id:
            return
        try:
            countries = await self.tg_lion.available_countries(user.api_key, user.your_id)
        except TGLionApiError as exc:
            logger.warning("TG-Lion check failed for user %s: %s", user.user_id, exc)
            await self.db.add_log(user.user_id, f"api_error:{exc}")
            return

        await self.db.increment_checks(user.user_id)
        selected = await self.db.get_user_countries(user.user_id)
        # Normalize all selected codes to lowercase for consistent comparison
        selected_codes = {normalize_code(item["country_code"]) for item in selected}
        autobuy = await self.db.ensure_autobuy_settings(user.user_id)

        for country in countries:
            # Normalize country code for comparison
            normalized_country_code = normalize_code(country.code)
            
            if selected_codes and normalized_country_code not in selected_codes:
                continue
            if country.qty <= 0:
                continue
            if user.max_price is not None and (country.price is None or country.price > user.max_price):
                continue
            if autobuy.enabled:
                bought = await self._try_autobuy(user, country, autobuy)
                if bought:
                    continue
            if not await self._can_send(user.user_id, normalized_country_code):
                continue
            await self._send_alert(user, country, escalation=False)
            await self.db.set_last_alert_time(user.user_id, normalized_country_code)
            await self.db.increment_alerts(user.user_id)
            await self.db.add_log(user.user_id, f"alert_sent:{normalized_country_code}")
            if user.escalation_enabled and user.country_alert_enabled:
                next_send_at = (datetime.now(timezone.utc) + timedelta(seconds=user.escalation_interval_seconds)).isoformat()
                await self.db.upsert_pending_country_alert(
                    user_id=user.user_id,
                    country_code=normalized_country_code,
                    country_name=country.name,
                    price=country.price,
                    qty=country.qty,
                    next_send_at=next_send_at,
                )

    async def _can_send(self, user_id: int, country_code: str) -> bool:
        last = await self.db.get_last_alert_time(user_id, country_code)
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - last_dt).total_seconds() >= self.alert_cooldown_seconds

    async def _send_alert(self, user: User, country: CountryInfo, escalation: bool) -> None:
        if not user.country_alert_enabled:
            return
        if self._is_quiet_hours(user) and not await self._is_critical_country(user.user_id, country.code):
            return
        limit = "без лимита" if user.max_price is None else f"до {user.max_price:.2f}$"
        price = "не указана" if country.price is None else f"{country.price:.2f}$"
        critical_repeat = await self.db.get_critical_repeat_for_country(user.user_id, country.code)
        title = "🚨 <b>Эскалация алерта</b>\n\n" if escalation else "🔥 <b>Найдено по фильтру</b>\n\n"
        text = (
            f"{title}"
            f"🌍 Страна: <b>{country.name}</b> {flag_emoji(country.code)}\n"
            f"🏷 Код: <b>{country.code.upper()}</b> / <code>{country.code.lower()}</code>\n"
            f"💵 Цена: <b>{price}</b>\n"
            f"📦 Количество: <b>{country.qty}</b>\n"
            f"🎯 Лимит: <b>{limit}</b>\n"
            f"⏱️ Проверка: <b>{user.interval_seconds} сек</b>"
        )
        repeat_count = max(1, int(critical_repeat if critical_repeat is not None else user.alert_repeat_count))
        markup = alert_ack_kb(country.code.lower()) if user.escalation_enabled else None
        for _ in range(repeat_count):
            await self.bot.send_message(user.user_id, text, reply_markup=markup)

    async def _try_autobuy(self, user: User, country: CountryInfo, settings) -> bool:
        if not user.api_key or not user.your_id:
            return False
        if country.price is None:
            return False
        if settings.min_price is not None and country.price < settings.min_price:
            return False

        max_price = settings.max_price if settings.max_price is not None else user.max_price
        if max_price is not None and country.price > max_price:
            return False

        if await self.db.count_purchases(user.user_id) >= settings.max_purchases_total:
            await self.db.update_autobuy_setting(user.user_id, "enabled", 0)
            await self.bot.send_message(user.user_id, "🤖 Автоскуп остановлен: достигнут общий лимит покупок.")
            return False
        if await self.db.count_purchases_today(user.user_id) >= settings.max_purchases_day:
            await self.bot.send_message(user.user_id, "🤖 Автоскуп сегодня на паузе: достигнут дневной лимит.")
            return False
        if await self.db.has_recent_purchase_for_country(user.user_id, country.code):
            return False

        if settings.stop_balance is not None:
            balance = await self._safe_balance(user)
            if balance is not None and balance <= settings.stop_balance:
                await self.db.update_autobuy_setting(user.user_id, "enabled", 0)
                await self.bot.send_message(
                    user.user_id,
                    f"💰 Автоскуп остановлен: баланс {balance:.2f}$ дошел до стоп-уровня {settings.stop_balance:.2f}$.",
                )
                return False

        try:
            purchase = await self.tg_lion.get_number(user.api_key, user.your_id, country.code, max_price)
        except TGLionApiError as exc:
            logger.warning("Autobuy failed for user %s: %s", user.user_id, exc)
            await self.db.add_log(user.user_id, f"api_error:autobuy:{exc}")
            return False

        purchase_id = await self.db.create_purchase(
            user.user_id,
            country.code,
            purchase.country_name or country.name,
            purchase.number,
            purchase.price,
            purchase.new_balance,
        )
        await self.db.set_last_alert_time(user.user_id, country.code)
        await self.db.increment_alerts(user.user_id)
        await self._send_purchase_message(user, country, purchase, purchase_id)

        if settings.stop_balance is not None and purchase.new_balance is not None and purchase.new_balance <= settings.stop_balance:
            await self.db.update_autobuy_setting(user.user_id, "enabled", 0)
            await self.bot.send_message(user.user_id, "💰 Автоскуп выключен: достигнут стоп-баланс после покупки.")
        return True

    async def _send_purchase_message(self, user: User, country: CountryInfo, purchase, purchase_id: int) -> None:
        if not user.autobuy_alert_enabled:
            return
        price = "не указана" if purchase.price is None else f"{purchase.price:.2f}$"
        balance = "не указан" if purchase.new_balance is None else f"{purchase.new_balance:.2f}$"
        text = (
            "✅ <b>Автоскуп выполнен</b>\n\n"
            f"🌍 Страна: <b>{purchase.country_name or country.name}</b> {flag_emoji(country.code)}\n"
            f"🏷 Код: <b>{country.code.upper()}</b>\n"
            f"📱 Номер: <code>{purchase.number}</code>\n"
            f"💵 Цена: <b>{price}</b>\n"
            f"💰 Новый баланс: <b>{balance}</b>\n"
            f"🧾 ID покупки: <code>{purchase_id}</code>\n\n"
            "⏳ Номер висит тут. Если включен автокод, я сам пришлю код входа, когда TG-Lion его отдаст."
        )
        repeat_count = max(1, int(user.autobuy_alert_repeat_count))
        for _ in range(repeat_count):
            await self.bot.send_message(user.user_id, text)

    async def _poll_codes(self, now: float) -> None:
        purchases = await self.db.get_pending_code_purchases()
        for purchase in purchases:
            purchase_id = purchase["id"]
            if now < self._next_code_check.get(purchase_id, 0):
                continue
            self._next_code_check[purchase_id] = now + max(10, int(purchase["code_check_seconds"]))
            try:
                login = await self.tg_lion.get_code(purchase["api_key"], purchase["your_id"], purchase["number"])
            except TGLionApiError as exc:
                await self.db.add_log(purchase["user_id"], f"api_error:get_code:{exc}")
                continue
            if not login.code:
                continue
            await self.db.complete_purchase_code(purchase_id, login.code, login.password)
            await self.db.add_log(purchase["user_id"], f"autobuy_code:{purchase['number']}")
            password_text = login.password or "не указан"
            await self.bot.send_message(
                purchase["user_id"],
                "🔑 <b>Код получен</b>\n\n"
                f"📱 Номер: <code>{purchase['number']}</code>\n"
                f"🔐 Код: <code>{login.code}</code>\n"
                f"🔒 Пароль/2FA: <code>{password_text}</code>",
            )

    async def _safe_balance(self, user: User) -> float | None:
        if not user.api_key or not user.your_id:
            return None
        try:
            raw_balance = await self.tg_lion.get_balance(user.api_key, user.your_id)
        except TGLionApiError as exc:
            await self.db.add_log(user.user_id, f"api_error:balance:{exc}")
            return None
        match = re.search(r"\d+(?:[.,]\d+)?", raw_balance)
        if not match:
            return None
        return float(match.group(0).replace(",", "."))

    async def _is_critical_country(self, user_id: int, country_code: str) -> bool:
        return (await self.db.get_critical_repeat_for_country(user_id, country_code)) is not None

    def _is_quiet_hours(self, user: User) -> bool:
        if not user.quiet_hours_enabled:
            return False
        current_hour = datetime.now(timezone.utc).hour
        start = user.quiet_start_hour % 24
        end = user.quiet_end_hour % 24
        if start == end:
            return True
        if start < end:
            return start <= current_hour < end
        return current_hour >= start or current_hour < end

    async def _process_escalations(self) -> None:
        now_dt = datetime.now(timezone.utc)
        rows = await self.db.get_due_pending_country_alerts(now_dt.isoformat())
        for row in rows:
            user = await self.db.get_user(int(row["user_id"]))
            if not user or not user.escalation_enabled or not user.country_alert_enabled:
                await self.db.remove_pending_country_alert(int(row["user_id"]), row["country_code"])
                continue
            country = CountryInfo(
                code=row["country_code"],
                name=row["country_name"],
                qty=int(row["qty"]),
                price=row["price"],
            )
            await self._send_alert(user, country, escalation=True)
            next_send_at = (now_dt + timedelta(seconds=user.escalation_interval_seconds)).isoformat()
            await self.db.upsert_pending_country_alert(
                user_id=int(row["user_id"]),
                country_code=row["country_code"],
                country_name=row["country_name"],
                price=row["price"],
                qty=int(row["qty"]),
                next_send_at=next_send_at,
            )


def flag_emoji(code: str) -> str:
    code = code.upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
