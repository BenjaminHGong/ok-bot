"""SQLite-backed storage for user banking data.

The economy cog talks to the bank exclusively through this module's
load_users()/save_users(), which present the exact same {user_id: {...}}
dict shape the JSON store used to hold. That way the rest of economy.py
keeps working unchanged while the data really lives in SQL.
"""

import asyncio
import json
import sqlite3

DB_PATH = "data/bank.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id  TEXT PRIMARY KEY,
            wallet   INTEGER NOT NULL DEFAULT 0,
            bank     INTEGER NOT NULL DEFAULT 0,
            bag      TEXT    NOT NULL DEFAULT '[]',
            meta     TEXT    NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.commit()


_ready = asyncio.Lock()
_initialized = False


async def ensure_ready():
    """Idempotent one-time setup: create the schema, under a lock."""
    global _initialized
    if _initialized:
        return
    async with _ready:
        if _initialized:
            return
        conn = _connect()
        try:
            _init_db(conn)
        finally:
            conn.close()
        _initialized = True


def load_sync():
    conn = _connect()
    try:
        _init_db(conn)
        rows = conn.execute("SELECT user_id, wallet, bank, bag, meta FROM users")
        users = {}
        for row in rows:
            user_id = row["user_id"]
            users[user_id] = {
                "wallet": row["wallet"],
                "bank": row["bank"],
                "bag": json.loads(row["bag"] or "[]"),
            }
            meta = json.loads(row["meta"] or "{}")
            users[user_id].update(meta)
        return users
    finally:
        conn.close()


def save_sync(users):
    conn = _connect()
    try:
        _init_db(conn)
        with conn:
            for user_id, data in users.items():
                bag = data.get("bag", [])
                meta = {k: v for k, v in data.items() if k not in ("wallet", "bank", "bag")}
                conn.execute(
                    """
                    INSERT INTO users (user_id, wallet, bank, bag, meta)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        wallet = excluded.wallet,
                        bank = excluded.bank,
                        bag = excluded.bag,
                        meta = excluded.meta
                    """,
                    (
                        str(user_id),
                        int(data.get("wallet", 0) or 0),
                        int(data.get("bank", 0) or 0),
                        json.dumps(bag),
                        json.dumps(meta),
                    ),
                )
        return True
    finally:
        conn.close()


def load_users():
    return load_sync()


def save_users(users):
    return save_sync(users)
