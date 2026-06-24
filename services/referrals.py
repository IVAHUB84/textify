import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 5000

REFERRAL_COUNT_TTL_SECONDS = 600
_referral_count_cache: dict[int, tuple[int, float]] = {}

_CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS referrals (
    referred_id  INTEGER PRIMARY KEY,
    referrer_id  INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
"""


def init_referrals_db() -> None:
    db_path = Path(config["STATS_DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.executescript(_CREATE_SCHEMA_SQL)
        con.commit()
    finally:
        con.close()


def _record_referral_sync(referrer_id: int, referred_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.execute(
            "INSERT OR IGNORE INTO referrals (referred_id, referrer_id, created_at) VALUES (?, ?, ?)",
            (referred_id, referrer_id, now),
        )
        con.commit()
    finally:
        con.close()


async def record_referral(referrer_id: int, referred_id: int) -> None:
    await asyncio.to_thread(_record_referral_sync, referrer_id, referred_id)
    _referral_count_cache.pop(referrer_id, None)


def _count_referrals_sync(referrer_id: int) -> int:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (referrer_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        con.close()


async def count_referrals(referrer_id: int) -> int:
    return await asyncio.to_thread(_count_referrals_sync, referrer_id)


async def cached_referral_count(user_id: int) -> int:
    now = time.monotonic()
    cached = _referral_count_cache.get(user_id)
    if cached is not None:
        count, expiry = cached
        if now < expiry:
            return count
    try:
        count = await count_referrals(user_id)
    except Exception:
        logger.warning(
            "cached_referral_count: failed to read count for user=%d", user_id, exc_info=True
        )
        _referral_count_cache.pop(user_id, None)
        return 0
    _referral_count_cache[user_id] = (count, now + REFERRAL_COUNT_TTL_SECONDS)
    return count


def _total_referrals_sync() -> int:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute("SELECT COUNT(*) FROM referrals").fetchone()
        return row[0] if row else 0
    finally:
        con.close()


async def total_referrals() -> int:
    return await asyncio.to_thread(_total_referrals_sync)


def _top_referrers_sync(limit: int) -> list[tuple[int, int]]:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        rows = con.execute(
            """
            SELECT referrer_id, COUNT(*) AS cnt
            FROM referrals
            GROUP BY referrer_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
    finally:
        con.close()


async def top_referrers(limit: int) -> list[tuple[int, int]]:
    return await asyncio.to_thread(_top_referrers_sync, limit)
