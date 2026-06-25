"""Тесты gate/идемпотентность/отписка (handlers/announce.py, bot.py логика детекта)."""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


ADMIN_ID = 777


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


# ---------------------------------------------------------------------------
# Детект ожидающего анонса (логика из bot._check_pending_announcement)
# ---------------------------------------------------------------------------

async def _run_check(bot, db_path, version, last_version, announcements_dict, enabled=True):
    """Выполняет логику _check_pending_announcement изолированно."""
    import services.announce as ann
    from version import parse_version

    with patch.dict(ann.config, {"STATS_DB_PATH": db_path}):
        if last_version is not None:
            await ann.set_last_announced_version(last_version)

    fake_config = {
        "ANNOUNCEMENTS_ENABLED": enabled,
        "ADMIN_USER_ID": ADMIN_ID,
        "STATS_DB_PATH": db_path,
    }

    with patch.dict(ann.config, {"STATS_DB_PATH": db_path}), \
         patch("bot.config", fake_config), \
         patch("bot.__version__", version), \
         patch("bot.ANNOUNCEMENTS", announcements_dict), \
         patch("bot.parse_version", parse_version), \
         patch("bot.get_last_announced_version", ann.get_last_announced_version), \
         patch("bot.set_last_announced_version", ann.set_last_announced_version), \
         patch("bot.build_admin_preview_keyboard", return_value=MagicMock()):
        import bot as bot_module
        await bot_module._check_pending_announcement(bot)


@pytest.mark.asyncio
async def test_check_sends_preview_when_newer_and_has_text(setup_db):
    ann, st, db = setup_db
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _run_check(bot, db, "1.10.0", "1.9.0", {"1.10.0": "Что нового"})

    bot.send_message.assert_awaited_once()
    args = bot.send_message.await_args
    assert ADMIN_ID == args[0][0]
    assert "Что нового" in args[0][1]


@pytest.mark.asyncio
async def test_check_no_preview_when_no_text(setup_db):
    ann, st, db = setup_db
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        await _run_check(bot, db, "1.10.0", "1.9.0", {})

    bot.send_message.assert_not_awaited()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        last = await ann.get_last_announced_version()
    assert last == "1.10.0"


@pytest.mark.asyncio
async def test_check_no_preview_when_not_newer(setup_db):
    ann, st, db = setup_db
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _run_check(bot, db, "1.10.0", "1.10.0", {"1.10.0": "Что нового"})

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_no_preview_when_disabled(setup_db):
    ann, st, db = setup_db
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _run_check(bot, db, "1.10.0", "1.9.0", {"1.10.0": "Что нового"}, enabled=False)

    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# ann:send
# ---------------------------------------------------------------------------

def _make_callback(user_id: int, data: str) -> MagicMock:
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_ann_send_marks_version_before_broadcast(setup_db):
    ann, st, db = setup_db

    marked_before_broadcast = {}

    async def fake_broadcast(bot, text):
        with patch.dict(ann.config, {"STATS_DB_PATH": db}):
            last = await ann.get_last_announced_version()
        marked_before_broadcast["last"] = last
        return (0, 0, 0)

    callback = _make_callback(ADMIN_ID, "ann:send")
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.config", {"ADMIN_USER_ID": ADMIN_ID, "STATS_DB_PATH": db}), \
         patch("handlers.announce.__version__", "1.10.0"), \
         patch("handlers.announce.ANNOUNCEMENTS", {"1.10.0": "Что нового"}), \
         patch("handlers.announce.set_last_announced_version", ann.set_last_announced_version), \
         patch("handlers.announce.run_broadcast", fake_broadcast):
        from handlers.announce import handle_ann_send
        await handle_ann_send(callback, bot)

        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})

    assert marked_before_broadcast.get("last") == "1.10.0"


