"""Тесты v1.2.0: групповой роутер, фильтры чата, force_local ASR, регресс лички."""
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------


def _make_sender_mock():
    sender = MagicMock()
    sender.__aenter__ = AsyncMock(return_value=None)
    sender.__aexit__ = AsyncMock(return_value=False)
    return sender


def _make_message(
    chat_type: str = "private",
    has_photo: bool = False,
    has_voice: bool = False,
    has_audio: bool = False,
    has_image_doc: bool = False,
    has_audio_doc: bool = False,
    text: str | None = None,
    entities: list | None = None,
    caption: str | None = None,
    caption_entities: list | None = None,
    reply_to: "MagicMock | None" = None,
) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock()
    msg.chat.type = chat_type
    msg.chat.id = 100
    msg.answer = AsyncMock()
    msg.text = text
    msg.caption = caption
    msg.entities = entities
    msg.caption_entities = caption_entities
    msg.reply_to_message = reply_to

    msg.photo = [MagicMock()] if has_photo else None
    msg.voice = MagicMock() if has_voice else None
    msg.audio = MagicMock() if has_audio else None

    if has_image_doc:
        msg.document = MagicMock()
        msg.document.mime_type = "image/jpeg"
    elif has_audio_doc:
        msg.document = MagicMock()
        msg.document.mime_type = "audio/ogg"
    else:
        msg.document = None

    return msg


def _make_entity(entity_type: str, offset: int, length: int, username: str | None = None):
    entity = MagicMock()
    entity.type = entity_type
    entity.offset = offset
    entity.length = length
    if entity_type == "text_mention":
        entity.user = MagicMock()
        entity.user.username = username
    else:
        entity.user = None
    return entity


# ---------------------------------------------------------------------------
# Задача 2: Фильтры чата — приватные хендлеры не срабатывают в группах
# ---------------------------------------------------------------------------


def _get_router_level_private_filter(router):
    """Извлекает роутер-уровневый фильтр F.chat.type=='private' и возвращает его.

    Возвращает первый MagicFilter из _handler.filters роутера, который даёт True на
    private и False на group. Падает с AssertionError если такого фильтра нет.
    """
    filters = router.message._handler.filters
    assert filters, "router.message не имеет роутер-уровневых фильтров"
    msg_private = MagicMock()
    msg_private.chat.type = "private"
    msg_group = MagicMock()
    msg_group.chat.type = "group"
    for f in filters:
        if f.magic is not None:
            allows_private = f.magic.resolve(msg_private)
            allows_group = f.magic.resolve(msg_group)
            if allows_private and not allows_group:
                return f.magic
    raise AssertionError(
        "Не найден роутер-уровневый фильтр, разрешающий private и блокирующий group"
    )


def test_image_router_blocks_group_chat():
    """image router: фильтр F.chat.type=='private' блокирует group и пропускает private."""
    from handlers.image import router
    private_filter = _get_router_level_private_filter(router)
    msg_private = MagicMock()
    msg_private.chat.type = "private"
    msg_group = MagicMock()
    msg_group.chat.type = "group"
    assert private_filter.resolve(msg_private) is True
    assert private_filter.resolve(msg_group) is False


def test_audio_router_blocks_group_chat():
    """audio router: фильтр F.chat.type=='private' блокирует group и пропускает private."""
    from handlers.audio import router
    private_filter = _get_router_level_private_filter(router)
    msg_private = MagicMock()
    msg_private.chat.type = "private"
    msg_group = MagicMock()
    msg_group.chat.type = "group"
    assert private_filter.resolve(msg_private) is True
    assert private_filter.resolve(msg_group) is False


def test_text_router_blocks_group_chat():
    """text router: фильтр F.chat.type=='private' блокирует group и пропускает private."""
    from handlers.text import router
    private_filter = _get_router_level_private_filter(router)
    msg_private = MagicMock()
    msg_private.chat.type = "private"
    msg_group = MagicMock()
    msg_group.chat.type = "group"
    assert private_filter.resolve(msg_private) is True
    assert private_filter.resolve(msg_group) is False


