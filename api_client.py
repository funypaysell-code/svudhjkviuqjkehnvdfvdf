from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import aiohttp

from country_utils import normalize_code


logger = logging.getLogger(__name__)


class TGLionApiError(Exception):
    pass


@dataclass(slots=True)
class CountryInfo:
    code: str
    name: str
    price: float | None = None
    qty: int = 0


@dataclass(slots=True)
class NumberPurchase:
    country_code: str
    country_name: str
    number: str
    price: float | None
    new_balance: float | None


@dataclass(slots=True)
class LoginCode:
    number: str
    code: str | None
    password: str | None


class TGLionClient:
    def __init__(self, base_url: str, timeout: int = 15) -> None:
        self.base_url = base_url
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def available_countries(self, api_key: str, your_id: str) -> list[CountryInfo]:
        payload = await self._request(
            {
                "action": "available_countries",
                "apiKey": api_key,
                "YourID": your_id,
            }
        )
        return self._parse_countries(payload)

    async def country_info(self, api_key: str, your_id: str, country_code: str) -> CountryInfo:
        payload = await self._request(
            {
                "action": "country_info",
                "apiKey": api_key,
                "YourID": your_id,
                "country_code": normalize_code(country_code),
            }
        )
        countries = self._parse_countries(payload, fallback_code=normalize_code(country_code))
        if countries:
            return countries[0]
        raise TGLionApiError("Пустой ответ по стране")

    async def get_balance(self, api_key: str, your_id: str) -> str:
        payload = await self._request(
            {
                "action": "get_balance",
                "apiKey": api_key,
                "YourID": your_id,
            }
        )
        if isinstance(payload, dict):
            self._raise_if_error(payload)
            for key in ("balance", "Balance", "money", "amount", "data"):
                if key in payload and not isinstance(payload[key], (dict, list)):
                    return str(payload[key])
        if isinstance(payload, (str, int, float)):
            return str(payload)
        return str(payload)

    async def get_number(
        self,
        api_key: str,
        your_id: str,
        country_code: str,
        max_price: float | None = None,
    ) -> NumberPurchase:
        params = {
            "action": "getNumber",
            "apiKey": api_key,
            "YourID": your_id,
            "country_code": normalize_code(country_code),
        }
        if max_price is not None:
            params["maxPrice"] = f"{max_price:.2f}"
        payload = await self._request(params)
        if not isinstance(payload, dict):
            raise TGLionApiError("TG-Lion вернул неожиданный ответ покупки")

        number = self._first_text(payload, "Number", "number", "phone")
        if not number:
            raise TGLionApiError(str(payload.get("message") or "Номер не получен"))
        return NumberPurchase(
            country_code=normalize_code(self._first_text(payload, "code", "country_code")) or normalize_code(country_code),
            country_name=self._first_text(payload, "name", "country_name") or country_code.upper(),
            number=number,
            price=self._first_float(payload, "price", "cost", "amount"),
            new_balance=self._first_float(payload, "new_balance", "balance"),
        )

    async def get_code(self, api_key: str, your_id: str, number: str) -> LoginCode:
        payload = await self._request(
            {
                "action": "getCode",
                "apiKey": api_key,
                "YourID": your_id,
                "number": number,
            }
        )
        if not isinstance(payload, dict):
            raise TGLionApiError("TG-Lion вернул неожиданный ответ кода")
        code = self._first_text(payload, "code", "Code", "sms")
        password = self._first_text(payload, "pass", "password", "Password", "2fa")
        return LoginCode(
            number=self._first_text(payload, "Number", "number") or number,
            code=code or None,
            password=password or None,
        )

    async def _request(self, params: dict[str, str]) -> Any:
        safe_params = {k: ("***" if k == "apiKey" else v) for k, v in params.items()}
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.base_url, params=params) as response:
                    text = await response.text()
                    if response.status >= 400:
                        logger.warning("TG-Lion HTTP %s for params %s", response.status, safe_params)
                        raise TGLionApiError(f"HTTP {response.status}: API недоступен")
                    try:
                        payload = await response.json(content_type=None)
                    except Exception:
                        payload = text.strip()
        except TimeoutError as exc:
            raise TGLionApiError("Таймаут запроса к TG-Lion") from exc
        except aiohttp.ClientError as exc:
            raise TGLionApiError("Ошибка соединения с TG-Lion") from exc

        if isinstance(payload, dict):
            self._raise_if_error(payload)
        return payload

    @staticmethod
    def _raise_if_error(payload: dict[str, Any]) -> None:
        status = str(payload.get("status", payload.get("success", ""))).lower()
        error = payload.get("error") or payload.get("message") or payload.get("msg")
        if status in {"false", "error", "fail", "failed", "0"}:
            raise TGLionApiError(str(error or "TG-Lion вернул ошибку"))
        if error and "error" in str(error).lower():
            raise TGLionApiError(str(error))

    def _parse_countries(self, payload: Any, fallback_code: str | None = None) -> list[CountryInfo]:
        raw_items = self._extract_items(payload)
        countries: list[CountryInfo] = []

        if isinstance(raw_items, dict):
            iterator = raw_items.items()
        elif isinstance(raw_items, list):
            iterator = enumerate(raw_items)
        else:
            iterator = [(fallback_code or "", raw_items)]

        for key, value in iterator:
            item = value if isinstance(value, dict) else {"value": value}
            code = self._first_text(item, "country_code", "code", "country", "iso", "short_name")
            if not code and isinstance(key, str) and len(key) <= 4:
                code = key
            if not code:
                code = fallback_code or ""

            name = self._first_text(item, "country_name", "name", "title", "country")
            if not name or name.lower() == code.lower():
                name = self._country_name_from_code(code)

            price = self._first_float(item, "price", "cost", "amount", "rate")
            qty = self._first_int(item, "qty", "quantity", "count", "available", "numbers", "value")

            # Normalize code to lowercase for consistency across all operations
            normalized_code = normalize_code(code)
            if normalized_code:
                countries.append(CountryInfo(code=normalized_code, name=name, price=price, qty=qty))

        return countries

    @staticmethod
    def _extract_items(payload: Any) -> Any:
        if isinstance(payload, dict):
            for key in ("countries", "data", "result", "items", "list"):
                if key in payload:
                    return payload[key]
        return payload

    @staticmethod
    def _first_text(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                return str(value).strip()
        return ""

    @staticmethod
    def _first_float(item: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = item.get(key)
            try:
                if value is not None and str(value).strip() != "":
                    return float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _first_int(item: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = item.get(key)
            try:
                if value is not None and str(value).strip() != "":
                    return int(float(str(value).replace(",", ".")))
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _country_name_from_code(code: str) -> str:
        return code.upper() if code else "Unknown"
