"""Тесты v1.11.0: хендлер видео-канала."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.video import DECODE_ERROR_MESSAGE, NO_AUDIO_MESSAGE
from handlers.limits import OVERSIZED_MESSAGE


_CHAT_ID = 55555
_USER_ID = 12345
_AUDIO_BYTES = b"fake_audio_payload"
_VIDEO_BYTES = b"fake_video_bytes"


def _make_message(file_size: int = 1024 * 1024) -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    msg.message_id = 101
    msg.chat = MagicMock()
    msg.chat.id = _CHAT_ID
    msg.chat.type = "private"
    msg.from_user = MagicMock()
    msg.from_user.id = _USER_ID

    video = MagicMock()
    video.file_size = file_size
    msg.video = video

    video_note = MagicMock()
    video_note.file_size = file_size
    msg.video_note = video_note

    document = MagicMock()
    document.file_size = file_size
    document.mime_type = "video/mp4"
    msg.document = document

    return msg


def _make_bot(content: bytes = _VIDEO_BYTES) -> AsyncMock:
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(content)

    bot.download = fake_download
    return bot


# ---------------------------------------------------------------------------
# Три формы видео → extract_audio + process_audio вызываются
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_video_calls_extract_and_process_audio():
    """F.video: extract_audio вызывается с байтами, process_audio — с извлечённым аудио."""
    from handlers.video import handle_video

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=_AUDIO_BYTES)) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video(message, bot)

    mock_extract.assert_awaited_once_with(_VIDEO_BYTES)
    mock_process.assert_awaited_once()
    call_kwargs = mock_process.await_args
    assert call_kwargs.args[3] == _AUDIO_BYTES
    assert call_kwargs.kwargs.get("progressive") is True


@pytest.mark.asyncio
async def test_video_note_calls_extract_and_process_audio():
    """F.video_note: extract_audio вызывается с байтами, process_audio — с извлечённым аудио."""
    from handlers.video import handle_video_note

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=_AUDIO_BYTES)) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video_note(message, bot)

    mock_extract.assert_awaited_once_with(_VIDEO_BYTES)
    mock_process.assert_awaited_once()
    assert mock_process.await_args.args[3] == _AUDIO_BYTES


@pytest.mark.asyncio
async def test_video_document_calls_extract_and_process_audio():
    """document video/*: extract_audio вызывается с байтами, process_audio — с извлечённым аудио."""
    from handlers.video import handle_video_document

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=_AUDIO_BYTES)) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video_document(message, bot)

    mock_extract.assert_awaited_once_with(_VIDEO_BYTES)
    mock_process.assert_awaited_once()
    assert mock_process.await_args.args[3] == _AUDIO_BYTES


# ---------------------------------------------------------------------------
# Гард 20 МБ — extract_audio и process_audio не вызываются
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_video_returns_oversized_message():
    """file_size > 20 МБ → OVERSIZED_MESSAGE, extract_audio/process_audio не вызываются."""
    from handlers.video import handle_video

    oversized = 21 * 1024 * 1024
    message = _make_message(file_size=oversized)
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock()) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video(message, bot)

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == OVERSIZED_MESSAGE
    mock_extract.assert_not_awaited()
    mock_process.assert_not_awaited()


# ---------------------------------------------------------------------------
# extract_audio=None → NO_AUDIO_MESSAGE, process_audio не вызывается
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_audio_stream_returns_no_audio_message():
    """extract_audio → None: ответ NO_AUDIO_MESSAGE, process_audio не вызывается."""
    from handlers.video import handle_video

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=None)),
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video(message, bot)

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == NO_AUDIO_MESSAGE
    mock_process.assert_not_awaited()


# ---------------------------------------------------------------------------
# Ошибка декода → бот не падает, пользователь получает сообщение
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decode_error_does_not_crash_bot():
    """extract_audio бросает исключение → бот не падает, пользователь получает понятное сообщение."""
    from handlers.video import handle_video

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(side_effect=RuntimeError("corrupt"))),
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video(message, bot)

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == DECODE_ERROR_MESSAGE
    mock_process.assert_not_awaited()


# ---------------------------------------------------------------------------
# video_note без mime_type — диспетчеризация по типу (КП-1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_video_note_dispatched_by_type_not_mime():
    """video_note не имеет mime_type — хендлер всё равно вызывается (фильтр F.video_note по типу)."""
    from handlers.video import handle_video_note

    message = _make_message()
    message.video_note.mime_type = None  # кружочки не имеют mime

    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=_AUDIO_BYTES)) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()),
    ):
        await handle_video_note(message, bot)

    mock_extract.assert_awaited_once_with(_VIDEO_BYTES)


# ---------------------------------------------------------------------------
# Лимит/gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_limit_true_proceeds():
    """enforce_limit → True: обработка продолжается, extract_audio вызывается."""
    from handlers.video import handle_video

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.video.extract_audio", new=AsyncMock(return_value=_AUDIO_BYTES)) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()),
    ):
        await handle_video(message, bot)

    mock_extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_limit_false_stops_processing():
    """enforce_limit → False: обработка прерывается, extract_audio не вызывается."""
    from handlers.video import handle_video

    message = _make_message()
    bot = _make_bot()

    with (
        patch("handlers.video.enforce_limit", new=AsyncMock(return_value=False)),
        patch("handlers.video.extract_audio", new=AsyncMock()) as mock_extract,
        patch("handlers.video.process_audio", new=AsyncMock()) as mock_process,
    ):
        await handle_video(message, bot)

    mock_extract.assert_not_awaited()
    mock_process.assert_not_awaited()
    message.answer.assert_not_awaited()