# ---------------------------------------------------------------------------
# Задача 3: group_router зарегистрирован и имеет хендлеры
# ---------------------------------------------------------------------------


def test_group_router_exported():
    """group_router экспортируется из handlers/__init__.py."""
    from handlers import group_router
    from handlers.group import group_router as gr
    assert group_router is gr


def test_group_router_has_handlers():
    """group_router содержит хендлеры сообщений."""
    from handlers.group import group_router
    handlers = list(group_router.message.handlers)
    assert len(handlers) >= 1


# ---------------------------------------------------------------------------
# Задача 5: Порядок роутеров в bot.py
# ---------------------------------------------------------------------------


def test_bot_router_order():
    """Порядок роутеров в bot.py: commands → actions → group → image → audio → text.

    Проверяется через порядок включения в исходнике bot.py.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).parent.parent / "bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    include_calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "include_router"
        ):
            args = node.value.args
            if args and isinstance(args[0], ast.Name):
                include_calls.append(args[0].id)

    expected_order = [
        "commands_router",
        "actions_router",
        "group_router",
        "image_router",
        "audio_router",
        "text_router",
    ]
    for name in expected_order:
        assert name in include_calls, f"{name} не найден в dp.include_router вызовах bot.py"

    positions = {name: include_calls.index(name) for name in expected_order}
    assert positions["commands_router"] < positions["group_router"]
    assert positions["actions_router"] < positions["group_router"]
    assert positions["group_router"] < positions["image_router"]
    assert positions["group_router"] < positions["audio_router"]
    assert positions["image_router"] < positions["text_router"]
    assert positions["audio_router"] < positions["text_router"]


# ---------------------------------------------------------------------------
# Задача 6: config — GROUP_ASR_LOCAL
# ---------------------------------------------------------------------------


def _reload_config(monkeypatch, envs: dict):
    for key, val in envs.items():
        monkeypatch.setenv(key, val)
    for mod_name in list(sys.modules):
        if mod_name == "config":
            del sys.modules[mod_name]
    return importlib.import_module("config")


def test_config_group_asr_local_default(monkeypatch):
    """Отсутствие GROUP_ASR_LOCAL → True."""
    monkeypatch.setenv("BOT_TOKEN", "tok")
    monkeypatch.delenv("GROUP_ASR_LOCAL", raising=False)
    if "config" in sys.modules:
        del sys.modules["config"]
    cfg = importlib.import_module("config")
    assert cfg.config["GROUP_ASR_LOCAL"] is True


def test_config_group_asr_local_true(monkeypatch):
    """GROUP_ASR_LOCAL=true → True."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "true"})
    assert module.config["GROUP_ASR_LOCAL"] is True


def test_config_group_asr_local_one(monkeypatch):
    """GROUP_ASR_LOCAL=1 → True."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "1"})
    assert module.config["GROUP_ASR_LOCAL"] is True


def test_config_group_asr_local_yes(monkeypatch):
    """GROUP_ASR_LOCAL=yes → True."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "yes"})
    assert module.config["GROUP_ASR_LOCAL"] is True


def test_config_group_asr_local_false(monkeypatch):
    """GROUP_ASR_LOCAL=false → False."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "false"})
    assert module.config["GROUP_ASR_LOCAL"] is False


def test_config_group_asr_local_zero(monkeypatch):
    """GROUP_ASR_LOCAL=0 → False."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "0"})
    assert module.config["GROUP_ASR_LOCAL"] is False


def test_config_group_asr_local_no(monkeypatch):
    """GROUP_ASR_LOCAL=no → False."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "no"})
    assert module.config["GROUP_ASR_LOCAL"] is False


def test_config_group_asr_local_invalid_defaults(monkeypatch):
    """GROUP_ASR_LOCAL=garbage → дефолт True, старт не падает."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": "garbage"})
    assert module.config["GROUP_ASR_LOCAL"] is True


