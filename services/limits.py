import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 5000

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_usage (
    user_id INTEGER NOT NULL,
    day     TEXT    NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
"""


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def init_limits_db() -> None:
    db_path = Path(config["STATS_DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.executescript(_CREATE_TABLE_SQL)
        con.commit()
    finally:
        con.close()


def _record_recognition_sync(user_id: int) -> None:
    db_path = config["STATS_DB_PATH"]
    day = _today_utc()
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.execute(
            """
            INSERT INTO daily_usage(user_id, day, count) VALUES(?, ?, 1)
            ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1
            """,
            (user_id, day),
        )
        con.commit()
    finally:
        con.close()


async def record_recognition(user_id: int) -> None:
    await asyncio.to_thread(_record_recognition_sync, user_id)


def _usage_today_sync(user_id: int) -> int:
    db_path = config["STATS_DB_PATH"]
    day = _today_utc()
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            "SELECT count FROM daily_usage WHERE user_id = ? AND day = ?",
            (user_id, day),
        ).fetchone()
        return row[0] if row else 0
    finally:
        con.close()


async def usage_today(user_id: int) -> int:
    return await asyncio.to_thread(_usage_today_sync, user_id)


def _total_today_sync() -> int:
    db_path = config["STATS_DB_PATH"]
    day = _today_utc()
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            "SELECT COALESCE(SUM(count), 0) FROM daily_usage WHERE day = ?",
            (day,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        con.close()


async def total_today() -> int:
    return await asyncio.to_thread(_total_today_sync)


def effective_daily_limit(base_limit: int, referral_count: int) -> int:
    if referral_count <= 0:
        return base_limit
    bonus = min(referral_count * config["REFERRAL_BONUS_PER"], config["REFERRAL_BONUS_CAP"])
    return base_limit + bonus
