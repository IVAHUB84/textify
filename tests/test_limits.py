"""Тесты лимита на скачивание медиа (>20 МБ)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.limits import MAX_DOWNLOAD_BYTES, is_oversized


def test_is_oversized_none_false():
    assert is_oversized(None) is False


def test_is_oversized_small_false():
    assert is_oversized(1024) is False


def test_is_oversized_at_limit_false():
    assert is_oversized(MAX_DOWNLOAD_BYTES) is False


def test_is_oversized_above_limit_true():
    assert is_oversized(MAX_DOWNLOAD_BYTES + 1) is True


def test_is_oversized_non_int_false():
    """MagicMock/нечисло не считается превышением (и не роняет сравнение)."""
    assert is_oversized(MagicMock()) is False


@pytest.mark.asyncio
async def test_handle_voice_oversized_answers_and_skips_download():
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.voice.file_size = MAX_DOWNLOAD_BYTES + 10
    message.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.audio.process_audio", new=AsyncMock()) as mock_proc:
        await handle_voice(message, bot)

    message.answer.assert_awaited_once()
    bot.download.assert_not_called()
    mock_proc.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_voice_normal_size_downloads():
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.voice.file_size = 1024
    message.answer = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    bot = MagicMock()
    bot.download = fake_download

    with patch("handlers.audio.process_audio", new=AsyncMock()) as mock_proc:
        await handle_voice(message, bot)

    mock_proc.assert_awaited_once()