def test_config_group_asr_local_empty_defaults(monkeypatch):
    """GROUP_ASR_LOCAL='' → дефолт True."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "GROUP_ASR_LOCAL": ""})
    assert module.config["GROUP_ASR_LOCAL"] is True


# ---------------------------------------------------------------------------
# transcribe(force_local=True) идёт локальным путём, CF не вызывается
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_force_local_skips_cf(monkeypatch):
    """force_local=True → _transcribe_local вызывается, CF post не вызывается."""
    httpx = pytest.importorskip("httpx")
    import services.transcribe as svc

    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")

    from types import SimpleNamespace
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([SimpleNamespace(text="local only")]), MagicMock())
    mock_post = AsyncMock()

    with (
        patch.object(httpx.AsyncClient, "post", mock_post),
        patch("services.transcribe._get_model", return_value=mock_model),
    ):
        result = await svc.transcribe(b"audio", force_local=True)

    assert result == "local only"
    mock_post.assert_not_called()
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_force_local_false_uses_cf(monkeypatch):
    """force_local=False (дефолт) → CF-путь используется при наличии кредов."""
    httpx = pytest.importorskip("httpx")
    import services.transcribe as svc

    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"result": {"text": "cf result"}}
    mock_post = AsyncMock(return_value=resp)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await svc.transcribe(b"audio", force_local=False)

    assert result == "cf result"
    mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# Фильтр упоминания: set_bot_username и _is_bot_mention
# ---------------------------------------------------------------------------


def _setup_username(username: str):
    import handlers.group as grp
    from services.bot_identity import set_bot_username
    set_bot_username(username)
    return grp


def test_mention_filter_recognizes_exact_mention():
    """mention с @botusername (точное совпадение) → True."""
    grp = _setup_username("TestifyBot")
    entity = _make_entity("mention", 0, 12)
    result = grp._is_bot_mention([entity], "@TestifyBot")
    assert result is True


def test_mention_filter_case_insensitive():
    """mention с @TESTIFYBOT (другой регистр) → True."""
    grp = _setup_username("testifybot")
    entity = _make_entity("mention", 0, 12)
    result = grp._is_bot_mention([entity], "@TESTIFYBOT")
    assert result is True


def test_mention_filter_different_user_not_matches():
    """mention @OtherBot → False."""
    grp = _setup_username("TestifyBot")
    entity = _make_entity("mention", 0, 9)
    result = grp._is_bot_mention([entity], "@OtherBot")
    assert result is False


def test_mention_filter_no_entities_returns_false():
    """Нет entities → False."""
    grp = _setup_username("TestifyBot")
    result = grp._is_bot_mention(None, "@TestifyBot")
    assert result is False


def test_mention_filter_no_username_configured():
    """_bot_username не задан → False (защита от хардкода)."""
    import handlers.group as grp
    from services.bot_identity import set_bot_username
    set_bot_username("")
    entity = _make_entity("mention", 0, 12)
    result = grp._is_bot_mention([entity], "@TestifyBot")
    assert result is False


def test_text_mention_on_bot_matches():
    """text_mention с username бота → True."""
    grp = _setup_username("TestifyBot")
    entity = _make_entity("text_mention", 0, 5, username="TestifyBot")
    result = grp._is_bot_mention([entity], "Textify")
    assert result is True


def test_text_mention_other_user_not_matches():
    """text_mention с другим username → False."""
    grp = _setup_username("TestifyBot")
    entity = _make_entity("text_mention", 0, 5, username="OtherUser")
    result = grp._is_bot_mention([entity], "Other")
    assert result is False


def test_arbitrary_substring_not_mention():
    """Текст содержит @TestifyBot как подстроку, но без сущности-mention → False."""
    grp = _setup_username("TestifyBot")
    result = grp._is_bot_mention([], "Напиши @TestifyBot и что-то")
    assert result is False


# ---------------------------------------------------------------------------
# Группа: /textify reply на голосовое → process_audio вызывается с reply_to_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_textify_command_voice_reply():
    """reply + /textify на voice → process_audio вызывается с reply_to_message."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_voice=True)
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)

    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio_bytes")

    bot.download = fake_download

    with patch("handlers.group.process_audio", new=AsyncMock()) as mock_process:
        await grp.handle_group_textify_command(trigger_msg, bot)

    mock_process.assert_awaited_once()
    call_args = mock_process.await_args
    assert call_args[0][0] is reply_msg
    assert call_args[0][1] is reply_msg


