import base64
import inspect
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

httpx = pytest.importorskip("httpx")

import services.transcribe as svc  # noqa: E402  (after importorskip)

_CF_ENV_VARS = ("ASR_PROVIDER", "CF_ACCOUNT_ID", "CF_API_TOKEN", "CF_WHISPER_MODEL")


@pytest.fixture(autouse=True)
def _clean_asr_env(monkeypatch):
    """Удаляет CF/ASR-переменные из окружения перед каждым тестом и восстанавливает после.

    Без этого тесты локального пути становятся флакающими в окружениях,
    где CF_ACCOUNT_ID/CF_API_TOKEN экспортированы (CI, прод).
    """
    for var in _CF_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


def _make_mock_segment(text: str):
    seg = SimpleNamespace(text=text)
    return seg


def _make_local_mock(segments=None):
    if segments is None:
        segments = [_make_mock_segment("local result")]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(segments), MagicMock())
    return mock_model


def _make_cf_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "result": {
            "text": text,
            "transcription_info": {"language": "ru"},
        }
    }
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
        if status_code >= 400
        else None
    )
    return resp


# ---------------------------------------------------------------------------
# Существующие тесты локального пути
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcribe_returns_joined_segments():
    """Т-1: сервис корректно склеивает сегменты и возвращает str."""
    # faster-whisper включает ведущий пробел в text сегмента, сервис конкатенирует без разделителя
    segments = [_make_mock_segment("Hello"), _make_mock_segment(" world")]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(segments), MagicMock())

    with patch("services.transcribe._get_model", return_value=mock_model):
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


# ---------------------------------------------------------------------------
# Новые тесты: Cloudflare-провайдер и оркестратор
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cf_provider_success(monkeypatch):
    """CF-провайдер успех: правильный URL, заголовок, тело, результат."""
    audio = b"audio_data"
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc123")
    monkeypatch.setenv("CF_API_TOKEN", "tok456")
    monkeypatch.setenv("CF_WHISPER_MODEL", "@cf/openai/whisper-large-v3-turbo")
    mock_post = AsyncMock(return_value=_make_cf_response("распознанный текст"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await svc.transcribe(audio)

    assert result == "распознанный текст"

    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert "accounts/acc123/ai/run/@cf/openai/whisper-large-v3-turbo" in url

    headers = call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer tok456"

    body = call_args.kwargs.get("json", {})
    assert "audio" in body
    assert body["audio"] == base64.b64encode(audio).decode()


@pytest.mark.asyncio
async def test_cf_provider_parses_result_text_not_response(monkeypatch):
    """Результат берётся из result.text, а не из result.response."""
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "result": {
            "text": "правильный текст",
            "response": "неправильный текст",
        }
    }
    mock_post = AsyncMock(return_value=resp)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await svc.transcribe(b"audio")

    assert result == "правильный текст"


@pytest.mark.asyncio
async def test_cf_fallback_on_connect_error(monkeypatch):
    """httpx.ConnectError → фолбэк на локальный путь, исключение не пробрасывается."""
    mock_model = _make_local_mock([_make_mock_segment("local result")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(side_effect=httpx.ConnectError("DNS failed"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local result"
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_cf_fallback_on_timeout(monkeypatch):
    """httpx.TimeoutException → фолбэк на локальный путь, исключение не пробрасывается."""
    mock_model = _make_local_mock([_make_mock_segment("local fallback")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local fallback"
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_cf_fallback_on_http_status_error(monkeypatch):
    """raise_for_status бросает HTTPStatusError (500) → фолбэк на локальный путь."""
    mock_model = _make_local_mock([_make_mock_segment("local after 500")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(return_value=_make_cf_response("", status_code=500))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local after 500"
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_cf_fallback_on_429(monkeypatch):
    """raise_for_status бросает HTTPStatusError (429) → фолбэк на локальный путь."""
    mock_model = _make_local_mock([_make_mock_segment("local after 429")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(return_value=_make_cf_response("", status_code=429))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local after 429"
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_cf_fallback_no_credentials(monkeypatch):
    """ASR_PROVIDER=cloudflare, пустые CF-креды → post не вызван, используется локальный путь."""
    mock_model = _make_local_mock([_make_mock_segment("local no creds")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "")
    monkeypatch.setenv("CF_API_TOKEN", "")
    mock_post = AsyncMock()

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local no creds"
    mock_post.assert_not_called()
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_asr_provider_local_skips_cf(monkeypatch):
    """ASR_PROVIDER=local → post не вызван, используется только локальный путь."""
    mock_model = _make_local_mock([_make_mock_segment("local only")])
    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock()

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(b"audio")

    assert result == "local only"
    mock_post.assert_not_called()
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_default_provider_is_cloudflare(monkeypatch):
    """При незаданном ASR_PROVIDER (с CF-кредами) запрос идёт на CF-эндпоинт."""
    # autouse-фикстура уже удалила ASR_PROVIDER; выставляем только CF-креды
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(return_value=_make_cf_response("default cf"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await svc.transcribe(b"audio")

    assert result == "default cf"
    mock_post.assert_called_once()
    url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "cloudflare.com" in url


@pytest.mark.asyncio
async def test_large_file_uses_local_skips_cf(monkeypatch):
    """len(audio_bytes) > _CF_MAX_AUDIO_BYTES при дефолте → post не вызван, локальный путь."""
    mock_model = _make_local_mock([_make_mock_segment("local large")])
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock()
    big_audio = b"x" * (svc._CF_MAX_AUDIO_BYTES + 1)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("services.transcribe._get_model", return_value=mock_model):
            result = await svc.transcribe(big_audio)

    assert result == "local large"
    mock_post.assert_not_called()
    mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_cf_empty_text_returns_empty_string(monkeypatch):
    """Успешный 2xx ответ с пустым result.text → возвращается '' (не фолбэк).

    Облако ответило корректно, речи нет — это не сбой. Решение про
    'речь не распознана' остаётся в хендлере.
    """
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    mock_post = AsyncMock(return_value=_make_cf_response("   "))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await svc.transcribe(b"silence")

    assert isinstance(result, str)
    assert result == ""


def test_cloudflare_branch_uses_httpx_async_client_not_to_thread():
    """Облачная ветка использует httpx.AsyncClient/await, а не asyncio.to_thread."""
    source = inspect.getsource(svc._transcribe_cloudflare)
    assert "AsyncClient" in source
    assert "to_thread" not in source


def test_cf_whisper_model_env_var_is_independent_from_cf_model(monkeypatch):
    """CF_WHISPER_MODEL и CF_MODEL — разные переменные, не конфликтуют."""
    monkeypatch.setenv("CF_WHISPER_MODEL", "@cf/openai/whisper-large-v3-turbo")
    monkeypatch.setenv("CF_MODEL", "@cf/meta/llama-3.1-8b-instruct")

    cf_whisper = os.environ.get("CF_WHISPER_MODEL")
    cf_model = os.environ.get("CF_MODEL")

    assert cf_whisper != cf_model
    assert cf_whisper == "@cf/openai/whisper-large-v3-turbo"
    assert cf_model == "@cf/meta/llama-3.1-8b-instruct"


@pytest.mark.asyncio
async def test_cf_whisper_model_env_used_in_url(monkeypatch):
    """CF_WHISPER_MODEL из окружения используется в URL запроса к CF."""
    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    monkeypatch.setenv("CF_WHISPER_MODEL", "@cf/openai/whisper-large-v3-turbo")
    mock_post = AsyncMock(return_value=_make_cf_response("ok"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        await svc.transcribe(b"audio")

    url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "@cf/openai/whisper-large-v3-turbo" in url
