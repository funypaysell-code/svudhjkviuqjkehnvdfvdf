import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

_db_path: Optional[Path] = None
_db_instance: Optional["Database"] = None


async def get_db() -> "Database":
    """Return the global Database instance (not the raw connection)."""
    if _db_instance is None:
        raise RuntimeError("Database is not initialized. Call Database.init() first.")
    return _db_instance


class Database:
    """Singleton-style async SQLite database manager."""

    def __init__(self, db_path: Path) -> None:
        global _db_path
        _db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """Open connection and create schema."""
        global _db_instance
        self._conn = await aiosqlite.connect(_db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        _db_instance = self          # ← ключевая строка
        await self._create_schema()
        logger.info("Database initialized at %s", _db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed.")

    async def _create_schema(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                last_name   TEXT,
                is_allowed  INTEGER NOT NULL DEFAULT 0,
                is_banned   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen   TEXT
            );

            CREATE TABLE IF NOT EXISTS monitored_accounts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                target_username TEXT NOT NULL,
                target_id       INTEGER,
                display_name    TEXT,
                bio             TEXT,
                photo_hash      TEXT,
                is_active       INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                last_checked    TEXT,
                UNIQUE(owner_id, target_username)
            );

            CREATE TABLE IF NOT EXISTS change_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  INTEGER NOT NULL REFERENCES monitored_accounts(id) ON DELETE CASCADE,
                field       TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                changed_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_monitored_owner ON monitored_accounts(owner_id);
            CREATE INDEX IF NOT EXISTS idx_monitored_active ON monitored_accounts(is_active);
        """)
        await self._conn.commit()

    # ── Users ────────────────────────────────────────────────────────────────

    async def upsert_user(self, user_id, username, first_name, last_name) -> None:
        await self._conn.execute(
            """
            INSERT INTO users (id, username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                last_seen  = excluded.last_seen
            """,
            (user_id, username, first_name, last_name),
        )
        await self._conn.commit()

    async def get_user(self, user_id: int):
        async with self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def is_allowed(self, user_id: int) -> bool:
        async with self._conn.execute(
            "SELECT is_allowed, is_banned FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            return bool(row["is_allowed"]) and not bool(row["is_banned"])

    async def set_allowed(self, user_id: int, allowed: bool) -> bool:
        async with self._conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                return False
        await self._conn.execute(
            "UPDATE users SET is_allowed = ? WHERE id = ?", (1 if allowed else 0, user_id)
        )
        await self._conn.commit()
        return True

    async def set_banned(self, user_id: int, banned: bool) -> bool:
        async with self._conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                return False
        await self._conn.execute(
            "UPDATE users SET is_banned = ? WHERE id = ?", (1 if banned else 0, user_id)
        )
        await self._conn.commit()
        return True

    async def get_all_users(self):
        async with self._conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cur:
            return await cur.fetchall()

    async def count_active_users(self) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_allowed = 1 AND is_banned = 0"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    # ── Monitored accounts ───────────────────────────────────────────────────

    async def add_monitored(self, owner_id, target_username, target_id, display_name, bio, photo_hash):
        try:
            async with self._conn.execute(
                """
                INSERT INTO monitored_accounts
                    (owner_id, target_username, target_id, display_name, bio, photo_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (owner_id, target_username.lower().lstrip("@"), target_id, display_name, bio, photo_hash),
            ) as cur:
                await self._conn.commit()
                return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None

    async def get_monitored(self, account_id: int):
        async with self._conn.execute(
            "SELECT * FROM monitored_accounts WHERE id = ?", (account_id,)
        ) as cur:
            return await cur.fetchone()

    async def get_user_monitored(self, owner_id: int):
        async with self._conn.execute(
            "SELECT * FROM monitored_accounts WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
        ) as cur:
            return await cur.fetchall()

    async def delete_monitored(self, account_id: int, owner_id: int) -> bool:
        async with self._conn.execute(
            "DELETE FROM monitored_accounts WHERE id = ? AND owner_id = ?", (account_id, owner_id)
        ) as cur:
            await self._conn.commit()
            return cur.rowcount > 0

    async def toggle_monitored(self, account_id: int, owner_id: int):
        async with self._conn.execute(
            "SELECT is_active FROM monitored_accounts WHERE id = ? AND owner_id = ?", (account_id, owner_id)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
        new_state = 0 if row["is_active"] else 1
        await self._conn.execute(
            "UPDATE monitored_accounts SET is_active = ? WHERE id = ?", (new_state, account_id)
        )
        await self._conn.commit()
        return bool(new_state)

    async def update_monitored_state(self, account_id, target_username, target_id, display_name, bio, photo_hash) -> None:
        await self._conn.execute(
            """
            UPDATE monitored_accounts
            SET target_username = ?,
                target_id       = ?,
                display_name    = ?,
                bio             = ?,
                photo_hash      = ?,
                last_checked    = datetime('now')
            WHERE id = ?
            """,
            (target_username, target_id, display_name, bio, photo_hash, account_id),
        )
        await self._conn.commit()

    async def get_all_active_monitored(self):
        async with self._conn.execute(
            """
            SELECT ma.*, u.id as uid
            FROM monitored_accounts ma
            JOIN users u ON u.id = ma.owner_id
            WHERE ma.is_active = 1 AND u.is_allowed = 1 AND u.is_banned = 0
            """
        ) as cur:
            return await cur.fetchall()

    async def count_all_monitored(self) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM monitored_accounts WHERE is_active = 1"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    async def log_change(self, account_id, field, old_value, new_value) -> None:
        await self._conn.execute(
            "INSERT INTO change_log (account_id, field, old_value, new_value) VALUES (?, ?, ?, ?)",
            (account_id, field, old_value, new_value),
        )
        await self._conn.commit()

    async def get_change_log(self, account_id: int, limit: int = 20):
        async with self._conn.execute(
            "SELECT * FROM change_log WHERE account_id = ? ORDER BY changed_at DESC LIMIT ?",
            (account_id, limit),
        ) as cur:
            return await cur.fetchall()

    async def admin_delete_monitored(self, account_id: int) -> bool:
        async with self._conn.execute(
            "DELETE FROM monitored_accounts WHERE id = ?", (account_id,)
        ) as cur:
            await self._conn.commit()
            return cur.rowcount > 0