@pytest.mark.asyncio
async def test_ann_send_non_admin_rejected(setup_db):
    ann, st, db = setup_db

    callback = _make_callback(999, "ann:send")
    bot = MagicMock()
    broadcast_called = []

    async def fake_broadcast(b, text):
        broadcast_called.append(True)
        return (0, 0, 0)

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.config", {"ADMIN_USER_ID": ADMIN_ID}), \
         patch("handlers.announce.run_broadcast", fake_broadcast):
        from handlers.announce import handle_ann_send
        await handle_ann_send(callback, bot)

    assert not broadcast_called
    callback.answer.assert_awaited_with("Недоступно.")


@pytest.mark.asyncio
async def test_ann_skip_marks_version_without_broadcast(setup_db):
    ann, st, db = setup_db

    callback = _make_callback(ADMIN_ID, "ann:skip")
    broadcast_called = []

    async def fake_broadcast(b, text):
        broadcast_called.append(True)
        return (0, 0, 0)

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.config", {"ADMIN_USER_ID": ADMIN_ID, "STATS_DB_PATH": db}), \
         patch("handlers.announce.__version__", "1.10.0"), \
         patch("handlers.announce.set_last_announced_version", ann.set_last_announced_version), \
         patch("handlers.announce.run_broadcast", fake_broadcast):
        from handlers.announce import handle_ann_skip
        await handle_ann_skip(callback)

    assert not broadcast_called
    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        last = await ann.get_last_announced_version()
    assert last == "1.10.0"


@pytest.mark.asyncio
async def test_ann_skip_non_admin_rejected(setup_db):
    ann, st, db = setup_db

    callback = _make_callback(888, "ann:skip")

    with patch.dict(ann.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.config", {"ADMIN_USER_ID": ADMIN_ID}):
        from handlers.announce import handle_ann_skip
        await handle_ann_skip(callback)

    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        last = await ann.get_last_announced_version()
    assert last is None

    callback.answer.assert_awaited_with("Недоступно.")


# ---------------------------------------------------------------------------
# ann:off / /announces_off / /announces_on
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ann_off_sets_optout(setup_db):
    ann, st, db = setup_db

    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen) VALUES(42, 'now', 'now')"
        )
        con.commit()
    finally:
        con.close()

    callback = _make_callback(42, "ann:off")

    with patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.set_announcements_optout", st.set_announcements_optout):
        from handlers.announce import handle_ann_off
        await handle_ann_off(callback)

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        assert await st.is_announcements_optout(42)


@pytest.mark.asyncio
async def test_announces_off_command_sets_optout(setup_db):
    ann, st, db = setup_db

    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen) VALUES(55, 'now', 'now')"
        )
        con.commit()
    finally:
        con.close()

    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 55
    message.answer = AsyncMock()

    with patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.set_announcements_optout", st.set_announcements_optout):
        from handlers.announce import cmd_announces_off
        await cmd_announces_off(message)

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        assert await st.is_announcements_optout(55)


@pytest.mark.asyncio
async def test_announces_on_command_clears_optout(setup_db):
    ann, st, db = setup_db

    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO user_stats(user_id, first_seen, last_seen, announcements_optout) "
            "VALUES(66, 'now', 'now', 1)"
        )
        con.commit()
    finally:
        con.close()

    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 66
    message.answer = AsyncMock()

    with patch.dict(st.config, {"STATS_DB_PATH": db}), \
         patch("handlers.announce.set_announcements_optout", st.set_announcements_optout):
        from handlers.announce import cmd_announces_on
        await cmd_announces_on(message)

    with patch.dict(st.config, {"STATS_DB_PATH": db}):
        assert not await st.is_announcements_optout(66)


# ---------------------------------------------------------------------------
# Идемпотентность — повторный анонс не предлагается
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_second_preview_after_skip(setup_db):
    ann, st, db = setup_db
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch.dict(ann.config, {"STATS_DB_PATH": db}):
        await ann.set_last_announced_version("1.10.0")

    await _run_check(bot, db, "1.10.0", None, {"1.10.0": "Что нового"})

    bot.send_message.assert_not_awaited()
