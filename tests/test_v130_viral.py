"""Тесты v1.3.0: рефералы, is_new_user, подпись attribution, /start, /stats."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Изоляция глобального состояния bot_identity между тестами
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_bot_username():
    import services.bot_identity as bi
    bi.set_bot_username("")
    yield
    bi.set_bot_username("")


@pytest.fixture(autouse=True)
def reset_referral_cache():
    import services.referrals as ref
    ref._referral_count_cache.clear()
    yield
    ref._referral_count_cache.clear()


# ---------------------------------------------------------------------------
# Вспомогательные фабрики и фикстуры
# ---------------------------------------------------------------------------


def _init_referrals_schema(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id  INTEGER PRIMARY KEY,
                referrer_id  INTEGER NOT NULL,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
            """
        )
        con.commit()
    finally:
        con.close()


def _init_stats_schema(db_path: str) -> None:
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


def _fetch_referral(db_path: str, referred_id: int) -> dict | None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM referrals WHERE referred_id = ?", (referred_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


@pytest.fixture()
def ref_db_path(tmp_path):
    path = str(tmp_path / "stats.db")
    _init_referrals_schema(path)
    return path


@pytest.fixture()
def ref_module(ref_db_path, monkeypatch):
    import services.referrals as m
    fake_config = {"STATS_DB_PATH": ref_db_path}
    monkeypatch.setattr(m, "config", fake_config)
    yield m


@pytest.fixture()
def full_db_path(tmp_path):
    path = str(tmp_path / "stats.db")
    _init_stats_schema(path)
    _init_referrals_schema(path)
    return path


@pytest.fixture()
def stats_module(full_db_path, monkeypatch):
    import services.stats as m
    fake_config = {"STATS_DB_PATH": full_db_path}
    monkeypatch.setattr(m, "config", fake_config)
    yield m


def _make_message(
    chat_type: str = "private",
    user_id: int = 1,
    text: str = "/start",
) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock()
    msg.chat.type = chat_type
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_command(args: str | None = None) -> MagicMock:
    cmd = MagicMock()
    cmd.args = args
    return cmd


# ---------------------------------------------------------------------------
# Задача 1: services/referrals.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_referral_creates_row(ref_module, ref_db_path):
    """record_referral создаёт строку (referred_id, referrer_id, created_at)."""
    await ref_module.record_referral(referrer_id=10, referred_id=20)
    row = _fetch_referral(ref_db_path, 20)
    assert row is not None
    assert row["referrer_id"] == 10
    assert row["referred_id"] == 20
    assert row["created_at"]


@pytest.mark.asyncio
async def test_record_referral_idempotent(ref_module, ref_db_path):
    """Повторный record_referral с тем же referred_id не меняет строку и не падает."""
    await ref_module.record_referral(referrer_id=10, referred_id=20)
    row_before = _fetch_referral(ref_db_path, 20)

    await ref_module.record_referral(referrer_id=99, referred_id=20)
    row_after = _fetch_referral(ref_db_path, 20)

    assert row_after["referrer_id"] == row_before["referrer_id"]
    assert row_after["created_at"] == row_before["created_at"]


@pytest.mark.asyncio
async def test_count_referrals_grows(ref_module):
    """count_referrals растёт на 1 после каждого нового приглашённого."""
    assert await ref_module.count_referrals(10) == 0
    await ref_module.record_referral(referrer_id=10, referred_id=21)
    assert await ref_module.count_referrals(10) == 1
    await ref_module.record_referral(referrer_id=10, referred_id=22)
    assert await ref_module.count_referrals(10) == 2


@pytest.mark.asyncio
async def test_count_referrals_empty(ref_module):
    """count_referrals для неизвестного referrer_id возвращает 0."""
    assert await ref_module.count_referrals(9999) == 0


@pytest.mark.asyncio
async def test_total_referrals_and_top_referrers(ref_module):
    """total_referrals и top_referrers корректны, упорядочены по убыванию count."""
    assert await ref_module.total_referrals() == 0
    assert await ref_module.top_referrers(5) == []

    await ref_module.record_referral(referrer_id=1, referred_id=101)
    await ref_module.record_referral(referrer_id=1, referred_id=102)
    await ref_module.record_referral(referrer_id=2, referred_id=103)

    assert await ref_module.total_referrals() == 3

    top = await ref_module.top_referrers(5)
    assert len(top) == 2
    assert top[0] == (1, 2)
    assert top[1] == (2, 1)


