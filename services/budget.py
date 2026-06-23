import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 5000


def init_cf_usage_db() -> None:
    db_path = Path(config["STATS_DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS cf_usage (
                date  TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        con.commit()
    finally:
        con.close()


def _get_count_sync(date_str: str) -> int:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            "SELECT count FROM cf_usage WHERE date = ?", (date_str,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        con.close()


def _consume_sync(date_str: str) -> None:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.execute(
            """
            INSERT INTO cf_usage (date, count) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET count = count + 1
            """,
            (date_str,),
        )
        con.commit()
    finally:
        con.close()


async def cf_budget_allow() -> bool:
    date_str = datetime.now(timezone.utc).date().isoformat()
    budget: int = config["CF_DAILY_BUDGET"]
    try:
        count = await asyncio.to_thread(_get_count_sync, date_str)
        return count < budget
    except Exception:
        logger.warning("cf_budget_allow: failed to read cf_usage, allowing CF call (fail-open)")
        return True


async def cf_budget_consume() -> None:
    date_str = datetime.now(timezone.utc).date().isoformat()
    try:
        await asyncio.to_thread(_consume_sync, date_str)
    except Exception:
        logger.warning("cf_budget_consume: failed to increment cf_usage counter")
