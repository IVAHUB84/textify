"""Тесты announce_state (services/announce.py) и opt-out (services/stats.py)."""
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "stats.db")


@pytest.fixture()
def announce(db_path):
    import services.announce as ann
    import services.stats as st

    with patch.dict(ann.config, {"STATS_DB_PATH": db_path}), \
         patch.dict(st.config, {"STATS_DB_PATH": db_path}):
        st.init_db()
        ann.init_announce_db()
        yield ann, st, db_path


@pytest.mark.asyncio
async def test_get_last_announced_version_none_initially(announce):
    ann, st, db = announce
    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        result = await ann.get_last_announced_version()
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_last_announced_version(announce):
    ann, st, db = announce
    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        await ann.set_last_announced_version("1.10.0")
        result = await ann.get_last_announced_version()
    assert result == "1.10.0"


@pytest.mark.asyncio
async def test_set_last_announced_version_upsert(announce):
    ann, st, db = announce
    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        await ann.set_last_announced_version("1.9.0")
        await ann.set_last_announced_version("1.10.0")
        result = await ann.get_last_announced_version()
    assert result == "1.10.0"


@pytest.mark.asyncio
async def test_set_last_announced_version_survives_reopen(announce):
    ann, st, db = announce
    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        await ann.set_last_announced_version("1.10.0")

    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        result = await ann.get_last_announced_version()
    assert result == "1.10.0"


@pytest.mark.asyncio
async def test_all_active_recipient_ids_empty(announce):
    ann, st, db = announce
    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        result = await st.all_active_recipient_ids()
    assert result == []


@pytest.mark.asyncio
async def test_all_active_recipient_ids_includes_non_optout(announce):
    ann, st, db = announce
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen) VALUES(1, 'now', 'now')"
        )
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen) VALUES(2, 'now', 'now')"
        )
        con.commit()
    finally:
        con.close()

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        result = await st.all_active_recipient_ids()
    assert set(result) == {1, 2}


@pytest.mark.asyncio
async def test_all_active_recipient_ids_excludes_optout(announce):
    ann, st, db = announce
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen, announcements_optout) "
            "VALUES(1, 'now', 'now', 0)"
        )
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen, announcements_optout) "
            "VALUES(2, 'now', 'now', 1)"
        )
        con.commit()
    finally:
        con.close()

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        result = await st.all_active_recipient_ids()
    assert result == [1]


@pytest.mark.asyncio
async def test_set_announcements_optout_and_check(announce):
    ann, st, db = announce
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen) VALUES(10, 'now', 'now')"
        )
        con.commit()
    finally:
        con.close()

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        assert not await st.is_announcements_optout(10)
        await st.set_announcements_optout(10, True)
        assert await st.is_announcements_optout(10)
        await st.set_announcements_optout(10, False)
        assert not await st.is_announcements_optout(10)


@pytest.mark.asyncio
async def test_is_announcements_optout_unknown_user(announce):
    ann, st, db = announce
    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        result = await st.is_announcements_optout(9999)
    assert result is False


def test_migration_adds_column_to_old_schema(tmp_path):
    """Миграция колонки announcements_optout на БД без неё не теряет данные."""
    import services.stats as st

    db = str(tmp_path / "old_stats.db")
    con = sqlite3.connect(db)
    try:
        con.execute(
            """
            CREATE TABLE user_stats (
                user_id       INTEGER PRIMARY KEY,
                first_seen    TEXT NOT NULL,
                last_seen     TEXT NOT NULL,
                photo_count   INTEGER NOT NULL DEFAULT 0,
                audio_count   INTEGER NOT NULL DEFAULT 0,
                text_count    INTEGER NOT NULL DEFAULT 0,
                command_count INTEGER NOT NULL DEFAULT 0,
                other_count   INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen, audio_count) "
            "VALUES(42, 'now', 'now', 5)"
        )
        con.commit()
    finally:
        con.close()

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        st.init_db()

    con = sqlite3.connect(db)
    try:
        cols = {row[1] for row in con.execute("PRAGMA table_info(user_stats)").fetchall()}
        assert "announcements_optout" in cols
        row = con.execute(
            "SELECT audio_count, announcements_optout FROM user_stats WHERE user_id=42"
        ).fetchone()
    finally:
        con.close()

    assert row is not None
    assert row[0] == 5
    assert row[1] == 0


def test_migration_idempotent(tmp_path):
    """Повторный вызов init_db не ломает схему."""
    import services.stats as st

    db = str(tmp_path / "stats.db")
    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        st.init_db()
        st.init_db()

    con = sqlite3.connect(db)
    try:
        cols = {row[1] for row in con.execute("PRAGMA table_info(user_stats)").fetchall()}
    finally:
        con.close()
    assert "announcements_optout" in cols
