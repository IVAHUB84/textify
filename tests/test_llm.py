"""Тесты services/llm.py: summarize, translate, эвристика направления."""
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

httpx = pytest.importorskip("httpx")


def _make_cf_response(response_text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"result": {"response": response_text}}
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
        if status_code >= 400
        else None
    )
    return resp


_CF_ENV = {
    "LLM_PROVIDER": "cloudflare",
    "CF_ACCOUNT_ID": "acc123",
    "CF_API_TOKEN": "tok456",
    "CF_MODEL": "@cf/meta/llama-3.1-8b-instruct",
}


# ---------------------------------------------------------------------------
# Эвристика направления перевода
# ---------------------------------------------------------------------------


def test_has_cyrillic_detects_russian():
    import services.llm as llm
    assert llm._has_cyrillic("Привет мир") is True


def test_has_cyrillic_returns_false_for_latin():
    import services.llm as llm
    assert llm._has_cyrillic("Hello world") is False


def test_target_language_cyrillic_returns_en():
    import services.llm as llm
    assert llm._target_language("Привет мир") == "en"


def test_target_language_latin_returns_ru():
    import services.llm as llm
    assert llm._target_language("Hello world") == "ru"


def test_target_language_empty_string_no_crash():
    import services.llm as llm
    result = llm._target_language("")
    assert result in ("en", "ru")


def test_target_language_whitespace_no_crash():
    import services.llm as llm
    result = llm._target_language("   \n\t  ")
    assert result in ("en", "ru")


# ---------------------------------------------------------------------------
# summarize — успешный ответ CF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_cf_success_returns_text():
    """Мок CF → summarize возвращает текст саммари."""
    mock_post = AsyncMock(return_value=_make_cf_response("- Пункт 1\n- Пункт 2\n- Пункт 3"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("Длинный текст для саммари.")

    assert result == "- Пункт 1\n- Пункт 2\n- Пункт 3"


@pytest.mark.asyncio
async def test_summarize_truncates_long_input():
    """Длинный вход усекается до MAX_INPUT_CHARS перед отправкой в LLM."""
    mock_post = AsyncMock(return_value=_make_cf_response("- summary"))
    long_text = "x" * 10000

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.summarize(long_text)

    body = mp.call_args.kwargs.get("json", {})
    user_content = [m["content"] for m in body["messages"] if m["role"] == "user"][-1]
    assert ("x" * llm.MAX_INPUT_CHARS) in user_content
    assert ("x" * (llm.MAX_INPUT_CHARS + 1)) not in user_content


# ---------------------------------------------------------------------------
# translate — успешный ответ, проверка направления в промпте
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_cf_success_returns_text():
    """Мок CF → translate возвращает перевод."""
    mock_post = AsyncMock(return_value=_make_cf_response("Hello world"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.translate("Привет мир")

    assert result == "Hello world"


@pytest.mark.asyncio
async def test_translate_cyrillic_prompts_english_target():
    """Кириллический текст → в системном промпте целевой язык английский."""
    mock_post = AsyncMock(return_value=_make_cf_response("Hello"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.translate("Привет мир")

    body = mp.call_args.kwargs.get("json", {})
    system_content = next(m["content"] for m in body["messages"] if m["role"] == "system")
    assert "английский" in system_content


@pytest.mark.asyncio
async def test_translate_latin_prompts_russian_target():
    """Латинский текст → в системном промпте целевой язык русский."""
    mock_post = AsyncMock(return_value=_make_cf_response("Привет"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.translate("Hello world")

    body = mp.call_args.kwargs.get("json", {})
    system_content = next(m["content"] for m in body["messages"] if m["role"] == "system")
    assert "русский" in system_content


# ---------------------------------------------------------------------------
# Сбои CF — summarize и translate возвращают None, исключение не пробрасывается
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_returns_none_on_network_error():
    """httpx.ConnectError → summarize возвращает None, исключение не пробрасывается."""
    mock_post = AsyncMock(side_effect=httpx.ConnectError("DNS failed"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_returns_none_on_timeout():
    """Таймаут → summarize возвращает None."""
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_returns_none_on_5xx():
    """HTTP 5xx → summarize возвращает None."""
    mock_post = AsyncMock(return_value=_make_cf_response("", status_code=500))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_returns_none_on_empty_response():
    """Пустой ответ LLM → summarize возвращает None."""
    mock_post = AsyncMock(return_value=_make_cf_response(""))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("текст")

    assert result is None


@pytest.mark.asyncio
async def test_translate_returns_none_on_network_error():
    """httpx.ConnectError → translate возвращает None."""
    mock_post = AsyncMock(side_effect=httpx.ConnectError("DNS failed"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.translate("текст")

    assert result is None


@pytest.mark.asyncio
async def test_translate_returns_none_on_empty_response():
    """Пустой ответ LLM → translate возвращает None."""
    mock_post = AsyncMock(return_value=_make_cf_response("   "))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.translate("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_no_provider_returns_none():
    """Нет CF-кредов → summarize возвращает None, HTTP не вызывается."""
    env = {"LLM_PROVIDER": "cloudflare", "CF_ACCOUNT_ID": "", "CF_API_TOKEN": ""}
    mock_post = AsyncMock()

    with patch.dict("os.environ", env, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize("текст")

    assert result is None
    mock_post.assert_not_called()