@pytest.mark.asyncio
async def test_top_referrers_limit(ref_module):
    """top_referrers уважает limit."""
    for i in range(10):
        await ref_module.record_referral(referrer_id=i + 1, referred_id=200 + i)
    top = await ref_module.top_referrers(3)
    assert len(top) == 3


# ---------------------------------------------------------------------------
# Задача 2: is_new_user через record_message и StatsMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_message_returns_true_first_time(stats_module):
    """record_message возвращает True на первое обращение пользователя."""
    result = await stats_module.record_message(501, "command")
    assert result is True


@pytest.mark.asyncio
async def test_record_message_returns_false_second_time(stats_module):
    """record_message возвращает False на повторное обращение."""
    await stats_module.record_message(502, "command")
    result = await stats_module.record_message(502, "command")
    assert result is False


def _make_aiogram_message(user_id: int = 601) -> MagicMock:
    """Создаёт мок, проходящий isinstance(event, Message)."""
    from aiogram.types import Message as AiogramMessage
    message = MagicMock(spec=AiogramMessage)
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.text = "/start"
    message.photo = None
    message.voice = None
    message.audio = None
    message.document = None
    return message


@pytest.mark.asyncio
async def test_middleware_sets_is_new_user_true():
    """StatsMiddleware кладёт is_new_user=True для нового пользователя."""
    from middlewares.stats import StatsMiddleware

    middleware = StatsMiddleware()
    message = _make_aiogram_message(601)

    captured_data: dict = {}

    async def fake_handler(event, data):
        captured_data.update(data)
        return "ok"

    with patch("middlewares.stats.record_message", AsyncMock(return_value=True)):
        await middleware(fake_handler, message, {})

    assert captured_data.get("is_new_user") is True


@pytest.mark.asyncio
async def test_middleware_sets_is_new_user_false_on_repeat():
    """StatsMiddleware кладёт is_new_user=False для повторного пользователя."""
    from middlewares.stats import StatsMiddleware

    middleware = StatsMiddleware()
    message = _make_aiogram_message(602)

    captured_data: dict = {}

    async def fake_handler(event, data):
        captured_data.update(data)
        return "ok"

    with patch("middlewares.stats.record_message", AsyncMock(return_value=False)):
        await middleware(fake_handler, message, {})

    assert captured_data.get("is_new_user") is False


@pytest.mark.asyncio
async def test_middleware_sets_is_new_user_false_on_exception():
    """При исключении в record_message middleware кладёт is_new_user=False и не падает."""
    from middlewares.stats import StatsMiddleware

    middleware = StatsMiddleware()
    message = _make_aiogram_message(603)

    captured_data: dict = {}
    handler_called = False

    async def fake_handler(event, data):
        nonlocal handler_called
        handler_called = True
        captured_data.update(data)
        return "ok"

    with patch("middlewares.stats.record_message", side_effect=RuntimeError("db error")):
        result = await middleware(fake_handler, message, {})

    assert handler_called
    assert result == "ok"
    assert captured_data.get("is_new_user") is False


# ---------------------------------------------------------------------------
# Задача 3: /start реф-логика (комбинаторика)
# ---------------------------------------------------------------------------


@pytest.fixture()
def commands_module(ref_db_path, monkeypatch):
    import services.referrals as ref_m
    monkeypatch.setattr(ref_m, "config", {"STATS_DB_PATH": ref_db_path})
    import handlers.commands as cmd_m
    monkeypatch.setattr(cmd_m, "record_referral", ref_m.record_referral)
    monkeypatch.setattr(cmd_m, "cached_referral_count", ref_m.cached_referral_count)
    return cmd_m, ref_m, ref_db_path


