"""Тесты services/llm.py: summarize, summarize_gist."""
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
# translate и extract_tasks присутствуют в модуле; старые хелперы — нет
# ---------------------------------------------------------------------------


def test_translate_in_module():
    import services.llm as llm
    assert hasattr(llm, "translate")
    assert hasattr(llm, "extract_tasks")


def test_translate_system_in_module():
    import services.llm as llm
    assert hasattr(llm, "_TRANSLATE_SYSTEM")
    assert hasattr(llm, "_TASKS_SYSTEM")


def test_has_cyrillic_not_in_module():
    import services.llm as llm
    assert not hasattr(llm, "_has_cyrillic"), "_has_cyrillic должна быть удалена"


def test_target_language_not_in_module():
    import services.llm as llm
    assert not hasattr(llm, "_target_language"), "_target_language должна быть удалена"


def test_all_contains_summarize_gist():
    import services.llm as llm
    assert "summarize_gist" in llm.__all__


def test_all_contains_translate_and_tasks():
    import services.llm as llm
    assert "translate" in llm.__all__
    assert "extract_tasks" in llm.__all__


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
# Сбои CF — summarize возвращает None, исключение не пробрасывается
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


# ---------------------------------------------------------------------------
# summarize_gist — успешный ответ
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_gist_cf_success_returns_text():
    """Мок CF → summarize_gist возвращает строку сути."""
    mock_post = AsyncMock(return_value=_make_cf_response("Краткая суть текста."))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize_gist("Длинный текст.")

    assert result == "Краткая суть текста."


@pytest.mark.asyncio
async def test_summarize_gist_returns_none_on_network_error():
    """httpx.ConnectError → summarize_gist возвращает None."""
    mock_post = AsyncMock(side_effect=httpx.ConnectError("DNS failed"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize_gist("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_gist_returns_none_on_empty_response():
    """Пустой ответ LLM → summarize_gist возвращает None."""
    mock_post = AsyncMock(return_value=_make_cf_response(""))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize_gist("текст")

    assert result is None


@pytest.mark.asyncio
async def test_summarize_gist_budget_exceeded():
    """Исчерпан CF-бюджет → summarize_gist возвращает BUDGET_EXCEEDED."""
    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=False)):
            result = await llm.summarize_gist("текст")

    from services.sentinel import BUDGET_EXCEEDED
    assert result is BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_summarize_gist_no_provider_returns_none():
    """Нет CF-кредов → summarize_gist возвращает None."""
    env = {"LLM_PROVIDER": "cloudflare", "CF_ACCOUNT_ID": "", "CF_API_TOKEN": ""}
    mock_post = AsyncMock()

    with patch.dict("os.environ", env, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.summarize_gist("текст")

    assert result is None
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_summarize_gist_truncates_long_input():
    """Длинный вход усекается до MAX_INPUT_CHARS."""
    mock_post = AsyncMock(return_value=_make_cf_response("суть"))
    long_text = "y" * 10000

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.summarize_gist(long_text)

    body = mp.call_args.kwargs.get("json", {})
    user_content = [m["content"] for m in body["messages"] if m["role"] == "user"][-1]
    assert ("y" * llm.MAX_INPUT_CHARS) in user_content
    assert ("y" * (llm.MAX_INPUT_CHARS + 1)) not in user_content


# ---------------------------------------------------------------------------
# translate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_cf_success_returns_text():
    mock_post = AsyncMock(return_value=_make_cf_response("Hello world"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.translate("Привет мир")

    assert result == "Hello world"


@pytest.mark.asyncio
async def test_translate_includes_fewshot_examples():
    """translate отправляет few-shot (несколько user/assistant пар до основного текста)."""
    mock_post = AsyncMock(return_value=_make_cf_response("ok"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.translate("текст")

    messages = mp.call_args.kwargs["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert sum(1 for m in messages if m["role"] == "assistant") >= 2


@pytest.mark.asyncio
async def test_translate_budget_exceeded():
    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=False)):
            result = await llm.translate("текст")

    assert result is llm.BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_translate_returns_none_on_network_error():
    mock_post = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.translate("текст")

    assert result is None


def test_translate_target_detection():
    """Направление перевода берётся из алфавита: кириллица → на английский, латиница → на русский."""
    import services.llm as llm
    importlib.reload(llm)
    assert llm._translate_target("Какие планы на завтра?") == "английский"
    assert llm._translate_target("What are the plans for tomorrow?") == "русский"
    assert llm._translate_target("Сколько стоит доставка?") == "английский"


@pytest.mark.asyncio
async def test_translate_russian_input_targets_english():
    """Русский вход → системный промпт указывает цель «английский»."""
    mock_post = AsyncMock(return_value=_make_cf_response("ok"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.translate("Какие у нас планы на завтра? Когда созвон?")

    messages = mp.call_args.kwargs["json"]["messages"]
    assert "английский" in messages[0]["content"]
    assert "русский" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_translate_english_input_targets_russian():
    """Английский вход → системный промпт указывает цель «русский»."""
    mock_post = AsyncMock(return_value=_make_cf_response("ok"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.translate("How much is the delivery and when will it arrive?")

    messages = mp.call_args.kwargs["json"]["messages"]
    assert "русский" in messages[0]["content"]


# ---------------------------------------------------------------------------
# extract_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_tasks_cf_success_returns_text():
    mock_post = AsyncMock(return_value=_make_cf_response("- Позвонить подрядчику"))

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post):
            result = await llm.extract_tasks("надо позвонить подрядчику")

    assert result == "- Позвонить подрядчику"


@pytest.mark.asyncio
async def test_extract_tasks_budget_exceeded():
    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=False)):
            result = await llm.extract_tasks("текст")

    assert result is llm.BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_extract_tasks_truncates_long_input():
    mock_post = AsyncMock(return_value=_make_cf_response("- задача"))
    long_text = "z" * 10000

    with patch.dict("os.environ", _CF_ENV, clear=False):
        import services.llm as llm
        importlib.reload(llm)
        with patch.object(httpx.AsyncClient, "post", mock_post) as mp:
            await llm.extract_tasks(long_text)

    body = mp.call_args.kwargs.get("json", {})
    user_content = [m["content"] for m in body["messages"] if m["role"] == "user"][-1]
    assert ("z" * llm.MAX_INPUT_CHARS) in user_content
    assert ("z" * (llm.MAX_INPUT_CHARS + 1)) not in user_content
