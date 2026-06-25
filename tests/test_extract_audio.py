"""Тесты v1.11.0: extract_audio (services/media.py)."""
import inspect
from io import BytesIO
from unittest.mock import MagicMock, patch

import av
import pytest


# ---------------------------------------------------------------------------
# Синтез реального mini-контейнера с аудиодорожкой (тишина, без сети/ffmpeg)
# ---------------------------------------------------------------------------


def _make_mkv_with_audio() -> bytes:
    """Синтезирует минимальный MKV с аудиодорожкой pcm_s16le через PyAV."""
    buf = BytesIO()
    with av.open(buf, mode="w", format="matroska") as out:
        stream = out.add_stream("pcm_s16le", rate=16000, layout="mono")
        frame = av.AudioFrame(format="s16", layout="mono", samples=160)
        frame.sample_rate = 16000
        frame.pts = 0
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Вспомогательные фабрики для мока av.open (для изолированных unit-тестов)
# ---------------------------------------------------------------------------


def _make_av_stream(stream_type: str) -> MagicMock:
    stream = MagicMock()
    stream.type = stream_type
    return stream


def _make_av_container(streams: list) -> MagicMock:
    container = MagicMock()
    container.streams = streams
    container.__enter__ = MagicMock(return_value=container)
    container.__exit__ = MagicMock(return_value=False)
    container.decode.return_value = iter([])
    return container


# ---------------------------------------------------------------------------
# Тесты на реальных байтах (без моков PyAV) — фиксируют реальную перекодировку
# ---------------------------------------------------------------------------


def test_extract_audio_sync_real_mkv_with_audio_returns_wav():
    """_extract_audio_sync на реальном MKV с аудиодорожкой возвращает WAV-байты (RIFF/WAVE)."""
    from services.media import _extract_audio_sync

    mkv_bytes = _make_mkv_with_audio()
    result = _extract_audio_sync(mkv_bytes)

    assert result is not None
    assert len(result) > 0
    assert result[:4] == b"RIFF", "ожидался WAV-заголовок RIFF"
    assert b"WAVE" in result[:12], "ожидался WAVE-маркер в заголовке"


@pytest.mark.asyncio
async def test_extract_audio_real_mkv_with_audio_returns_wav():
    """extract_audio (async) на реальном MKV с аудиодорожкой возвращает WAV-байты."""
    from services.media import extract_audio

    mkv_bytes = _make_mkv_with_audio()
    result = await extract_audio(mkv_bytes)

    assert result is not None
    assert len(result) > 0
    assert result[:4] == b"RIFF"


def test_extract_audio_sync_garbage_bytes_raises():
    """_extract_audio_sync на битых байтах бросает исключение (не глотает, не возвращает None)."""
    from services.media import _extract_audio_sync

    with pytest.raises(Exception):
        _extract_audio_sync(b"this is not a valid video container")


@pytest.mark.asyncio
async def test_extract_audio_garbage_bytes_raises():
    """extract_audio на битых байтах пробрасывает исключение — хендлер его должен поймать."""
    from services.media import extract_audio

    with pytest.raises(Exception):
        await extract_audio(b"garbage bytes not a video")


# ---------------------------------------------------------------------------
# Unit-тесты с мокингом (изолированные: проверяют логику ветвления)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_audio_no_audio_stream_returns_none():
    """Видео без аудиопотока → None."""
    from services.media import extract_audio

    video_stream = _make_av_stream("video")
    in_container = _make_av_container([video_stream])

    with patch("services.media.av.open", return_value=in_container):
        result = await extract_audio(b"video_bytes")

    assert result is None


@pytest.mark.asyncio
async def test_extract_audio_empty_streams_returns_none():
    """Контейнер без потоков → None."""
    from services.media import extract_audio

    in_container = _make_av_container([])

    with patch("services.media.av.open", return_value=in_container):
        result = await extract_audio(b"video_bytes")

    assert result is None


# ---------------------------------------------------------------------------
# Структурные тесты (async, to_thread, семафор)
# ---------------------------------------------------------------------------


def test_extract_audio_is_async():
    """extract_audio — корутина (async def)."""
    from services.media import extract_audio

    assert inspect.iscoroutinefunction(extract_audio)


def test_extract_audio_sync_is_not_async():
    """_extract_audio_sync — синхронная функция."""
    from services import media as media_mod

    assert not inspect.iscoroutinefunction(media_mod._extract_audio_sync)


def test_extract_audio_calls_to_thread():
    """extract_audio использует asyncio.to_thread."""
    from services import media as media_mod

    src = inspect.getsource(media_mod.extract_audio)
    assert "to_thread" in src


def test_extract_audio_uses_semaphore():
    """extract_audio использует HEAVY_LOCAL_SEMAPHORE."""
    from services import media as media_mod

    src = inspect.getsource(media_mod.extract_audio)
    assert "HEAVY_LOCAL_SEMAPHORE" in src