@pytest.mark.asyncio
async def test_start_new_private_valid_ref_not_self_records(commands_module):
    """new+private+valid ref+not-self → реферал фиксируется."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=200)
    command = _make_command(args="ref_100")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 200)
    assert row is not None
    assert row["referrer_id"] == 100


@pytest.mark.asyncio
async def test_start_not_new_does_not_record(commands_module):
    """is_new_user=False → реферал не фиксируется."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=201)
    command = _make_command(args="ref_100")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=False)

    row = _fetch_referral(ref_db_path, 201)
    assert row is None


@pytest.mark.asyncio
async def test_start_group_chat_does_not_record(commands_module):
    """/start в группе → реферал не фиксируется, ответ = START_TEXT без кнопки."""
    from handlers.commands import START_TEXT
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="group", user_id=202)
    command = _make_command(args="ref_100")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 202)
    assert row is None
    message.answer.assert_called_once()
    assert message.answer.call_args[0][0] == START_TEXT
    assert message.answer.call_args.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_start_self_referral_not_recorded(commands_module):
    """referrer_id == user_id → самоприглашение не фиксируется."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=300)
    command = _make_command(args="ref_300")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 300)
    assert row is None


@pytest.mark.asyncio
async def test_start_invalid_ref_not_recorded(commands_module):
    """Невалидный ref (ref_abc) → реферал не фиксируется."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=203)
    command = _make_command(args="ref_abc")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 203)
    assert row is None


@pytest.mark.asyncio
async def test_start_no_ref_param_not_recorded(commands_module):
    """/start без deep-link → реферал не создаётся."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=204)
    command = _make_command(args=None)

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 204)
    assert row is None


@pytest.mark.asyncio
async def test_start_no_deep_link_shows_link_and_counter(commands_module):
    """/start без deep-link: ответ содержит реф-ссылку и счётчик."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=205)
    command = _make_command(args=None)

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=False)

    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert "ref_205" in reply
    assert "Приглашено: 0" in reply


@pytest.mark.asyncio
async def test_start_reply_contains_ref_link_and_counter(commands_module):
    """Ответ /start содержит ?start=ref_<user_id> с замоканным username и счётчик."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=206)
    command = _make_command(args=None)

    with patch("handlers.commands.get_bot_username", return_value="mytestbot"):
        await cmd_m.cmd_start(message, command, is_new_user=False)

    reply = message.answer.call_args[0][0]
    assert "?start=ref_206" in reply
    assert "mytestbot" in reply
    assert "Приглашено:" in reply


@pytest.mark.asyncio
async def test_start_has_share_button(commands_module):
    """Ответ /start содержит InlineKeyboardMarkup с кнопкой «Поделиться ботом» и t.me/share/url."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=207)
    command = _make_command(args=None)

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=False)

    kwargs = message.answer.call_args.kwargs
    markup = kwargs.get("reply_markup")
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any("Поделиться ботом" in btn.text for btn in buttons)
    assert any("t.me/share/url" in btn.url for btn in buttons)
    assert any("ref_207" in btn.url for btn in buttons)


@pytest.mark.asyncio
async def test_start_db_error_on_count_does_not_crash(commands_module):
    """/start при сбое cached_referral_count деградирует до 0 и не падает."""
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="private", user_id=208)
    command = _make_command(args=None)

    async def _fail(*a, **kw):
        raise RuntimeError("db down")

    with patch("handlers.commands.get_bot_username", return_value="testbot"), \
         patch("handlers.commands.cached_referral_count", _fail):
        await cmd_m.cmd_start(message, command, is_new_user=False)

    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert "Приглашено: 0" in reply


# ---------------------------------------------------------------------------
# Задача 4: подпись attribution в send_result
# ---------------------------------------------------------------------------


def _make_reply_message() -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_attribution_short_text_has_signature():
    """Короткий текст + ATTRIBUTION_FOOTER=True + непустой username → подпись присутствует."""
    from services.reply import send_result

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"):
        await send_result(message, "Короткий текст")

    reply = message.answer.call_args[0][0]
    assert "— @mybot" in reply


@pytest.mark.asyncio
async def test_attribution_off_no_signature():
    """ATTRIBUTION_FOOTER=False → подпись не добавляется."""
    from services.reply import send_result

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": False}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"):
        await send_result(message, "Короткий текст")

    reply = message.answer.call_args[0][0]
    assert "— @mybot" not in reply