@pytest.mark.asyncio
async def test_group_textify_command_photo_reply():
    """reply + /textify на photo → process_photo вызывается с reply_to_message."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_photo=True)
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)

    bot = AsyncMock()

    with patch("handlers.group.process_photo", new=AsyncMock()) as mock_process:
        await grp.handle_group_textify_command(trigger_msg, bot)

    mock_process.assert_awaited_once()
    call_args = mock_process.await_args
    assert call_args[0][0] is reply_msg
    assert call_args[0][1] is reply_msg


# ---------------------------------------------------------------------------
# Группа: упоминание @bot → обработка reply_to_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_mention_audio_reply():
    """reply + @mention на audio → process_audio вызывается с reply_to_message."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_audio=True)

    entity = _make_entity("mention", 0, 12)
    trigger_msg = _make_message(
        chat_type="group",
        text="@TestifyBot распознай",
        entities=[entity],
        reply_to=reply_msg,
    )

    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio_bytes")

    bot.download = fake_download

    with patch("handlers.group.process_audio", new=AsyncMock()) as mock_process:
        await grp.handle_group_mention(trigger_msg, bot)

    mock_process.assert_awaited_once()
    assert mock_process.await_args[0][0] is reply_msg
    assert mock_process.await_args[0][1] is reply_msg


@pytest.mark.asyncio
async def test_group_mention_photo_reply():
    """reply + @mention на photo → process_photo вызывается."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_photo=True)
    entity = _make_entity("mention", 0, 12)
    trigger_msg = _make_message(
        chat_type="group",
        text="@TestifyBot",
        entities=[entity],
        reply_to=reply_msg,
    )

    bot = AsyncMock()

    with patch("handlers.group.process_photo", new=AsyncMock()) as mock_process:
        await grp.handle_group_mention(trigger_msg, bot)

    mock_process.assert_awaited_once()
    assert mock_process.await_args[0][0] is reply_msg


# ---------------------------------------------------------------------------
# Группа: триггер без reply → подсказка, обработки нет
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_textify_no_reply_sends_hint():
    """Команда /textify без reply_to_message → подсказка, process_* не вызывается."""
    import handlers.group as grp

    trigger_msg = _make_message(chat_type="group", reply_to=None)

    bot = AsyncMock()

    with (
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_audio,
        patch("handlers.group.process_photo", new=AsyncMock()) as mock_photo,
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    trigger_msg.answer.assert_awaited_once_with(grp._HINT_MESSAGE)
    mock_audio.assert_not_awaited()
    mock_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_textify_reply_no_media_sends_hint():
    """Команда /textify, reply есть, но медиа нет → подсказка."""
    import handlers.group as grp

    reply_msg = _make_message(chat_type="group")
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)

    bot = AsyncMock()

    with (
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_audio,
        patch("handlers.group.process_photo", new=AsyncMock()) as mock_photo,
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    trigger_msg.answer.assert_awaited_once_with(grp._HINT_MESSAGE)
    mock_audio.assert_not_awaited()
    mock_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_mention_no_reply_sends_hint():
    """Упоминание без reply_to_message → подсказка."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    entity = _make_entity("mention", 0, 12)
    trigger_msg = _make_message(
        chat_type="group",
        text="@TestifyBot",
        entities=[entity],
        reply_to=None,
    )
    bot = AsyncMock()

    with patch("handlers.group.process_audio", new=AsyncMock()) as mock_audio:
        await grp.handle_group_mention(trigger_msg, bot)

    trigger_msg.answer.assert_awaited_once_with(grp._HINT_MESSAGE)
    mock_audio.assert_not_awaited()


