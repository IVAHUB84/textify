import importlib
import types
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


def _make_groq_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_structure_text_cloudflare_success():
    """Успешный запрос к Cloudflare: возвращает result.response, запрос идёт на CF-эндпоинт."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc123",
        "CF_API_TOKEN": "tok456",
        "CF_MODEL": "@cf/meta/llama-3.1-8b-instruct",
    }
    mock_post = AsyncMock(return_value=_make_cf_response("## Заголовок\n- пункт 1"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("Привет мир")

    assert result == "## Заголовок\n- пункт 1"
    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert "cloudflare.com" in url
    assert "acc123" in url
    headers = call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer tok456"
    body = call_args.kwargs.get("json", {})
    messages = body.get("messages", [])
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


@pytest.mark.asyncio
async def test_structure_text_fallback_on_network_error():
    """Сетевая ошибка → фолбэк на исходный сырой текст, исключение не пробрасывается."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc123",
        "CF_API_TOKEN": "tok456",
    }
    mock_post = AsyncMock(side_effect=httpx.ConnectError("DNS failed"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("raw text")

    assert result == "raw text"


@pytest.mark.asyncio
async def test_structure_text_fallback_on_timeout():
    """Таймаут → фолбэк на исходный сырой текст."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc123",
        "CF_API_TOKEN": "tok456",
    }
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("raw text")

    assert result == "raw text"


@pytest.mark.asyncio
async def test_structure_text_fallback_on_5xx():
    """HTTP 5xx → фолбэк на исходный сырой текст."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc123",
        "CF_API_TOKEN": "tok456",
    }
    bad_resp = _make_cf_response("", status_code=500)
    mock_post = AsyncMock(return_value=bad_resp)

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("raw text")

    assert result == "raw text"


@pytest.mark.asyncio
async def test_structure_text_fallback_on_empty_response():
    """Пустой result.response → фолбэк на исходный сырой текст."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc123",
        "CF_API_TOKEN": "tok456",
    }
    mock_post = AsyncMock(return_value=_make_cf_response(""))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("raw text")

    assert result == "raw text"


@pytest.mark.asyncio
async def test_structure_text_fallback_no_cf_credentials():
    """Отсутствие CF_ACCOUNT_ID/CF_API_TOKEN → фолбэк без падения, LLM не вызывается."""
    env = {"LLM_PROVIDER": "cloudflare", "CF_ACCOUNT_ID": "", "CF_API_TOKEN": ""}
    mock_post = AsyncMock()

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("raw text")

    assert result == "raw text"
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_structure_text_groq_provider_selected():
    """При LLM_PROVIDER=groq используется Groq-ветка (другой URL)."""
    env = {
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "groq-key",
        "GROQ_MODEL": "llama3-8b-8192",
    }
    mock_post = AsyncMock(return_value=_make_groq_response("## Groq result"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text("some text")

    assert result == "## Groq result"
    call_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "groq.com" in call_url
    assert "cloudflare.com" not in call_url


@pytest.mark.asyncio
async def test_structure_text_default_provider_is_cloudflare():
    """При незаданном LLM_PROVIDER используется Cloudflare (дефолт)."""
    env = {
        "CF_ACCOUNT_ID": "acc",
        "CF_API_TOKEN": "tok",
    }
    # Убираем LLM_PROVIDER из окружения если есть
    import os
    saved = os.environ.pop("LLM_PROVIDER", None)
    mock_post = AsyncMock(return_value=_make_cf_response("## ok"))

    try:
        with patch.dict("os.environ", env, clear=False):
            import services.structure as svc
            importlib.reload(svc)
            with patch.object(httpx.AsyncClient, "post", mock_post):
                result = await svc.structure_text("text")
    finally:
        if saved is not None:
            os.environ["LLM_PROVIDER"] = saved

    assert result == "## ok"
    call_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "cloudflare.com" in call_url


@pytest.mark.asyncio
async def test_structure_text_truncates_long_input():
    """Длинный вход усекается в запросе, но фолбэк возвращает полный исходный текст."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc",
        "CF_API_TOKEN": "tok",
    }
    long_text = "x" * 10000
    mock_post = AsyncMock(side_effect=httpx.ConnectError("fail"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await svc.structure_text(long_text)

    assert result == long_text
    assert len(result) == 10000


@pytest.mark.asyncio
async def test_structure_text_truncates_long_input_sent_to_provider():
    """В запрос к провайдеру уходит текст не длиннее порога (~8000 симв.)."""
    env = {
        "LLM_PROVIDER": "cloudflare",
        "CF_ACCOUNT_ID": "acc",
        "CF_API_TOKEN": "tok",
    }
    long_text = "a" * 10000
    mock_post = AsyncMock(return_value=_make_cf_response("## ok"))

    with patch.dict("os.environ", env, clear=False):
        import services.structure as svc
        importlib.reload(svc)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            await svc.structure_text(long_text)

    body = mock_post.call_args.kwargs.get("json", {})
    user_content = next(
        m["content"] for m in body["messages"] if m["role"] == "user"
    )
    assert len(user_content) <= svc._MAX_INPUT_CHARS
    assert len(user_content) < 10000


def test_structure_module_does_not_import_aiogram():
    """services/structure.py не импортирует aiogram."""
    import services.structure as svc
    importlib.reload(svc)
    # Проверяем через sys.modules что сам модуль не тянет aiogram в свои globals
    module_globals = vars(svc)
    aiogram_names = [k for k, v in module_globals.items() if
                     isinstance(v, types.ModuleType) and "aiogram" in v.__name__]
    assert not aiogram_names, f"aiogram найден в globals structure.py: {aiogram_names}"


def test_structure_text_is_async():
    """structure_text — корутинная функция (async def)."""
    import inspect
    import services.structure as svc
    assert inspect.iscoroutinefunction(svc.structure_text)


def test_structure_text_uses_httpx_async_client():
    """structure_text использует httpx.AsyncClient, а не requests или asyncio.to_thread."""
    import inspect
    import services.structure as svc
    source = inspect.getsource(svc.structure_text)
    assert "AsyncClient" in source
    assert "to_thread" not in source