@pytest.mark.asyncio
async def test_attribution_empty_username_no_signature():
    """Пустой username → подпись не добавляется."""
    from services.reply import send_result

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value=""):
        await send_result(message, "Короткий текст")

    reply = message.answer.call_args[0][0]
    assert "— @" not in reply


@pytest.mark.asyncio
async def test_attribution_does_not_exceed_limit():
    """Текст у границы: len(text)+len(signature)>MAX → подпись НЕ добавляется, одно сообщение."""
    from services.reply import MAX_MESSAGE_LEN, send_result

    signature = "\n\n— @mybot"
    # Текст занимает ровно MAX_MESSAGE_LEN - len(signature) + 1 → подпись не влезает
    text = "а" * (MAX_MESSAGE_LEN - len(signature) + 1)
    assert len(text) <= MAX_MESSAGE_LEN

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"):
        await send_result(message, text)

    # Должно быть одно сообщение, без подписи
    message.answer.assert_awaited_once()
    reply = message.answer.call_args[0][0]
    assert "— @mybot" not in reply
    assert len(reply) <= MAX_MESSAGE_LEN


@pytest.mark.asyncio
async def test_attribution_fits_exactly():
    """Текст: len(text)+len(signature)==MAX → подпись добавляется."""
    from services.reply import MAX_MESSAGE_LEN, send_result

    signature = "\n\n— @mybot"
    text = "а" * (MAX_MESSAGE_LEN - len(signature))
    assert len(text) + len(signature) == MAX_MESSAGE_LEN

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"):
        await send_result(message, text)

    reply = message.answer.call_args[0][0]
    assert "— @mybot" in reply
    assert len(reply) == MAX_MESSAGE_LEN


@pytest.mark.asyncio
async def test_attribution_series_no_signature():
    """Серия (текст > MAX_MESSAGE_LEN) → подпись не добавляется."""
    from services.reply import MAX_MESSAGE_LEN, send_result

    paragraph = "Слово предложение текст здесь.\n\n"
    text = paragraph * 150
    assert len(text) > MAX_MESSAGE_LEN

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"), \
         patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text)

    for call in message.answer.await_args_list:
        assert "— @mybot" not in call[0][0]