# ---------------------------------------------------------------------------
# Группа: GROUP_ASR_LOCAL форсирует force_local
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_asr_force_local_true():
    """При GROUP_ASR_LOCAL=True групповой аудио вызывает process_audio с force_local=True."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_voice=True)
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio_bytes")

    bot.download = fake_download

    with (
        patch("handlers.group.config", {"GROUP_ASR_LOCAL": True}),
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_process,
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    mock_process.assert_awaited_once()
    call_kwargs = mock_process.await_args[1]
    assert call_kwargs.get("force_local") is True


@pytest.mark.asyncio
async def test_group_asr_force_local_false():
    """При GROUP_ASR_LOCAL=False групповой аудио вызывает process_audio с force_local=False."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_voice=True)
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio_bytes")

    bot.download = fake_download

    with (
        patch("handlers.group.config", {"GROUP_ASR_LOCAL": False}),
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_process,
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    mock_process.assert_awaited_once()
    call_kwargs = mock_process.await_args[1]
    assert call_kwargs.get("force_local") is False


# ---------------------------------------------------------------------------
# Личка регресс: photo/voice в private обрабатываются без reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_private_photo_handled_without_reply():
    """Фото в личке обрабатывается автоматически (без reply)."""
    from handlers.image import handle_photo

    message = _make_message(chat_type="private", has_photo=True)
    message.photo = [MagicMock(file_id="fid")]
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake_img")

    bot.download = fake_download
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## текст")),
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_voice_handled_without_reply():
    """Голосовое в личке обрабатывается автоматически (без reply)."""
    from handlers.audio import handle_voice

    message = _make_message(chat_type="private", has_voice=True)
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake_audio")

    bot.download = fake_download
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="речь")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## речь")),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_audio_handled_without_reply():
    """Аудиофайл в личке обрабатывается автоматически."""
    from handlers.audio import handle_audio

    message = _make_message(chat_type="private", has_audio=True)
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake_audio")

    bot.download = fake_download
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="речь")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## речь")),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_audio(message, bot)

    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_text_stub_reply():
    """Текст в личке получает заглушку."""
    from handlers.text import handle_text, STUB_TEXT

    message = _make_message(chat_type="private", text="привет")
    await handle_text(message)
    message.answer.assert_awaited_once_with(STUB_TEXT)


