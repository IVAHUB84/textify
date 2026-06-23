"""Тесты интеграции структурирования в хендлеры изображений и аудио."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.result_cache as cache_mod
from handlers.image import NO_TEXT_MESSAGE, handle_photo, handle_image_document
from handlers.audio import NO_SPEECH_MESSAGE, handle_voice, handle_audio, handle_audio_document


_CHAT_ID = 88888


def _make_message(message_id: int = 77) -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    msg.message_id = message_id
    msg.chat = AsyncMock()
    msg.chat.id = _CHAT_ID
    sent = AsyncMock()
    sent.message_id = message_id + 1000
    sent.chat = AsyncMock()
    sent.chat.id = _CHAT_ID
    msg.answer.return_value = sent
    return msg


def _make_sender_mock() -> MagicMock:
    sender = MagicMock()
    sender.__aenter__ = AsyncMock(return_value=None)
    sender.__aexit__ = AsyncMock(return_value=False)
    return sender


@pytest.fixture(autouse=True)
def mock_chat_action_sender():
    sender = _make_sender_mock()
    with (
        patch("handlers.image.ChatActionSender", return_value=sender),
        patch("handlers.audio.ChatActionSender", return_value=sender),
    ):
        yield sender


@pytest.fixture(autouse=True)
def clear_cache():
    cache_mod._cache.clear()
    yield
    cache_mod._cache.clear()


def _make_bot_with_download(content: bytes = b"fake") -> AsyncMock:
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(content)

    bot.download = fake_download
    return bot


# ---------------------------------------------------------------------------
# Канал изображений — личка (progressive=True, суть вместо полного текста)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_photo_progressive_sends_preview_on_nonempty_ocr():
    """handle_photo в личке → отправляет превью (суть), кэш заполнен, structure_text не вызван."""
    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="raw ocr")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
    ):
        await handle_photo(message, bot)

    mock_struct.assert_not_awaited()
    message.answer.assert_awaited_once()
    preview = message.answer.await_args[0][0]
    assert preview == "суть"

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "raw ocr"


@pytest.mark.asyncio
async def test_handle_photo_no_structure_on_empty_ocr():
    """handle_photo при пустом OCR отправляет NO_TEXT_MESSAGE, structure_text не вызывается."""
    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.image.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await handle_photo(message, bot)

    mock_struct.assert_not_awaited()
    mock_gist.assert_not_awaited()
    message.answer.assert_called_once_with(NO_TEXT_MESSAGE)


@pytest.mark.asyncio
async def test_handle_image_document_progressive_sends_preview_on_nonempty_ocr():
    """handle_image_document в личке → превью-суть, структура не вызвана."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="raw ocr doc")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
    ):
        await handle_image_document(message, bot)

    mock_struct.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args[0][0] == "суть"


@pytest.mark.asyncio
async def test_handle_image_document_no_structure_on_empty_ocr():
    """handle_image_document при пустом OCR — NO_TEXT_MESSAGE."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="   ")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.image.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await handle_image_document(message, bot)

    mock_struct.assert_not_awaited()
    mock_gist.assert_not_awaited()
    message.answer.assert_called_once_with(NO_TEXT_MESSAGE)


def test_image_handler_does_not_import_httpx():
    """handlers/image.py не импортирует httpx или провайдера напрямую."""
    import handlers.image as mod
    import types
    module_globals = vars(mod)
    httpx_refs = [k for k, v in module_globals.items()
                  if isinstance(v, types.ModuleType) and v.__name__ == "httpx"]
    assert not httpx_refs, "handlers/image.py напрямую импортирует httpx"


# ---------------------------------------------------------------------------
# Канал аудио — личка (progressive=True, суть вместо полного текста)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_voice_progressive_sends_preview_on_nonempty_transcript():
    """handle_voice в личке → превью-суть, structure_text не вызван."""
    message = _make_message()
    message.voice = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="voice transcript")),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
    ):
        await handle_voice(message, bot)

    mock_struct.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args[0][0] == "суть"

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "voice transcript"


@pytest.mark.asyncio
async def test_handle_voice_no_structure_on_empty_transcript():
    """handle_voice при пустом транскрипте — NO_SPEECH_MESSAGE, structure_text не вызван."""
    message = _make_message()
    message.voice = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await handle_voice(message, bot)

    mock_struct.assert_not_awaited()
    mock_gist.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


@pytest.mark.asyncio
async def test_handle_audio_progressive_sends_preview_on_nonempty_transcript():
    """handle_audio в личке → превью-суть."""
    message = _make_message()
    message.audio = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="audio text")),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть аудио")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
    ):
        await handle_audio(message, bot)

    mock_struct.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args[0][0] == "суть аудио"


@pytest.mark.asyncio
async def test_handle_audio_no_structure_on_empty_transcript():
    """handle_audio при пустом транскрипте — NO_SPEECH_MESSAGE."""
    message = _make_message()
    message.audio = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="  ")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await handle_audio(message, bot)

    mock_struct.assert_not_awaited()
    mock_gist.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


@pytest.mark.asyncio
async def test_handle_audio_document_progressive_sends_preview_on_nonempty_transcript():
    """handle_audio_document в личке → превью-суть."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="doc audio text")),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть документа")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
    ):
        await handle_audio_document(message, bot)

    mock_struct.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args[0][0] == "суть документа"


@pytest.mark.asyncio
async def test_handle_audio_document_no_structure_on_empty_transcript():
    """handle_audio_document при пустом транскрипте — NO_SPEECH_MESSAGE."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await handle_audio_document(message, bot)

    mock_struct.assert_not_awaited()
    mock_gist.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


def test_audio_handler_does_not_import_httpx():
    """handlers/audio.py не импортирует httpx или провайдера напрямую."""
    import handlers.audio as mod
    import types
    module_globals = vars(mod)
    httpx_refs = [k for k, v in module_globals.items()
                  if isinstance(v, types.ModuleType) and v.__name__ == "httpx"]
    assert not httpx_refs, "handlers/audio.py напрямую импортирует httpx"
