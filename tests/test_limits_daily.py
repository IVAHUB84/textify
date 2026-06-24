"""Тесты слоя учёта дневного лимита (services/limits.py)."""
import asyncio
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "stats.db")


@pytest.fixture()
def limits(db_path):
    import services.limits as lm

    with patch.dict(lm.config, {"STATS_DB_PATH": db_path}):
        lm.init_limits_db()
        yield lm, db_path


@pytest.mark.asyncio
async def test_init_creates_table(limits):
    lm, db = limits
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_usage'"
        ).fetchall()
    finally:
        con.close()
    assert rows, "Таблица daily_usage не создана"


@pytest.mark.asyncio
async def test_record_creates_row_with_count_one(limits):
    lm, db = limits
    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        await lm.record_recognition(user_id=42)
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT count FROM daily_usage WHERE user_id=42"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.asyncio
async def test_record_increments_on_repeat(limits):
    lm, db = limits
    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        await lm.record_recognition(user_id=7)
        await lm.record_recognition(user_id=7)
        await lm.record_recognition(user_id=7)
        count = await lm.usage_today(user_id=7)
    assert count == 3


@pytest.mark.asyncio
async def test_usage_today_new_user_returns_zero(limits):
    lm, db = limits
    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        count = await lm.usage_today(user_id=9999)
    assert count == 0


@pytest.mark.asyncio
async def test_usage_today_new_day_returns_zero(limits):
    lm, db = limits
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO daily_usage(user_id, day, count) VALUES(1, ?, 5)",
            ("2000-01-01",),
        )
        con.commit()
    finally:
        con.close()

    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        count = await lm.usage_today(user_id=1)
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_increments_atomic(limits):
    lm, db = limits
    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        await asyncio.gather(*[lm.record_recognition(user_id=55) for _ in range(10)])
        count = await lm.usage_today(user_id=55)
    assert count == 10


def test_today_utc_key_format():
    import services.limits as lm
    key = lm._today_utc()
    parts = key.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4
    assert len(parts[1]) == 2
    assert len(parts[2]) == 2


@pytest.mark.asyncio
async def test_total_today(limits):
    lm, db = limits
    with patch.dict(lm.config, {"STATS_DB_PATH": db}):
        await lm.record_recognition(user_id=1)
        await lm.record_recognition(user_id=2)
        await lm.record_recognition(user_id=2)
        total = await lm.total_today()
    assert total == 3
