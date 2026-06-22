import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные функции для изоляции services.stats на временной БД
# ---------------------------------------------------------------------------

def _init_schema(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS user_stats (
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
        con.commit()
    finally:
        con.close()


def _fetch_row(db_path: str, user_id: int) -> dict | None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "stats.db")
    _init_schema(path)
    return path


@pytest.fixture()
def stats_module(db_path, monkeypatch):
    """Подменяет config в services.stats, направляя запросы на временную БД."""
    import services.stats as m
    fake_config = {"BOT_TOKEN": "x", "ADMIN_USER_ID": None, "STATS_DB_PATH": db_path}
    monkeypatch.setattr(m, "config", fake_config)
    yield m


# ---------------------------------------------------------------------------
# Задача 1: services/stats.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_message_new_user(stats_module, db_path):
    """Новый user_id создаёт строку с first_seen == last_seen и счётчиком типа = 1."""
    await stats_module.record_message(111, "photo")
    row = _fetch_row(db_path, 111)
    assert row is not None
    assert row["photo_count"] == 1
    assert row["first_seen"] == row["last_seen"]
    assert row["audio_count"] == 0


@pytest.mark.parametrize("msg_type,column", [
    ("photo", "photo_count"),
    ("audio", "audio_count"),
    ("text", "text_count"),
    ("command", "command_count"),
    ("other", "other_count"),
])
@pytest.mark.asyncio
async def test_record_message_increments_correct_column(stats_module, db_path, msg_type, column):
    """Счётчик инкрементируется в правильную колонку для каждого типа."""
    await stats_module.record_message(200, msg_type)
    await stats_module.record_message(200, msg_type)
    row = _fetch_row(db_path, 200)
    assert row[column] == 2
    for other_col in ("photo_count", "audio_count", "text_count", "command_count", "other_count"):
        if other_col != column:
            assert row[other_col] == 0


@pytest.mark.asyncio
async def test_first_seen_immutable_last_seen_updated(stats_module, db_path):
    """Повторный record_message не меняет first_seen и обновляет last_seen."""
    import asyncio

    await stats_module.record_message(300, "text")
    row1 = _fetch_row(db_path, 300)

    # Небольшая задержка, чтобы timestamp точно отличался
    await asyncio.sleep(0.01)

    await stats_module.record_message(300, "text")
    row2 = _fetch_row(db_path, 300)

    assert row2["first_seen"] == row1["first_seen"], "first_seen не должен меняться"
    assert row2["last_seen"] > row1["last_seen"], "last_seen должен быть строго новее после задержки"
    assert row2["last_seen"] != row2["first_seen"], "last_seen должен отличаться от first_seen"
    assert row2["text_count"] == 2


@pytest.mark.asyncio
async def test_get_stats_empty_db(stats_module):
    """На пустой БД get_stats возвращает нули и None для дат."""
    result = await stats_module.get_stats()
    assert result["unique_users"] == 0
    assert result["total_messages"] == 0
    assert result["photo"] == 0
    assert result["audio"] == 0
    assert result["text"] == 0
    assert result["command"] == 0
    assert result["other"] == 0
    assert result["first_seen"] is None
    assert result["last_seen"] is None


@pytest.mark.asyncio
async def test_get_stats_aggregates(stats_module):
    """get_stats корректно агрегирует по нескольким пользователям."""
    await stats_module.record_message(401, "photo")
    await stats_module.record_message(401, "audio")
    await stats_module.record_message(402, "photo")
    await stats_module.record_message(402, "command")
    await stats_module.record_message(402, "command")

    result = await stats_module.get_stats()
    assert result["unique_users"] == 2
    assert result["photo"] == 2
    assert result["audio"] == 1
    assert result["command"] == 2
    assert result["text"] == 0
    assert result["other"] == 0
    assert result["total_messages"] == 5
    assert result["first_seen"] is not None
    assert result["last_seen"] is not None


# ---------------------------------------------------------------------------
# Задача 2: classify_message
# ---------------------------------------------------------------------------

def _make_message(**kwargs) -> MagicMock:
    msg = MagicMock()
    msg.text = kwargs.get("text", None)
    msg.photo = kwargs.get("photo", None)
    msg.voice = kwargs.get("voice", None)
    msg.audio = kwargs.get("audio", None)
    msg.document = kwargs.get("document", None)
    return msg


def _make_document(mime_type: str) -> MagicMock:
    doc = MagicMock()
    doc.mime_type = mime_type
    return doc


@pytest.fixture()
def classify():
    from middlewares.stats import classify_message
    return classify_message


def test_classify_command(classify):
    msg = _make_message(text="/start")
    assert classify(msg) == "command"


def test_classify_command_with_args(classify):
    msg = _make_message(text="/stats something")
    assert classify(msg) == "command"


def test_classify_photo(classify):
    msg = _make_message(photo=[MagicMock()])
    assert classify(msg) == "photo"


def test_classify_image_document(classify):
    msg = _make_message(document=_make_document("image/png"))
    assert classify(msg) == "photo"


def test_classify_image_document_jpeg(classify):
    msg = _make_message(document=_make_document("image/jpeg"))
    assert classify(msg) == "photo"


def test_classify_voice(classify):
    msg = _make_message(voice=MagicMock())
    assert classify(msg) == "audio"


def test_classify_audio(classify):
    msg = _make_message(audio=MagicMock())
    assert classify(msg) == "audio"


def test_classify_audio_document(classify):
    msg = _make_message(document=_make_document("audio/mpeg"))
    assert classify(msg) == "audio"


def test_classify_plain_text(classify):
    msg = _make_message(text="Привет, мир")
    assert classify(msg) == "text"


def test_classify_other_sticker(classify):
    msg = _make_message()
    msg.text = None
    msg.photo = None
    msg.voice = None
    msg.audio = None
    msg.document = None
    assert classify(msg) == "other"


def test_classify_other_document(classify):
    msg = _make_message(document=_make_document("application/pdf"))
    assert classify(msg) == "other"


# ---------------------------------------------------------------------------
# Задача 2: тихая деградация в StatsMiddleware
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_middleware_silent_degradation_on_error():
    """При исключении в record_message middleware не пробрасывает ошибку и вызывает handler."""
    from middlewares.stats import StatsMiddleware

    middleware = StatsMiddleware()

    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 999
    message.text = "hello"
    message.photo = None
    message.voice = None
    message.audio = None
    message.document = None

    handler_called = False

    async def fake_handler(event, data):
        nonlocal handler_called
        handler_called = True
        return "ok"

    with patch("middlewares.stats.record_message", side_effect=RuntimeError("db error")):
        result = await middleware(fake_handler, message, {})

    assert handler_called, "handler должен быть вызван даже при ошибке record_message"
    assert result == "ok"


@pytest.mark.asyncio
async def test_middleware_no_from_user_still_calls_handler():
    """Если from_user отсутствует — учёт пропускается, handler всё равно вызывается."""
    from middlewares.stats import StatsMiddleware

    middleware = StatsMiddleware()

    message = MagicMock()
    message.from_user = None

    handler_called = False

    async def fake_handler(event, data):
        nonlocal handler_called
        handler_called = True
        return "ok"

    with patch("middlewares.stats.record_message") as mock_record:
        await middleware(fake_handler, message, {})

    assert handler_called
    mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# Задача 3: авторизация /stats
# ---------------------------------------------------------------------------

@pytest.fixture()
def stats_handler():
    from handlers.commands import cmd_stats
    return cmd_stats


@pytest.mark.asyncio
async def test_stats_admin_gets_report(stats_module):
    """Администратор получает сводку статистики."""
    await stats_module.record_message(1001, "photo")
    await stats_module.record_message(1001, "audio")

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42

    fake_config = {"BOT_TOKEN": "x", "ADMIN_USER_ID": 42, "STATS_DB_PATH": stats_module.config["STATS_DB_PATH"]}

    with patch("handlers.commands.config", fake_config), \
         patch("handlers.commands.get_stats", stats_module.get_stats):
        from handlers.commands import cmd_stats
        await cmd_stats(message)

    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert "Уникальных пользователей" in reply
    assert "Всего сообщений" in reply


@pytest.mark.asyncio
async def test_stats_non_admin_gets_denied():
    """Не-администратор получает отказ."""
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 9999

    fake_config = {"BOT_TOKEN": "x", "ADMIN_USER_ID": 42, "STATS_DB_PATH": ":memory:"}

    with patch("handlers.commands.config", fake_config):
        from handlers.commands import cmd_stats
        await cmd_stats(message)

    message.answer.assert_called_once_with("Команда недоступна.")


@pytest.mark.asyncio
async def test_stats_no_admin_configured_gets_denied():
    """Если ADMIN_USER_ID не задан — /stats недоступна никому."""
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42

    fake_config = {"BOT_TOKEN": "x", "ADMIN_USER_ID": None, "STATS_DB_PATH": ":memory:"}

    with patch("handlers.commands.config", fake_config):
        from handlers.commands import cmd_stats
        await cmd_stats(message)

    message.answer.assert_called_once_with("Команда недоступна.")
