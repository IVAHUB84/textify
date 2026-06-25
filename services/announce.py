import asyncio
import logging
import sqlite3
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from services import stats

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 5000
ANNOUNCE_SEND_INTERVAL = 0.05

_CREATE_ANNOUNCE_STATE_SQL = """
CREATE TABLE IF NOT EXISTS announce_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def build_optout_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔕 Не показывать анонсы", callback_data="ann:off")]
        ]
    )


def init_announce_db() -> None:
    db_path = Path(config["STATS_DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.executescript(_CREATE_ANNOUNCE_STATE_SQL)
        con.commit()
    finally:
        con.close()


def _get_last_announced_version_sync() -> str | None:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            "SELECT value FROM announce_state WHERE key = 'last_announced_version'"
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


async def get_last_announced_version() -> str | None:
    return await asyncio.to_thread(_get_last_announced_version_sync)


def _set_last_announced_version_sync(version: str) -> None:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.execute(
            "INSERT INTO announce_state(key, value) VALUES('last_announced_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (version,),
        )
        con.commit()
    finally:
        con.close()


async def set_last_announced_version(version: str) -> None:
    await asyncio.to_thread(_set_last_announced_version_sync, version)


async def run_broadcast(bot: Bot, text: str) -> tuple[int, int, int]:
    sent = 0
    skipped = 0
    errors = 0

    recipients = await stats.all_active_recipient_ids()
    markup = build_optout_keyboard()

    for uid in recipients:
        for attempt in range(2):
            try:
                await bot.send_message(uid, text, reply_markup=markup)
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                if attempt == 1:
                    errors += 1
            except TelegramForbiddenError:
                skipped += 1
                break
            except Exception:
                logger.warning("Ошибка рассылки пользователю %d", uid, exc_info=True)
                errors += 1
                break

        await asyncio.sleep(ANNOUNCE_SEND_INTERVAL)

    return sent, skipped, errors
