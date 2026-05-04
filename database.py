from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from country_utils import normalize_code


DEFAULT_INTERVAL = 30
DEFAULT_TG_ACCOUNTS_INTERVAL = 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class User:
    user_id: int
    api_key: str | None
    your_id: str | None
    monitoring_enabled: bool
    max_price: float | None
    interval_seconds: int
    alert_repeat_count: int
    country_alert_enabled: bool
    autobuy_alert_enabled: bool
    autobuy_alert_repeat_count: int
    quiet_hours_enabled: bool
    quiet_start_hour: int
    quiet_end_hour: int
    escalation_enabled: bool
    escalation_interval_seconds: int
    created_at: str
    updated_at: str


@dataclass(slots=True)
class AutobuySettings:
    user_id: int
    enabled: bool
    min_price: float | None
    max_price: float | None
    stop_balance: float | None
    max_purchases_total: int
    max_purchases_day: int
    auto_get_code: bool
    code_check_seconds: int


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    api_key TEXT,
                    your_id TEXT,
                    monitoring_enabled INTEGER NOT NULL DEFAULT 0,
                    max_price REAL,
                    interval_seconds INTEGER NOT NULL DEFAULT 30,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tg_monitored_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    target_label TEXT NOT NULL,
                    target_username TEXT,
                    target_id INTEGER,
                    display_name TEXT,
                    bio TEXT,
                    photo_hash TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    UNIQUE(owner_id, target_label),
                    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tg_change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    field TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    changed_at TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES tg_monitored_accounts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS critical_countries (
                    user_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    repeat_count INTEGER NOT NULL DEFAULT 2,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, country_code),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS pending_country_alerts (
                    user_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    price REAL,
                    qty INTEGER NOT NULL,
                    next_send_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, country_code),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS countries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    UNIQUE(user_id, country_code),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS stats (
                    user_id INTEGER PRIMARY KEY,
                    checks_count INTEGER NOT NULL DEFAULT 0,
                    alerts_count INTEGER NOT NULL DEFAULT 0,
                    last_alert_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS alert_cache (
                    user_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    last_sent_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, country_code),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS allowed_users (
                    user_id INTEGER PRIMARY KEY,
                    added_at TEXT NOT NULL,
                    is_banned INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS autobuy_settings (
                    user_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    min_price REAL,
                    max_price REAL,
                    stop_balance REAL,
                    max_purchases_total INTEGER NOT NULL DEFAULT 1,
                    max_purchases_day INTEGER NOT NULL DEFAULT 3,
                    auto_get_code INTEGER NOT NULL DEFAULT 1,
                    code_check_seconds INTEGER NOT NULL DEFAULT 20,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    number TEXT NOT NULL,
                    price REAL,
                    status TEXT NOT NULL DEFAULT 'pending_code',
                    login_code TEXT,
                    password TEXT,
                    new_balance REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, number),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                INSERT OR IGNORE INTO settings(key, value) VALUES ('whitelist_enabled', '1');
                """
            )
            await self._ensure_column(db, "users", "tg_accounts_interval_seconds", "INTEGER NOT NULL DEFAULT 60")
            await self._ensure_column(db, "users", "alert_repeat_count", "INTEGER NOT NULL DEFAULT 1")
            await self._ensure_column(db, "users", "country_alert_enabled", "INTEGER NOT NULL DEFAULT 1")
            await self._ensure_column(db, "users", "autobuy_alert_enabled", "INTEGER NOT NULL DEFAULT 1")
            await self._ensure_column(db, "users", "autobuy_alert_repeat_count", "INTEGER NOT NULL DEFAULT 1")
            await self._ensure_column(db, "users", "quiet_hours_enabled", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "quiet_start_hour", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "quiet_end_hour", "INTEGER NOT NULL DEFAULT 8")
            await self._ensure_column(db, "users", "escalation_enabled", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "escalation_interval_seconds", "INTEGER NOT NULL DEFAULT 45")
            await db.commit()

    async def _ensure_column(self, db: aiosqlite.Connection, table_name: str, column_name: str, column_sql: str) -> None:
        cursor = await db.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}
        if column_name in existing:
            return
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    async def ensure_user(self, user_id: int) -> User:
        now = utc_now()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users(
                    user_id, interval_seconds, tg_accounts_interval_seconds,
                    alert_repeat_count, country_alert_enabled, autobuy_alert_enabled, autobuy_alert_repeat_count,
                    quiet_hours_enabled, quiet_start_hour, quiet_end_hour, escalation_enabled, escalation_interval_seconds,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, DEFAULT_INTERVAL, DEFAULT_TG_ACCOUNTS_INTERVAL,
                    1, 1, 1, 1,
                    0, 0, 8, 0, 45,
                    now, now,
                ),
            )
            await db.execute("INSERT OR IGNORE INTO stats(user_id) VALUES (?)", (user_id,))
            await db.commit()
        user = await self.get_user(user_id)
        assert user is not None
        return user

    async def get_user(self, user_id: int) -> User | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return self._user_from_row(row) if row else None

    async def get_enabled_users(self) -> list[User]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT * FROM users
                WHERE monitoring_enabled = 1 AND api_key IS NOT NULL AND your_id IS NOT NULL
                """
            )
        return [self._user_from_row(row) for row in rows]

    async def get_user_tg_accounts_interval(self, user_id: int) -> int:
        await self.ensure_user(user_id)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT tg_accounts_interval_seconds FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        if not row or row[0] is None:
            return DEFAULT_TG_ACCOUNTS_INTERVAL
        return int(row[0])

    async def set_user_tg_accounts_interval(self, user_id: int, seconds: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET tg_accounts_interval_seconds = ?, updated_at = ? WHERE user_id = ?",
            (seconds, utc_now(), user_id),
        )
        await self.add_log(user_id, f"tg_accounts_interval:{seconds}")

    async def set_api_key(self, user_id: int, api_key: str) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET api_key = ?, updated_at = ? WHERE user_id = ?",
            (api_key, utc_now(), user_id),
        )

    async def set_your_id(self, user_id: int, your_id: str) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET your_id = ?, updated_at = ? WHERE user_id = ?",
            (your_id, utc_now(), user_id),
        )

    async def delete_api_settings(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            """
            UPDATE users
            SET api_key = NULL, your_id = NULL, monitoring_enabled = 0, updated_at = ?
            WHERE user_id = ?
            """,
            (utc_now(), user_id),
        )

    async def set_monitoring(self, user_id: int, enabled: bool) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET monitoring_enabled = ?, updated_at = ? WHERE user_id = ?",
            (int(enabled), utc_now(), user_id),
        )
        await self.add_log(user_id, "monitoring_enabled" if enabled else "monitoring_disabled")

    async def set_max_price(self, user_id: int, price: float | None) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET max_price = ?, updated_at = ? WHERE user_id = ?",
            (price, utc_now(), user_id),
        )
        await self.add_log(user_id, "price_reset" if price is None else f"price_changed:{price:.2f}")

    async def set_interval(self, user_id: int, seconds: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET interval_seconds = ?, updated_at = ? WHERE user_id = ?",
            (seconds, utc_now(), user_id),
        )

    async def set_alert_repeat_count(self, user_id: int, repeat_count: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET alert_repeat_count = ?, updated_at = ? WHERE user_id = ?",
            (repeat_count, utc_now(), user_id),
        )
        await self.add_log(user_id, f"alert_repeat_count:{repeat_count}")

    async def set_country_alert_enabled(self, user_id: int, enabled: bool) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET country_alert_enabled = ?, updated_at = ? WHERE user_id = ?",
            (int(enabled), utc_now(), user_id),
        )
        await self.add_log(user_id, f"country_alert_enabled:{int(enabled)}")

    async def set_autobuy_alert_enabled(self, user_id: int, enabled: bool) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET autobuy_alert_enabled = ?, updated_at = ? WHERE user_id = ?",
            (int(enabled), utc_now(), user_id),
        )
        await self.add_log(user_id, f"autobuy_alert_enabled:{int(enabled)}")

    async def set_autobuy_alert_repeat_count(self, user_id: int, repeat_count: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET autobuy_alert_repeat_count = ?, updated_at = ? WHERE user_id = ?",
            (repeat_count, utc_now(), user_id),
        )
        await self.add_log(user_id, f"autobuy_alert_repeat_count:{repeat_count}")

    async def set_quiet_hours(self, user_id: int, enabled: bool, start_hour: int, end_hour: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            """
            UPDATE users
            SET quiet_hours_enabled = ?, quiet_start_hour = ?, quiet_end_hour = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (int(enabled), start_hour % 24, end_hour % 24, utc_now(), user_id),
        )
        await self.add_log(user_id, f"quiet_hours:{int(enabled)}:{start_hour}-{end_hour}")

    async def set_escalation_enabled(self, user_id: int, enabled: bool) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET escalation_enabled = ?, updated_at = ? WHERE user_id = ?",
            (int(enabled), utc_now(), user_id),
        )
        await self.add_log(user_id, f"escalation_enabled:{int(enabled)}")

    async def set_escalation_interval(self, user_id: int, seconds: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE users SET escalation_interval_seconds = ?, updated_at = ? WHERE user_id = ?",
            (seconds, utc_now(), user_id),
        )
        await self.add_log(user_id, f"escalation_interval_seconds:{seconds}")

    async def get_user_countries(self, user_id: int) -> list[dict[str, str]]:
        await self.ensure_user(user_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT country_code, country_name FROM countries WHERE user_id = ? ORDER BY country_name",
                (user_id,),
            )
        # Normalize codes to lowercase
        return [{"country_code": normalize_code(row["country_code"]), "country_name": row["country_name"]} for row in rows]

    async def add_country(self, user_id: int, code: str, name: str) -> None:
        await self.ensure_user(user_id)
        # Normalize code to lowercase before saving
        normalized_code = normalize_code(code)
        await self._execute(
            """
            INSERT OR REPLACE INTO countries(user_id, country_code, country_name)
            VALUES (?, ?, ?)
            """,
            (user_id, normalized_code, name),
        )
        await self.add_log(user_id, f"country_added:{normalized_code}")

    async def remove_country(self, user_id: int, code: str) -> int:
        await self.ensure_user(user_id)
        # Normalize code before removing
        normalized_code = normalize_code(code)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM countries WHERE user_id = ? AND lower(country_code) = ?",
                (user_id, normalized_code),
            )
            await db.commit()
            rowcount = cur.rowcount
        if rowcount:
            await self.add_log(user_id, f"country_removed:{normalized_code}")
        return rowcount

    async def clear_countries(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute("DELETE FROM countries WHERE user_id = ?", (user_id,))
        await self.add_log(user_id, "countries_cleared")

    async def get_stats(self, user_id: int) -> dict[str, Any]:
        await self.ensure_user(user_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM stats WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return dict(row) if row else {"checks_count": 0, "alerts_count": 0, "last_alert_at": None}

    async def increment_checks(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE stats SET checks_count = checks_count + 1 WHERE user_id = ?",
            (user_id,),
        )

    async def increment_alerts(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            "UPDATE stats SET alerts_count = alerts_count + 1, last_alert_at = ? WHERE user_id = ?",
            (utc_now(), user_id),
        )

    async def get_last_alert_time(self, user_id: int, country_code: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT last_sent_at FROM alert_cache WHERE user_id = ? AND country_code = ?",
                (user_id, normalize_code(country_code)),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def set_last_alert_time(self, user_id: int, country_code: str) -> None:
        await self._execute(
            """
            INSERT INTO alert_cache(user_id, country_code, last_sent_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, country_code) DO UPDATE SET last_sent_at = excluded.last_sent_at
            """,
            (user_id, normalize_code(country_code), utc_now()),
        )

    async def add_allowed_user(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            """
            INSERT INTO allowed_users(user_id, added_at, is_banned)
            VALUES (?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET is_banned = 0
            """,
            (user_id, utc_now()),
        )

    async def delete_allowed_user(self, user_id: int) -> None:
        await self._execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
        await self._execute(
            "UPDATE users SET monitoring_enabled = 0, updated_at = ? WHERE user_id = ?",
            (utc_now(), user_id),
        )

    async def ban_user(self, user_id: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            """
            INSERT INTO allowed_users(user_id, added_at, is_banned)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET is_banned = 1
            """,
            (user_id, utc_now()),
        )
        await self._execute(
            "UPDATE users SET monitoring_enabled = 0, updated_at = ? WHERE user_id = ?",
            (utc_now(), user_id),
        )

    async def unban_user(self, user_id: int) -> None:
        await self._execute(
            "UPDATE allowed_users SET is_banned = 0 WHERE user_id = ?",
            (user_id,),
        )

    async def is_allowed_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT is_banned FROM allowed_users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return bool(row and not row[0])

    async def is_banned_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT is_banned FROM allowed_users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return bool(row and row[0])

    async def count_allowed_users(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM allowed_users WHERE is_banned = 0")
            row = await cursor.fetchone()
        return int(row[0])

    async def get_allowed_users(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT au.user_id, au.added_at, au.is_banned, u.created_at, u.monitoring_enabled
                FROM allowed_users au
                LEFT JOIN users u ON u.user_id = au.user_id
                ORDER BY au.added_at DESC
                """
            )
        return [dict(row) for row in rows]

    async def get_all_users(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT u.*, COALESCE(s.checks_count, 0) AS checks_count,
                       COALESCE(s.alerts_count, 0) AS alerts_count,
                       s.last_alert_at,
                       COALESCE(au.is_banned, 0) AS is_banned,
                       au.added_at AS allowed_at
                FROM users u
                LEFT JOIN stats s ON s.user_id = u.user_id
                LEFT JOIN allowed_users au ON au.user_id = u.user_id
                ORDER BY u.created_at DESC
                """
            )
        return [dict(row) for row in rows]

    async def get_user_details(self, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT u.*, COALESCE(s.checks_count, 0) AS checks_count,
                       COALESCE(s.alerts_count, 0) AS alerts_count,
                       s.last_alert_at,
                       COALESCE(au.is_banned, 0) AS is_banned,
                       au.added_at AS allowed_at,
                       (SELECT COUNT(*) FROM countries c WHERE c.user_id = u.user_id) AS countries_count
                FROM users u
                LEFT JOIN stats s ON s.user_id = u.user_id
                LEFT JOIN allowed_users au ON au.user_id = u.user_id
                WHERE u.user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_global_stats(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE monitoring_enabled = 1) AS active_users,
                    (SELECT COALESCE(SUM(checks_count), 0) FROM stats) AS total_checks,
                    (SELECT COALESCE(SUM(alerts_count), 0) FROM stats) AS total_alerts
                """
            )
            row = await cursor.fetchone()
        return dict(row)

    async def get_top_alert_users(self, limit: int = 5) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT user_id, alerts_count
                FROM stats
                ORDER BY alerts_count DESC, user_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(row) for row in rows]

    async def get_broadcast_users(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            rows = await db.execute_fetchall(
                """
                SELECT u.user_id
                FROM users u
                LEFT JOIN allowed_users au ON au.user_id = u.user_id
                WHERE COALESCE(au.is_banned, 0) = 0
                """
            )
        return [int(row[0]) for row in rows]

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    async def whitelist_enabled(self) -> bool:
        return (await self.get_setting("whitelist_enabled", "1")) == "1"

    async def set_whitelist_enabled(self, enabled: bool) -> None:
        await self.set_setting("whitelist_enabled", "1" if enabled else "0")

    async def add_log(self, user_id: int | None, action: str) -> None:
        await self._execute(
            "INSERT INTO logs(user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action, utc_now()),
        )

    async def get_logs(self, limit: int = 20, pattern: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id, user_id, action, created_at FROM logs"
        params: tuple[Any, ...]
        if pattern:
            query += " WHERE action LIKE ?"
            params = (pattern,)
        else:
            params = ()
        query += " ORDER BY id DESC LIMIT ?"
        params = (*params, limit)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(query, params)
        return [dict(row) for row in rows]

    async def add_tg_monitored_account(
        self,
        owner_id: int,
        target_label: str,
        target_username: str | None,
        target_id: int | None,
        display_name: str | None,
        bio: str | None,
        photo_hash: str | None,
    ) -> int | None:
        await self.ensure_user(owner_id)
        now = utc_now()
        try:
            async with aiosqlite.connect(self.path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO tg_monitored_accounts(
                        owner_id, target_label, target_username, target_id, display_name, bio, photo_hash,
                        is_active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (owner_id, target_label, target_username, target_id, display_name, bio, photo_hash, now, now),
                )
                await db.commit()
                new_id = cursor.lastrowid
            await self.add_log(owner_id, f"tg_account_added:{target_label}")
            return int(new_id) if new_id else None
        except aiosqlite.IntegrityError:
            return None

    async def get_user_tg_monitored_accounts(self, owner_id: int) -> list[dict[str, Any]]:
        await self.ensure_user(owner_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM tg_monitored_accounts WHERE owner_id = ? ORDER BY id DESC",
                (owner_id,),
            )
        return [dict(row) for row in rows]

    async def get_tg_monitored_account(self, owner_id: int, account_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tg_monitored_accounts WHERE id = ? AND owner_id = ?",
                (account_id, owner_id),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_active_tg_monitored_accounts(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT tma.*, u.tg_accounts_interval_seconds
                FROM tg_monitored_accounts tma
                JOIN users u ON u.user_id = tma.owner_id
                LEFT JOIN allowed_users au ON au.user_id = tma.owner_id
                WHERE tma.is_active = 1
                  AND COALESCE(au.is_banned, 0) = 0
                ORDER BY tma.id ASC
                """
            )
        return [dict(row) for row in rows]

    async def toggle_tg_monitored_account(self, owner_id: int, account_id: int) -> bool | None:
        account = await self.get_tg_monitored_account(owner_id, account_id)
        if not account:
            return None
        new_state = 0 if account["is_active"] else 1
        await self._execute(
            "UPDATE tg_monitored_accounts SET is_active = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
            (new_state, utc_now(), account_id, owner_id),
        )
        await self.add_log(owner_id, f"tg_account_toggled:{account_id}:{new_state}")
        return bool(new_state)

    async def delete_tg_monitored_account(self, owner_id: int, account_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM tg_monitored_accounts WHERE id = ? AND owner_id = ?",
                (account_id, owner_id),
            )
            await db.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            await self.add_log(owner_id, f"tg_account_deleted:{account_id}")
        return deleted

    async def update_tg_monitored_snapshot(
        self,
        account_id: int,
        target_label: str,
        target_username: str | None,
        target_id: int | None,
        display_name: str | None,
        bio: str | None,
        photo_hash: str | None,
    ) -> None:
        await self._execute(
            """
            UPDATE tg_monitored_accounts
            SET target_label = ?, target_username = ?, target_id = ?,
                display_name = ?, bio = ?, photo_hash = ?,
                updated_at = ?, last_checked_at = ?
            WHERE id = ?
            """,
            (target_label, target_username, target_id, display_name, bio, photo_hash, utc_now(), utc_now(), account_id),
        )

    async def add_tg_change_log(self, account_id: int, field: str, old_value: str | None, new_value: str | None) -> None:
        await self._execute(
            "INSERT INTO tg_change_log(account_id, field, old_value, new_value, changed_at) VALUES (?, ?, ?, ?, ?)",
            (account_id, field, old_value, new_value, utc_now()),
        )

    async def get_critical_countries(self, user_id: int) -> list[dict[str, Any]]:
        await self.ensure_user(user_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT country_code, repeat_count FROM critical_countries WHERE user_id = ? ORDER BY country_code",
                (user_id,),
            )
        return [dict(row) for row in rows]

    async def get_critical_repeat_for_country(self, user_id: int, country_code: str) -> int | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT repeat_count FROM critical_countries WHERE user_id = ? AND country_code = ?",
                (user_id, normalize_code(country_code)),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def upsert_critical_country(self, user_id: int, country_code: str, repeat_count: int) -> None:
        await self.ensure_user(user_id)
        await self._execute(
            """
            INSERT INTO critical_countries(user_id, country_code, repeat_count, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, country_code) DO UPDATE SET repeat_count = excluded.repeat_count
            """,
            (user_id, normalize_code(country_code), max(1, repeat_count), utc_now()),
        )
        await self.add_log(user_id, f"critical_country_upsert:{normalize_code(country_code)}:{repeat_count}")

    async def remove_critical_country(self, user_id: int, country_code: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM critical_countries WHERE user_id = ? AND country_code = ?",
                (user_id, normalize_code(country_code)),
            )
            await db.commit()
            rowcount = cursor.rowcount
        if rowcount:
            await self.add_log(user_id, f"critical_country_remove:{normalize_code(country_code)}")
        return rowcount

    async def clear_critical_countries(self, user_id: int) -> None:
        await self._execute("DELETE FROM critical_countries WHERE user_id = ?", (user_id,))
        await self.add_log(user_id, "critical_country_clear")

    async def upsert_pending_country_alert(self, user_id: int, country_code: str, country_name: str, price: float | None, qty: int, next_send_at: str) -> None:
        await self._execute(
            """
            INSERT INTO pending_country_alerts(user_id, country_code, country_name, price, qty, next_send_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, country_code) DO UPDATE SET
                country_name = excluded.country_name,
                price = excluded.price,
                qty = excluded.qty,
                next_send_at = excluded.next_send_at
            """,
            (user_id, normalize_code(country_code), country_name, price, qty, next_send_at, utc_now()),
        )

    async def get_due_pending_country_alerts(self, now_iso: str, limit: int = 200) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT p.*, u.max_price, u.interval_seconds, u.alert_repeat_count,
                       u.country_alert_enabled, u.quiet_hours_enabled, u.quiet_start_hour, u.quiet_end_hour,
                       u.escalation_enabled, u.escalation_interval_seconds
                FROM pending_country_alerts p
                JOIN users u ON u.user_id = p.user_id
                LEFT JOIN allowed_users au ON au.user_id = p.user_id
                WHERE p.next_send_at <= ? AND COALESCE(au.is_banned, 0) = 0
                ORDER BY p.next_send_at ASC
                LIMIT ?
                """,
                (now_iso, limit),
            )
        return [dict(row) for row in rows]

    async def remove_pending_country_alert(self, user_id: int, country_code: str) -> None:
        await self._execute(
            "DELETE FROM pending_country_alerts WHERE user_id = ? AND country_code = ?",
            (user_id, normalize_code(country_code)),
        )

    async def has_pending_country_alert(self, user_id: int, country_code: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM pending_country_alerts WHERE user_id = ? AND country_code = ?",
                (user_id, normalize_code(country_code)),
            )
            row = await cursor.fetchone()
        return bool(row)

    async def _execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(query, params)
            await db.commit()

    @staticmethod
    def _user_from_row(row: aiosqlite.Row) -> User:
        return User(
            user_id=row["user_id"],
            api_key=row["api_key"],
            your_id=row["your_id"],
            monitoring_enabled=bool(row["monitoring_enabled"]),
            max_price=row["max_price"],
            interval_seconds=row["interval_seconds"],
            alert_repeat_count=max(1, int(row["alert_repeat_count"] or 1)),
            country_alert_enabled=bool(row["country_alert_enabled"]),
            autobuy_alert_enabled=bool(row["autobuy_alert_enabled"]),
            autobuy_alert_repeat_count=max(1, int(row["autobuy_alert_repeat_count"] or 1)),
            quiet_hours_enabled=bool(row["quiet_hours_enabled"]),
            quiet_start_hour=int(row["quiet_start_hour"] or 0),
            quiet_end_hour=int(row["quiet_end_hour"] or 8),
            escalation_enabled=bool(row["escalation_enabled"]),
            escalation_interval_seconds=max(15, int(row["escalation_interval_seconds"] or 45)),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def ensure_autobuy_settings(self, user_id: int) -> AutobuySettings:
        await self.ensure_user(user_id)
        now = utc_now()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO autobuy_settings(user_id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (user_id, now, now),
            )
            await db.commit()
        settings = await self.get_autobuy_settings(user_id)
        assert settings is not None
        return settings

    async def get_autobuy_settings(self, user_id: int) -> AutobuySettings | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM autobuy_settings WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return self._autobuy_from_row(row) if row else None

    async def get_autobuy_map(self, user_ids: list[int]) -> dict[int, AutobuySettings]:
        if not user_ids:
            return {}
        placeholders = ",".join("?" for _ in user_ids)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                f"SELECT * FROM autobuy_settings WHERE user_id IN ({placeholders})",
                tuple(user_ids),
            )
        return {row["user_id"]: self._autobuy_from_row(row) for row in rows}

    async def update_autobuy_setting(self, user_id: int, field: str, value: Any) -> None:
        allowed = {
            "enabled",
            "min_price",
            "max_price",
            "stop_balance",
            "max_purchases_total",
            "max_purchases_day",
            "auto_get_code",
            "code_check_seconds",
        }
        if field not in allowed:
            raise ValueError(f"Unknown autobuy field: {field}")
        await self.ensure_autobuy_settings(user_id)
        await self._execute(
            f"UPDATE autobuy_settings SET {field} = ?, updated_at = ? WHERE user_id = ?",
            (value, utc_now(), user_id),
        )
        await self.add_log(user_id, f"autobuy_{field}:{value}")

    async def reset_autobuy_limits(self, user_id: int) -> None:
        await self.ensure_autobuy_settings(user_id)
        await self._execute(
            """
            UPDATE autobuy_settings
            SET min_price = NULL, max_price = NULL, stop_balance = NULL,
                max_purchases_total = 1, max_purchases_day = 3,
                auto_get_code = 1, code_check_seconds = 20, updated_at = ?
            WHERE user_id = ?
            """,
            (utc_now(), user_id),
        )
        await self.add_log(user_id, "autobuy_limits_reset")

    async def create_purchase(
        self,
        user_id: int,
        country_code: str,
        country_name: str,
        number: str,
        price: float | None,
        new_balance: float | None,
    ) -> int:
        await self.ensure_user(user_id)
        now = utc_now()
        # Normalize country code
        normalized_code = normalize_code(country_code)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO purchases(
                    user_id, country_code, country_name, number, price,
                    status, new_balance, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending_code', ?, ?, ?)
                """,
                (user_id, normalized_code, country_name, number, price, new_balance, now, now),
            )
            await db.commit()
            purchase_id = cursor.lastrowid
        await self.add_log(user_id, f"autobuy_purchase:{normalized_code}:{number}")
        return int(purchase_id)

    async def complete_purchase_code(self, purchase_id: int, code: str | None, password: str | None) -> None:
        await self._execute(
            """
            UPDATE purchases
            SET status = ?, login_code = ?, password = ?, updated_at = ?
            WHERE id = ?
            """,
            ("code_received" if code else "pending_code", code, password, utc_now(), purchase_id),
        )

    async def get_recent_purchases(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT * FROM purchases
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        return [dict(row) for row in rows]

    async def get_pending_code_purchases(self, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT p.*, a.auto_get_code, a.code_check_seconds, u.api_key, u.your_id
                FROM purchases p
                JOIN autobuy_settings a ON a.user_id = p.user_id
                JOIN users u ON u.user_id = p.user_id
                WHERE p.status = 'pending_code'
                  AND a.auto_get_code = 1
                  AND u.api_key IS NOT NULL
                  AND u.your_id IS NOT NULL
                ORDER BY p.id ASC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(row) for row in rows]

    async def count_purchases(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return int(row[0])

    async def count_purchases_today(self, user_id: int) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM purchases WHERE user_id = ? AND substr(created_at, 1, 10) = ?",
                (user_id, today),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def has_recent_purchase_for_country(self, user_id: int, country_code: str, minutes: int = 10) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT created_at FROM purchases
                WHERE user_id = ? AND country_code = ?
                ORDER BY id DESC LIMIT 1
                """,
                (user_id, normalize_code(country_code)),
            )
            row = await cursor.fetchone()
        if not row:
            return False
        try:
            created = datetime.fromisoformat(row[0])
        except ValueError:
            return False
        return (datetime.now(timezone.utc) - created).total_seconds() < minutes * 60

    @staticmethod
    def _autobuy_from_row(row: aiosqlite.Row) -> AutobuySettings:
        return AutobuySettings(
            user_id=row["user_id"],
            enabled=bool(row["enabled"]),
            min_price=row["min_price"],
            max_price=row["max_price"],
            stop_balance=row["stop_balance"],
            max_purchases_total=row["max_purchases_total"],
            max_purchases_day=row["max_purchases_day"],
            auto_get_code=bool(row["auto_get_code"]),
            code_check_seconds=row["code_check_seconds"],
        )
