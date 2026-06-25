"""Тесты run_broadcast (services/announce.py) с замоканным Bot."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "stats.db")


@pytest.fixture()
def setup_db(db_path):
    import services.announce as ann
    import services.stats as st

    with patch.dict(ann.config, {"STATS_DB_PATH": db_path}), \
         patch.dict(st.config, {"STATS_DB_PATH": db_path}):
        st.init_db()
        ann.init_announce_db()
        yield ann, st, db_path


def _insert_users(db_path, users: list[tuple[int, int]]) -> None:
    con = sqlite3.connect(db_path)
    try:
        for uid, optout in users:
            con.execute(
                "INSERT INTO user_stats(user_id, first_seen, last_seen, announcements_optout) "
                "VALUES(?, 'now', 'now', ?)",
                (uid, optout),
            )
        con.commit()
    finally:
        con.close()


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_active(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 0), (3, 0)])
    bot = _make_bot()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert sent == 3
    assert skipped == 0
    assert errors == 0
    assert bot.send_message.call_count == 3


@pytest.mark.asyncio
async def test_broadcast_returns_correct_counters(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 0)])
    bot = _make_bot()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert (sent, skipped, errors) == (2, 0, 0)


@pytest.mark.asyncio
async def test_broadcast_skips_forbidden(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 0), (3, 0)])

    bot = _make_bot()

    async def send_side_effect(uid, *args, **kwargs):
        if uid == 2:
            raise TelegramForbiddenError(method=MagicMock(), message="Forbidden")
        return MagicMock()

    bot.send_message.side_effect = send_side_effect

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert sent == 2
    assert skipped == 1
    assert errors == 0


@pytest.mark.asyncio
async def test_broadcast_forbidden_does_not_interrupt(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 0), (3, 0)])

    received = []

    async def send_side_effect(uid, *args, **kwargs):
        received.append(uid)
        if uid == 1:
            raise TelegramForbiddenError(method=MagicMock(), message="Forbidden")
        return MagicMock()

    bot = _make_bot()
    bot.send_message.side_effect = send_side_effect

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert 2 in received
    assert 3 in received
    assert sent == 2
    assert skipped == 1


@pytest.mark.asyncio
async def test_broadcast_retry_after_triggers_sleep_and_retry(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0)])

    call_count = 0
    slept_values = []

    async def send_side_effect(uid, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = TelegramRetryAfter(method=MagicMock(), message="retry", retry_after=1)
            raise exc
        return MagicMock()

    async def fake_sleep(secs):
        slept_values.append(secs)

    bot = _make_bot()
    bot.send_message.side_effect = send_side_effect

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert call_count == 2
    assert 1 in slept_values
    assert sent == 1
    assert errors == 0


@pytest.mark.asyncio
async def test_broadcast_double_retry_after_exactly_two_calls(setup_db):
    """Два RetryAfter подряд → ровно 2 вызова send_message, получатель в errors."""
    ann, st, db = setup_db
    _insert_users(db, [(1, 0)])

    call_count = 0
    slept_values = []

    async def send_side_effect(uid, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        exc = TelegramRetryAfter(method=MagicMock(), message="retry", retry_after=call_count)
        raise exc

    async def fake_sleep(secs):
        slept_values.append(secs)

    bot = _make_bot()
    bot.send_message.side_effect = send_side_effect

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert call_count == 2, f"Ожидалось ровно 2 вызова, получено {call_count}"
    assert errors == 1
    assert sent == 0
    assert 1 in slept_values
    assert 2 in slept_values


@pytest.mark.asyncio
async def test_broadcast_other_exception_counted_as_error(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 0)])

    async def send_side_effect(uid, *args, **kwargs):
        if uid == 1:
            raise RuntimeError("Unexpected")
        return MagicMock()

    bot = _make_bot()
    bot.send_message.side_effect = send_side_effect

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert errors == 1
    assert sent == 1


@pytest.mark.asyncio
async def test_broadcast_optout_excluded(setup_db):
    ann, st, db = setup_db
    _insert_users(db, [(1, 0), (2, 1), (3, 0)])
    bot = _make_bot()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert sent == 2
    called_ids = {call.args[0] for call in bot.send_message.call_args_list}
    assert 2 not in called_ids


@pytest.mark.asyncio
async def test_broadcast_empty_recipients(setup_db):
    ann, st, db = setup_db
    bot = _make_bot()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("services.announce.ANNOUNCE_SEND_INTERVAL", 0):
        sent, skipped, errors = await ann.run_broadcast(bot, "Тест")

    assert (sent, skipped, errors) == (0, 0, 0)
    bot.send_message.assert_not_called()
