import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from config import config

_BUSY_TIMEOUT_MS = 5000

_COLUMN_MAP = {
    "photo": "photo_count",
    "audio": "audio_count",
    "text": "text_count",
    "command": "command_count",
    "other": "other_count",
}

class StatsResult(TypedDict):
    unique_users: int
    total_messages: int
    photo: int
    audio: int
    text: int
    command: int
    other: int
    first_seen: str | None
    last_seen: str | None


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_stats (
    user_id       INTEGER PRIMARY KEY,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    photo_count   INTEGER NOT NULL DEFAULT 0,
    audio_count   INTEGER NOT NULL DEFAULT 0,
    text_count    INTEGER NOT NULL DEFAULT 0,
    command_count INTEGER NOT NULL DEFAULT 0,
    other_count   INTEGER NOT NULL DEFAULT 0
);
"""


def init_db() -> None:
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


def _record_message_sync(user_id: int, msg_type: str) -> None:
    column = _COLUMN_MAP.get(msg_type, "other_count")
    now = datetime.now(timezone.utc).isoformat()
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        con.execute(
            f"""
            INSERT INTO user_stats (user_id, first_seen, last_seen, {column})
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                {column} = {column} + 1
            """,
            (user_id, now, now),
        )
        con.commit()
    finally:
        con.close()


async def record_message(user_id: int, msg_type: str) -> None:
    await asyncio.to_thread(_record_message_sync, user_id, msg_type)


def _get_stats_sync() -> StatsResult:
    db_path = config["STATS_DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        row = con.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(photo_count), 0),
                COALESCE(SUM(audio_count), 0),
                COALESCE(SUM(text_count), 0),
                COALESCE(SUM(command_count), 0),
                COALESCE(SUM(other_count), 0),
                MIN(first_seen),
                MAX(last_seen)
            FROM user_stats
            """
        ).fetchone()
    finally:
        con.close()

    unique_users, photo, audio, text, command, other, first_seen, last_seen = row
    total = photo + audio + text + command + other
    return StatsResult(
        unique_users=unique_users,
        total_messages=total,
        photo=photo,
        audio=audio,
        text=text,
        command=command,
        other=other,
        first_seen=first_seen,
        last_seen=last_seen,
    )


async def get_stats() -> StatsResult:
    return await asyncio.to_thread(_get_stats_sync)