# ---------------------------------------------------------------------------
# Кнопки в группе: actions_keyboard возвращается под результатом
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_result_has_actions_keyboard():
    """Групповая обработка медиа → send_result вызывается с actions_keyboard."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(chat_type="group", has_photo=True)
    trigger_msg = _make_message(chat_type="group", reply_to=reply_msg)
    bot = AsyncMock()

    sender_mock = _make_sender_mock()

    async def fake_download(src, *, destination):
        destination.write(b"fake_img")

    bot.download = fake_download

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## текст")),
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    mock_send.assert_awaited_once()
    call_kwargs = mock_send.await_args[1]
    assert call_kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_group_callback_sum_works():
    """callback act:sum из группового сообщения отрабатывает через handle_summarize."""
    from handlers.actions import handle_summarize
    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.text = "Групповой текст"
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 999
    callback.message.chat.type = "group"

    sender_mock = _make_sender_mock()

    with (
        patch("handlers.actions.ChatActionSender", return_value=sender_mock),
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- краткий пункт")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_awaited_once()
    assert mock_send.await_args[0][1] == "- краткий пункт"


@pytest.mark.asyncio
async def test_group_callback_tr_works():
    """callback act:tr из группового сообщения отрабатывает через handle_translate."""
    from handlers.actions import handle_translate
    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.text = "Group text to translate"
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 999
    callback.message.chat.type = "supergroup"

    sender_mock = _make_sender_mock()

    with (
        patch("handlers.actions.ChatActionSender", return_value=sender_mock),
        patch("handlers.actions.translate", new=AsyncMock(return_value="Переведённый текст")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_send.assert_awaited_once()
    assert mock_send.await_args[0][1] == "Переведённый текст"


# ---------------------------------------------------------------------------
# Группа: авто-медиа без триггера НЕ обрабатывается
# (проверяем, что group_router не имеет catch-all хендлера)
# ---------------------------------------------------------------------------


def test_group_router_has_no_catch_all():
    """group_router не обрабатывает медиа без явного триггера (нет catch-all хендлера)."""
    from handlers.group import group_router
    handlers = list(group_router.message.handlers)
    # Должны быть только хендлеры с явными фильтрами (Command("textify") и mention-фильтр)
    # Не должно быть хендлера на F.photo, F.voice и т.п. напрямую
    assert len(handlers) == 2, (
        f"group_router должен иметь ровно 2 хендлера (textify-command + mention), "
        f"найдено: {len(handlers)}"
    )


# ---------------------------------------------------------------------------
# set_bot_username корректно задаёт username
# ---------------------------------------------------------------------------


def test_set_bot_username_strips_at():
    """set_bot_username убирает @ и сохраняет в общем держателе."""
    from services.bot_identity import get_bot_username, set_bot_username
    set_bot_username("@MyBot")
    assert get_bot_username() == "MyBot"


def test_set_bot_username_without_at():
    """set_bot_username без @ — тоже работает."""
    from services.bot_identity import get_bot_username, set_bot_username
    set_bot_username("MyBot")
    assert get_bot_username() == "MyBot"


# ---------------------------------------------------------------------------
# .env.example содержит GROUP_ASR_LOCAL
# ---------------------------------------------------------------------------


def test_env_example_has_group_asr_local():
    """корневой .env.example содержит GROUP_ASR_LOCAL=true."""
    from pathlib import Path
    env_example = Path(__file__).parent.parent / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    assert "GROUP_ASR_LOCAL=true" in content


def test_deploy_env_example_has_group_asr_local():
    """deploy/.env.example содержит GROUP_ASR_LOCAL=true."""
    from pathlib import Path
    env_example = Path(__file__).parent.parent / "deploy" / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    assert "GROUP_ASR_LOCAL=true" in content


# ---------------------------------------------------------------------------
# Личка: force_local всегда False (не передаётся в transcribe)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_private_audio_uses_default_force_local():
    """В личке transcribe вызывается с force_local=False (дефолт)."""
    from handlers.audio import handle_voice

    message = _make_message(chat_type="private", has_voice=True)
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    bot.download = fake_download
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="речь")) as mock_tr,
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## речь")),
        patch("handlers.audio.send_result", new=AsyncMock()),
    ):
        await handle_voice(message, bot)

    mock_tr.assert_awaited_once()
    call_kwargs = mock_tr.await_args[1]
    assert call_kwargs.get("force_local", False) is False


# ---------------------------------------------------------------------------
# _has_supported_media корректно определяет медиа
# ---------------------------------------------------------------------------


def test_has_supported_media_voice():
    """_has_supported_media возвращает True для voice."""
    from handlers.group import _has_supported_media
    msg = _make_message(has_voice=True)
    assert _has_supported_media(msg) is True


def test_has_supported_media_audio():
    """_has_supported_media возвращает True для audio."""
    from handlers.group import _has_supported_media
    msg = _make_message(has_audio=True)
    assert _has_supported_media(msg) is True


def test_has_supported_media_photo():
    """_has_supported_media возвращает True для photo."""
    from handlers.group import _has_supported_media
    msg = _make_message(has_photo=True)
    assert _has_supported_media(msg) is True


def test_has_supported_media_image_doc():
    """_has_supported_media возвращает True для image-документа."""
    from handlers.group import _has_supported_media
    msg = _make_message(has_image_doc=True)
    assert _has_supported_media(msg) is True


def test_has_supported_media_audio_doc():
    """_has_supported_media возвращает True для audio-документа."""
    from handlers.group import _has_supported_media
    msg = _make_message(has_audio_doc=True)
    assert _has_supported_media(msg) is True


def test_has_supported_media_none():
    """_has_supported_media возвращает False для сообщения без медиа."""
    from handlers.group import _has_supported_media
    msg = _make_message(text="просто текст")
    assert _has_supported_media(msg) is False