@pytest.mark.asyncio
async def test_attribution_file_no_signature():
    """Файл (>MAX_PARTS частей) → подпись не добавляется."""
    from services.reply import send_result

    paragraph = "Длинный абзац текста для теста разбивки.\n\n"
    text = paragraph * 1000

    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"), \
         patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text)

    message.answer_document.assert_awaited_once()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_attribution_does_not_break_reply_markup():
    """Подпись не ломает reply_markup (кнопки ADR-009) на коротком сообщении."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from services.reply import send_result

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Кратко", callback_data="act:sum")]]
    )
    message = _make_reply_message()
    fake_config = {"ATTRIBUTION_FOOTER": True}

    with patch("services.reply.config", fake_config), \
         patch("services.reply.get_bot_username", return_value="mybot"):
        await send_result(message, "Короткий текст", reply_markup=markup)

    kwargs = message.answer.call_args.kwargs
    assert kwargs.get("reply_markup") is markup
    reply = message.answer.call_args[0][0]
    assert "— @mybot" in reply


# ---------------------------------------------------------------------------
# Задача 5: /stats реферальные метрики
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_stats_module(full_db_path, monkeypatch):
    import services.stats as stats_m
    import services.referrals as ref_m
    monkeypatch.setattr(stats_m, "config", {"STATS_DB_PATH": full_db_path})
    monkeypatch.setattr(ref_m, "config", {"STATS_DB_PATH": full_db_path})
    return stats_m, ref_m, full_db_path


@pytest.mark.asyncio
async def test_stats_admin_ref_metrics(full_stats_module, monkeypatch):
    """Администратор видит реферальные метрики в /stats."""
    stats_m, ref_m, db_path = full_stats_module

    await ref_m.record_referral(10, 100)
    await ref_m.record_referral(10, 101)
    await ref_m.record_referral(20, 102)

    import handlers.commands as cmd_m
    monkeypatch.setattr(cmd_m, "total_referrals", ref_m.total_referrals)
    monkeypatch.setattr(cmd_m, "top_referrers", ref_m.top_referrers)
    monkeypatch.setattr(cmd_m, "get_stats", stats_m.get_stats)

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42

    fake_config = {"ADMIN_USER_ID": 42, "STATS_DB_PATH": db_path}
    with patch("handlers.commands.config", fake_config):
        await cmd_m.cmd_stats(message)

    reply = message.answer.call_args[0][0]
    assert "Всего рефералов: 3" in reply
    assert "Топ приглашающих:" in reply
    assert "10: 2" in reply
    assert "20: 1" in reply


@pytest.mark.asyncio
async def test_stats_admin_no_referrals(full_stats_module, monkeypatch):
    """Если рефералов нет — выводится 'пока нет рефералов'."""
    stats_m, ref_m, db_path = full_stats_module

    import handlers.commands as cmd_m
    monkeypatch.setattr(cmd_m, "total_referrals", ref_m.total_referrals)
    monkeypatch.setattr(cmd_m, "top_referrers", ref_m.top_referrers)
    monkeypatch.setattr(cmd_m, "get_stats", stats_m.get_stats)

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42

    fake_config = {"ADMIN_USER_ID": 42, "STATS_DB_PATH": db_path}
    with patch("handlers.commands.config", fake_config):
        await cmd_m.cmd_stats(message)

    reply = message.answer.call_args[0][0]
    assert "пока нет рефералов" in reply


@pytest.mark.asyncio
async def test_stats_non_admin_no_ref_data(full_stats_module, monkeypatch):
    """Не-админ получает отказ без реферальных данных."""
    stats_m, ref_m, db_path = full_stats_module

    await ref_m.record_referral(10, 100)

    import handlers.commands as cmd_m

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 9999

    fake_config = {"ADMIN_USER_ID": 42, "STATS_DB_PATH": db_path}
    with patch("handlers.commands.config", fake_config):
        await cmd_m.cmd_stats(message)

    message.answer.assert_called_once_with("Команда недоступна.")


# ---------------------------------------------------------------------------
# Задача 6: /start в группе
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_in_group_does_not_crash(commands_module):
    """/start в группе: отвечает только START_TEXT, без реф-блока и без кнопки."""
    from handlers.commands import START_TEXT
    cmd_m, ref_m, ref_db_path = commands_module
    message = _make_message(chat_type="group", user_id=400)
    command = _make_command(args="ref_10")

    with patch("handlers.commands.get_bot_username", return_value="testbot"):
        await cmd_m.cmd_start(message, command, is_new_user=True)

    row = _fetch_referral(ref_db_path, 400)
    assert row is None
    message.answer.assert_called_once()
    call_args = message.answer.call_args
    assert call_args[0][0] == START_TEXT
    assert call_args.kwargs.get("reply_markup") is None


# ---------------------------------------------------------------------------
# Задача 7: init_referrals_db создаёт схему
# ---------------------------------------------------------------------------


def test_init_referrals_db_creates_schema(tmp_path, monkeypatch):
    """init_referrals_db создаёт таблицу referrals и индекс в указанном файле."""
    db_path = str(tmp_path / "test.db")

    import services.referrals as ref_m
    monkeypatch.setattr(ref_m, "config", {"STATS_DB_PATH": db_path})
    ref_m.init_referrals_db()

    con = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        indexes = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
    finally:
        con.close()

    assert "referrals" in tables
    assert "idx_referrals_referrer" in indexes


# ---------------------------------------------------------------------------
# Задача 8: bot_identity — общий держатель username
# ---------------------------------------------------------------------------


def test_bot_identity_set_and_get():
    """set_bot_username / get_bot_username работают корректно."""
    from services.bot_identity import get_bot_username, set_bot_username
    set_bot_username("@TestBot")
    assert get_bot_username() == "TestBot"


def test_bot_identity_empty_before_set():
    """После сброса (autouse-фикстура) держатель возвращает пустую строку."""
    from services.bot_identity import get_bot_username
    assert get_bot_username() == ""
