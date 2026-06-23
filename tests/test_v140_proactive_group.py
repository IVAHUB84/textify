"""Тесты v1.4.0: проактивный оффер-кнопка в группах, callback grec."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------


def _make_message(
    chat_type: str = "group",
    has_photo: bool = False,
    has_voice: bool = False,
    has_audio: bool = False,
    has_image_doc: bool = False,
    has_audio_doc: bool = False,
    text: str | None = None,
    reply_to=None,
) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock()
    msg.chat.type = chat_type
    msg.chat.id = 200
    msg.message_id = 42
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.text = text
    msg.caption = None
    msg.entities = None
    msg.caption_entities = None
    msg.reply_to_message = reply_to

    msg.photo = [MagicMock()] if has_photo else None
    msg.voice = MagicMock() if has_voice else None
    msg.audio = MagicMock() if has_audio else None

    if has_image_doc:
        msg.document = MagicMock()
        msg.document.mime_type = "image/png"
    elif has_audio_doc:
        msg.document = MagicMock()
        msg.document.mime_type = "audio/ogg"
    else:
        msg.document = None

    return msg


def _make_callback(reply_to=None) -> MagicMock:
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.bot = AsyncMock()
    cb.message = MagicMock()
    cb.message.reply_to_message = reply_to
    return cb


def _make_inaccessible_message() -> MagicMock:
    from aiogram.types import InaccessibleMessage
    return MagicMock(spec=InaccessibleMessage)


# ---------------------------------------------------------------------------
# Задача 1: media-offer — оффер на аудио
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_offer_on_voice():
    """Voice в группе → reply с кнопкой «Распознать голос», callback_data == 'grec'."""
    import handlers.group as grp

    msg = _make_message(has_voice=True)
    await grp.handle_group_media_offer(msg)

    msg.reply.assert_awaited_once()
    call_kwargs = msg.reply.await_args[1]
    offer_text = call_kwargs["text"]
    assert offer_text and offer_text.strip(), "text оффера не должен быть пустым или состоять только из пробельных символов"
    keyboard = call_kwargs["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Распознать голос"
    assert button.callback_data == "grec"


@pytest.mark.asyncio
async def test_offer_on_audio():
    """Audio в группе → reply с кнопкой «Распознать голос»."""
    import handlers.group as grp

    msg = _make_message(has_audio=True)
    await grp.handle_group_media_offer(msg)

    msg.reply.assert_awaited_once()
    keyboard = msg.reply.await_args[1]["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Распознать голос"
    assert button.callback_data == "grec"


@pytest.mark.asyncio
async def test_offer_on_audio_document():
    """Document audio/* в группе → reply с кнопкой «Распознать голос»."""
    import handlers.group as grp

    msg = _make_message(has_audio_doc=True)
    await grp.handle_group_media_offer(msg)

    msg.reply.assert_awaited_once()
    keyboard = msg.reply.await_args[1]["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Распознать голос"
    assert button.callback_data == "grec"


@pytest.mark.asyncio
async def test_offer_on_photo():
    """Photo в группе → reply с кнопкой «Распознать текст»."""
    import handlers.group as grp

    msg = _make_message(has_photo=True)
    await grp.handle_group_media_offer(msg)

    msg.reply.assert_awaited_once()
    keyboard = msg.reply.await_args[1]["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Распознать текст"
    assert button.callback_data == "grec"


@pytest.mark.asyncio
async def test_offer_on_image_document():
    """Document image/* в группе → reply с кнопкой «Распознать текст»."""
    import handlers.group as grp

    msg = _make_message(has_image_doc=True)
    await grp.handle_group_media_offer(msg)

    msg.reply.assert_awaited_once()
    keyboard = msg.reply.await_args[1]["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Распознать текст"
    assert button.callback_data == "grec"


@pytest.mark.asyncio
async def test_offer_text_is_visible():
    """text оффера непустой, видимый (без zero-width / пробельных символов)."""
    import unicodedata
    import handlers.group as grp

    _ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿"}

    for factory_kwargs in [
        {"has_voice": True},
        {"has_photo": True},
        {"has_audio_doc": True},
        {"has_image_doc": True},
    ]:
        msg = _make_message(**factory_kwargs)
        await grp.handle_group_media_offer(msg)

        offer_text: str = msg.reply.await_args[1]["text"]
        assert offer_text, "text оффера пустой"
        visible = "".join(
            ch for ch in offer_text
            if ch not in _ZERO_WIDTH and not unicodedata.category(ch).startswith("Z")
        )
        assert visible.strip(), f"text оффера не содержит видимых символов: {offer_text!r}"

        msg.reply.reset_mock()


# ---------------------------------------------------------------------------
# Задача 1: media-offer — молчание на текст
# ---------------------------------------------------------------------------


def test_has_supported_media_returns_false_for_text():
    """_has_supported_media возвращает False для текстового сообщения."""
    from handlers.group import _has_supported_media

    msg = _make_message(text="просто текст")
    assert _has_supported_media(msg) is False


@pytest.mark.asyncio
async def test_offer_handler_not_called_for_text():
    """На текстовое сообщение handle_group_media_offer не вызывает reply."""
    import handlers.group as grp
    from handlers.group import _has_supported_media

    msg = _make_message(text="просто текст")
    assert not _has_supported_media(msg)

    await grp.handle_group_media_offer(msg)
    msg.reply.assert_not_awaited()
    msg.answer.assert_not_awaited()


# ---------------------------------------------------------------------------
# Задача 2: callback grec — тап по аудио
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grec_callback_on_voice_calls_dispatch():
    """Тап grec при reply_to_message = voice → _dispatch_media вызывается."""
    import handlers.group as grp

    media_msg = _make_message(has_voice=True)
    cb = _make_callback(reply_to=media_msg)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    cb.answer.assert_awaited()
    mock_dispatch.assert_awaited_once_with(media_msg, cb.bot)


@pytest.mark.asyncio
async def test_grec_callback_on_audio_calls_dispatch():
    """Тап grec при reply_to_message = audio → _dispatch_media вызывается."""
    import handlers.group as grp

    media_msg = _make_message(has_audio=True)
    cb = _make_callback(reply_to=media_msg)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    mock_dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_grec_callback_on_photo_calls_dispatch():
    """Тап grec при reply_to_message = photo → _dispatch_media вызывается."""
    import handlers.group as grp

    media_msg = _make_message(has_photo=True)
    cb = _make_callback(reply_to=media_msg)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    mock_dispatch.assert_awaited_once()


# ---------------------------------------------------------------------------
# Задача 2: callback grec — force_local по GROUP_ASR_LOCAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grec_callback_audio_force_local_true():
    """GROUP_ASR_LOCAL=True → process_audio вызывается с force_local=True."""
    import handlers.group as grp

    media_msg = _make_message(has_voice=True)
    cb = _make_callback(reply_to=media_msg)

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    cb.bot.download = fake_download

    with (
        patch("handlers.group.config", {"GROUP_ASR_LOCAL": True}),
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_audio,
    ):
        await grp.handle_grec_callback(cb, cb.bot)

    mock_audio.assert_awaited_once()
    assert mock_audio.await_args[1].get("force_local") is True


@pytest.mark.asyncio
async def test_grec_callback_audio_force_local_false():
    """GROUP_ASR_LOCAL=False → process_audio вызывается с force_local=False."""
    import handlers.group as grp

    media_msg = _make_message(has_voice=True)
    cb = _make_callback(reply_to=media_msg)

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    cb.bot.download = fake_download

    with (
        patch("handlers.group.config", {"GROUP_ASR_LOCAL": False}),
        patch("handlers.group.process_audio", new=AsyncMock()) as mock_audio,
    ):
        await grp.handle_grec_callback(cb, cb.bot)

    mock_audio.assert_awaited_once()
    assert mock_audio.await_args[1].get("force_local") is False


# ---------------------------------------------------------------------------
# Задача 2: callback grec — тап по изображению
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grec_callback_on_image_document():
    """Тап grec при reply_to_message = image document → process_image_document вызывается."""
    import handlers.group as grp

    media_msg = _make_message(has_image_doc=True)
    cb = _make_callback(reply_to=media_msg)

    with patch("handlers.group.process_image_document", new=AsyncMock()) as mock_proc:
        await grp.handle_grec_callback(cb, cb.bot)

    mock_proc.assert_awaited_once_with(media_msg, media_msg, cb.bot)


@pytest.mark.asyncio
async def test_grec_callback_on_photo():
    """Тап grec при reply_to_message = photo → process_photo вызывается."""
    import handlers.group as grp

    media_msg = _make_message(has_photo=True)
    cb = _make_callback(reply_to=media_msg)

    with patch("handlers.group.process_photo", new=AsyncMock()) as mock_proc:
        await grp.handle_grec_callback(cb, cb.bot)

    mock_proc.assert_awaited_once_with(media_msg, media_msg, cb.bot)


# ---------------------------------------------------------------------------
# Задача 2: callback grec — недоступный reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grec_callback_reply_none_shows_alert():
    """reply_to_message = None → callback.answer(show_alert=True), пайплайн не вызван."""
    import handlers.group as grp

    cb = _make_callback(reply_to=None)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    call_args = cb.answer.await_args
    assert call_args[1].get("show_alert") is True
    mock_dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_grec_callback_inaccessible_message_shows_alert():
    """reply_to_message = InaccessibleMessage → callback.answer(show_alert=True), пайплайн не вызван."""
    import handlers.group as grp

    inaccessible = _make_inaccessible_message()
    cb = _make_callback(reply_to=inaccessible)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    call_args = cb.answer.await_args
    assert call_args[1].get("show_alert") is True
    mock_dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_grec_callback_no_media_in_reply_shows_alert():
    """reply_to_message без поддерживаемого медиа → callback.answer(show_alert=True), пайплайн не вызван."""
    import handlers.group as grp

    text_msg = _make_message(text="просто текст")
    cb = _make_callback(reply_to=text_msg)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()) as mock_dispatch:
        await grp.handle_grec_callback(cb, cb.bot)

    call_args = cb.answer.await_args
    assert call_args[1].get("show_alert") is True
    mock_dispatch.assert_not_awaited()


# ---------------------------------------------------------------------------
# Задача 2: callback.answer вызывается во всех ветках
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grec_answer_called_when_valid():
    """callback.answer вызывается при валидном reply."""
    import handlers.group as grp

    media_msg = _make_message(has_voice=True)
    cb = _make_callback(reply_to=media_msg)

    with patch.object(grp, "_dispatch_media", new=AsyncMock()):
        await grp.handle_grec_callback(cb, cb.bot)

    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_grec_answer_called_when_reply_none():
    """callback.answer вызывается даже когда reply = None."""
    import handlers.group as grp

    cb = _make_callback(reply_to=None)
    await grp.handle_grec_callback(cb, cb.bot)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_grec_answer_called_when_inaccessible():
    """callback.answer вызывается даже когда reply = InaccessibleMessage."""
    import handlers.group as grp

    inaccessible = _make_inaccessible_message()
    cb = _make_callback(reply_to=inaccessible)
    await grp.handle_grec_callback(cb, cb.bot)
    cb.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Задача 3: регресс триггера v1.2.0 — триггер-хендлеры присутствуют
# ---------------------------------------------------------------------------


def test_trigger_handlers_still_present():
    """handle_group_textify_command и handle_group_mention по-прежнему экспортируются."""
    import handlers.group as grp
    assert callable(grp.handle_group_textify_command)
    assert callable(grp.handle_group_mention)
    assert callable(grp._dispatch_media)
    assert callable(grp._has_supported_media)


@pytest.mark.asyncio
async def test_trigger_textify_still_works():
    """Регресс: /textify reply на voice → process_audio вызывается (триггер не сломан)."""
    import handlers.group as grp
    grp.set_bot_username("TestifyBot")

    reply_msg = _make_message(has_voice=True)
    trigger_msg = _make_message(reply_to=reply_msg)

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    grp_bot = AsyncMock()
    grp_bot.download = fake_download

    with patch("handlers.group.process_audio", new=AsyncMock()) as mock_proc:
        await grp.handle_group_textify_command(trigger_msg, grp_bot)

    mock_proc.assert_awaited_once()
    assert mock_proc.await_args[0][0] is reply_msg


# ---------------------------------------------------------------------------
# Порядок хендлеров в group_router
# ---------------------------------------------------------------------------


def test_group_router_handler_count():
    """group_router содержит ровно 3 message-хендлера: textify, mention, media-offer."""
    from handlers.group import group_router
    handlers = list(group_router.message.handlers)
    assert len(handlers) == 3, (
        f"group_router должен иметь 3 хендлера (textify + mention + media-offer), "
        f"найдено: {len(handlers)}"
    )


def test_grec_callback_handler_registered():
    """group_router содержит callback-хендлер для 'grec'."""
    from handlers.group import group_router
    handlers = list(group_router.callback_query.handlers)
    assert len(handlers) >= 1
