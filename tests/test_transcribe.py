import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_segment(text: str):
    seg = SimpleNamespace(text=text)
    return seg


@pytest.mark.asyncio
async def test_transcribe_returns_joined_segments():
    """Т-1: сервис корректно склеивает сегменты и возвращает str."""
    # faster-whisper включает ведущий пробел в text сегмента, сервис конкатенирует без разделителя
    segments = [_make_mock_segment("Hello"), _make_mock_segment(" world")]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(segments), MagicMock())

    with patch("services.transcribe._get_model", return_value=mock_model):
        import services.transcribe as svc
        result = await svc.transcribe(b"fake_audio")

    assert isinstance(result, str)
    assert result == "Hello world"
    mock_model.transcribe.assert_called_once()
    assert "language" not in mock_model.transcribe.call_args.kwargs


@pytest.mark.asyncio
async def test_transcribe_empty_segments_returns_empty_str():
    """Т-2: когда сегментов нет, сервис возвращает пустую строку без исключения."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MagicMock())

    with patch("services.transcribe._get_model", return_value=mock_model):
        import services.transcribe as svc
        result = await svc.transcribe(b"silence")

    assert isinstance(result, str)
    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_whitespace_only_segments_returns_stripped():
    """Т-2: сегменты из одних пробелов — результат пуст после strip."""
    segments = [_make_mock_segment("   "), _make_mock_segment("  ")]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(segments), MagicMock())

    with patch("services.transcribe._get_model", return_value=mock_model):
        import services.transcribe as svc
        result = await svc.transcribe(b"noise")

    assert isinstance(result, str)
    assert not result.strip()


@pytest.mark.asyncio
async def test_transcribe_passes_file_like_not_raw_bytes():
    """Регрессия: faster-whisper/av требует path или file-like с read();
    голые bytes дают 'File object has no read() method'. Сервис обязан
    оборачивать байты в file-like объект."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MagicMock())

    with patch("services.transcribe._get_model", return_value=mock_model):
        import services.transcribe as svc
        await svc.transcribe(b"\x00\x01raw_audio")

    passed = mock_model.transcribe.call_args.args[0]
    assert not isinstance(passed, (bytes, bytearray)), "в transcribe ушли сырые bytes"
    assert hasattr(passed, "read"), "аргумент не файлоподобный (нет read())"
    assert passed.read() == b"\x00\x01raw_audio"


def test_transcribe_uses_singleton_not_direct_instantiation():
    """Т-4: _transcribe_sync получает модель через _get_model(), а не напрямую через WhisperModel.

    Это гарантирует, что новый экземпляр модели (и потенциальное сетевое скачивание)
    не создаётся при каждом вызове транскрипции.
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        pytest.skip("faster-whisper не установлен в текущей среде")

    instantiation_calls = []

    def spy_WhisperModel(*args, **kwargs):
        instantiation_calls.append((args, kwargs))
        raise AssertionError("WhisperModel не должен инстанцироваться вне _get_model()")

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MagicMock())

    import services.transcribe as svc
    with patch("services.transcribe._get_model", return_value=mock_model):
        with patch("services.transcribe.WhisperModel", side_effect=spy_WhisperModel):
            svc._transcribe_sync(b"data")

    assert not instantiation_calls


def test_hf_home_env_configured():
    """Т-4: проверяем что HF_HOME задан через ENV в Dockerfile (offline-гарантия)."""
    dockerfile_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "Dockerfile"
    )
    with open(dockerfile_path, encoding="utf-8") as f:
        content = f.read()
    assert "HF_HOME=/opt/models" in content, "HF_HOME не задан в Dockerfile"
    assert "HF_HUB_OFFLINE=1" in content, "HF_HUB_OFFLINE не задан в Dockerfile"
    assert "TRANSFORMERS_OFFLINE=1" in content, "TRANSFORMERS_OFFLINE не задан в Dockerfile"
