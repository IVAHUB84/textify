"""Тесты интеграции structure_text в хендлеры изображений и аудио."""
from unittest.mock import AsyncMock, patch

import pytest

from handlers.image import NO_TEXT_MESSAGE, handle_photo, handle_image_document
from handlers.audio import NO_SPEECH_MESSAGE, handle_voice, handle_audio, handle_audio_document


def _make_message() -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_bot_with_download(content: bytes = b"fake") -> AsyncMock:
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(content)

    bot.download = fake_download
    return bot


# ---------------------------------------------------------------------------
# Канал изображений
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_photo_calls_structure_text_on_nonempty_ocr():
    """handle_photo вызывает structure_text при непустом OCR и отдаёт результат через send_result."""
    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="raw ocr")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## structured")) as mock_struct,
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_struct.assert_awaited_once_with("raw ocr")
    mock_send.assert_awaited_once_with(message, "## structured")


@pytest.mark.asyncio
async def test_handle_photo_no_structure_on_empty_ocr():
    """handle_photo при пустом OCR отправляет NO_TEXT_MESSAGE напрямую, structure_text не вызывается."""
    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_struct.assert_not_awaited()
    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_TEXT_MESSAGE)


@pytest.mark.asyncio
async def test_handle_image_document_calls_structure_text_on_nonempty_ocr():
    """handle_image_document вызывает structure_text при непустом OCR."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="raw ocr doc")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## doc structured")) as mock_struct,
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_image_document(message, bot)

    mock_struct.assert_awaited_once_with("raw ocr doc")
    mock_send.assert_awaited_once_with(message, "## doc structured")


@pytest.mark.asyncio
async def test_handle_image_document_no_structure_on_empty_ocr():
    """handle_image_document при пустом OCR — NO_TEXT_MESSAGE, structure_text не вызван."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="   ")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_image_document(message, bot)

    mock_struct.assert_not_awaited()
    mock_send.assert_not_awaited()
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
# Канал аудио
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_voice_calls_structure_text_on_nonempty_transcript():
    """handle_voice вызывает structure_text при непустом транскрипте."""
    message = _make_message()
    message.voice = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="voice transcript")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## voice structured")) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_struct.assert_awaited_once_with("voice transcript")
    mock_send.assert_awaited_once_with(message, "## voice structured")


@pytest.mark.asyncio
async def test_handle_voice_no_structure_on_empty_transcript():
    """handle_voice при пустом транскрипте — NO_SPEECH_MESSAGE напрямую, structure_text не вызван."""
    message = _make_message()
    message.voice = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_struct.assert_not_awaited()
    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


@pytest.mark.asyncio
async def test_handle_audio_calls_structure_text_on_nonempty_transcript():
    """handle_audio вызывает structure_text при непустом транскрипте."""
    message = _make_message()
    message.audio = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="audio text")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## audio ok")) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_audio(message, bot)

    mock_struct.assert_awaited_once_with("audio text")
    mock_send.assert_awaited_once_with(message, "## audio ok")


@pytest.mark.asyncio
async def test_handle_audio_no_structure_on_empty_transcript():
    """handle_audio при пустом транскрипте — NO_SPEECH_MESSAGE, structure_text не вызван."""
    message = _make_message()
    message.audio = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="  ")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_audio(message, bot)

    mock_struct.assert_not_awaited()
    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


@pytest.mark.asyncio
async def test_handle_audio_document_calls_structure_text_on_nonempty_transcript():
    """handle_audio_document вызывает structure_text при непустом транскрипте."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="doc audio text")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## doc ok")) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_audio_document(message, bot)

    mock_struct.assert_awaited_once_with("doc audio text")
    mock_send.assert_awaited_once_with(message, "## doc ok")


@pytest.mark.asyncio
async def test_handle_audio_document_no_structure_on_empty_transcript():
    """handle_audio_document при пустом транскрипте — NO_SPEECH_MESSAGE."""
    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_struct,
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_audio_document(message, bot)

    mock_struct.assert_not_awaited()
    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


def test_audio_handler_does_not_import_httpx():
    """handlers/audio.py не импортирует httpx или провайдера напрямую."""
    import handlers.audio as mod
    import types
    module_globals = vars(mod)
    httpx_refs = [k for k, v in module_globals.items()
                  if isinstance(v, types.ModuleType) and v.__name__ == "httpx"]
    assert not httpx_refs, "handlers/audio.py напрямую импортирует httpx"
