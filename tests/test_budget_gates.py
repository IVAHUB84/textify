"""Тесты гейтов бюджета в transcribe/structure/llm."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Задача 2: гейт в transcribe.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcribe_cf_branch_consumes_budget():
    """CF-ветка transcribe(): allow=True → consume вызван, CF вызван."""
    pytest.importorskip("faster_whisper")

    audio = b"x" * 100

    with (
        patch("services.transcribe.cf_budget_allow", new=AsyncMock(return_value=True)) as mock_allow,
        patch("services.transcribe.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.transcribe._transcribe_cloudflare", new=AsyncMock(return_value="text")) as mock_cf,
        patch.dict("os.environ", {
            "ASR_PROVIDER": "cloudflare",
            "CF_ACCOUNT_ID": "acc",
            "CF_API_TOKEN": "tok",
        }),
    ):
        from services.transcribe import transcribe
        result = await transcribe(audio)

    mock_allow.assert_awaited_once()
    mock_consume.assert_awaited_once()
    mock_cf.assert_awaited_once()
    assert result == "text"


@pytest.mark.asyncio
async def test_transcribe_cf_budget_exhausted_degrades_to_local():
    """CF-ветка transcribe(): allow=False → _transcribe_local вызван, CF НЕ вызван."""
    pytest.importorskip("faster_whisper")

    audio = b"x" * 100

    with (
        patch("services.transcribe.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.transcribe.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.transcribe._transcribe_cloudflare", new=AsyncMock()) as mock_cf,
        patch("services.transcribe._transcribe_local", new=AsyncMock(return_value="local text")) as mock_local,
        patch.dict("os.environ", {
            "ASR_PROVIDER": "cloudflare",
            "CF_ACCOUNT_ID": "acc",
            "CF_API_TOKEN": "tok",
        }),
    ):
        from services.transcribe import transcribe
        result = await transcribe(audio)

    mock_consume.assert_not_awaited()
    mock_cf.assert_not_awaited()
    mock_local.assert_awaited_once()
    assert result == "local text"


@pytest.mark.asyncio
async def test_transcribe_local_provider_no_consume():
    """ASR_PROVIDER=local → consume НЕ вызван."""
    pytest.importorskip("faster_whisper")

    audio = b"x" * 100

    with (
        patch("services.transcribe.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.transcribe._transcribe_local", new=AsyncMock(return_value="local")) as mock_local,
        patch.dict("os.environ", {"ASR_PROVIDER": "local"}),
    ):
        from services.transcribe import transcribe
        result = await transcribe(audio)

    mock_consume.assert_not_awaited()
    mock_local.assert_awaited_once()
    assert result == "local"


@pytest.mark.asyncio
async def test_transcribe_cf_budget_exhausted_warning_logged(caplog):
    """При исчерпании бюджета ASR в логах — warning о деградации."""
    pytest.importorskip("faster_whisper")

    import logging
    audio = b"x" * 100

    with (
        patch("services.transcribe.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.transcribe._transcribe_local", new=AsyncMock(return_value="local")),
        patch.dict("os.environ", {
            "ASR_PROVIDER": "cloudflare",
            "CF_ACCOUNT_ID": "acc",
            "CF_API_TOKEN": "tok",
        }),
        caplog.at_level(logging.WARNING, logger="services.transcribe"),
    ):
        from services.transcribe import transcribe
        await transcribe(audio)

    assert any("budget" in r.message.lower() or "деградац" in r.message.lower() or "degrading" in r.message.lower()
               for r in caplog.records)


# ---------------------------------------------------------------------------
# Задача 3: гейт в structure.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_structure_cf_budget_allows_consume_called():
    """CF-провайдер, allow=True → consume вызван."""
    with (
        patch("services.structure.cf_budget_allow", new=AsyncMock(return_value=True)) as mock_allow,
        patch("services.structure.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.structure._build_provider") as mock_build,
        patch("services.structure.httpx.AsyncClient") as mock_client_cls,
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        fake_provider.complete = AsyncMock(return_value="structured")
        mock_build.return_value = fake_provider

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.structure import structure_text
        result = await structure_text("raw")

    mock_allow.assert_awaited_once()
    mock_consume.assert_awaited_once()
    assert result == "structured"


@pytest.mark.asyncio
async def test_structure_cf_budget_exhausted_returns_raw():
    """CF-провайдер, allow=False → возвращается raw_text, consume НЕ вызван."""
    with (
        patch("services.structure.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.structure.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.structure._build_provider") as mock_build,
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        mock_build.return_value = fake_provider

        from services.structure import structure_text
        result = await structure_text("raw text")

    mock_consume.assert_not_awaited()
    assert result == "raw text"


@pytest.mark.asyncio
async def test_structure_groq_no_budget_consume():
    """Groq-провайдер → consume CF НЕ вызван."""
    with (
        patch("services.structure.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.structure._build_provider") as mock_build,
        patch("services.structure.httpx.AsyncClient") as mock_client_cls,
    ):
        from services.structure import _GroqProvider
        fake_provider = MagicMock(spec=_GroqProvider)
        fake_provider.complete = AsyncMock(return_value="groq result")
        mock_build.return_value = fake_provider

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.structure import structure_text
        await structure_text("some text")

    mock_consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_cf_exhausted_warning_logged(caplog):
    """При исчерпании бюджета структурирования — warning в логах."""
    import logging

    with (
        patch("services.structure.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.structure._build_provider") as mock_build,
        caplog.at_level(logging.WARNING, logger="services.structure"),
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        mock_build.return_value = fake_provider

        from services.structure import structure_text
        await structure_text("raw")

    assert any("budget" in r.message.lower() or "деградац" in r.message.lower() or "degrading" in r.message.lower()
               for r in caplog.records)


# ---------------------------------------------------------------------------
# Задача 4: гейт в llm.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_cf_budget_allows_consume_called():
    """summarize, CF-провайдер, allow=True → consume вызван, результат — строка."""
    with (
        patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=True)),
        patch("services.llm.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.llm.build_provider") as mock_build,
        patch("services.llm.httpx.AsyncClient") as mock_client_cls,
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        fake_provider.complete = AsyncMock(return_value="summary result")
        mock_build.return_value = fake_provider

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.llm import summarize
        result = await summarize("some text")

    mock_consume.assert_awaited_once()
    assert result == "summary result"


@pytest.mark.asyncio
async def test_summarize_cf_budget_exhausted_returns_sentinel():
    """summarize, CF-провайдер, allow=False → BUDGET_EXCEEDED."""
    with (
        patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.llm.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.llm.build_provider") as mock_build,
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        mock_build.return_value = fake_provider

        from services.sentinel import BUDGET_EXCEEDED
        from services.llm import summarize
        result = await summarize("some text")

    mock_consume.assert_not_awaited()
    assert result is BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_summarize_groq_no_consume():
    """summarize, Groq-провайдер → consume CF НЕ вызван."""
    with (
        patch("services.llm.cf_budget_consume", new=AsyncMock()) as mock_consume,
        patch("services.llm.build_provider") as mock_build,
        patch("services.llm.httpx.AsyncClient") as mock_client_cls,
    ):
        from services.structure import _GroqProvider
        fake_provider = MagicMock(spec=_GroqProvider)
        fake_provider.complete = AsyncMock(return_value="groq summary")
        mock_build.return_value = fake_provider

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.llm import summarize
        await summarize("some text")

    mock_consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_summarize_cf_exhausted_warning_logged(caplog):
    """При исчерпании бюджета summarize — warning в логах."""
    import logging

    with (
        patch("services.llm.cf_budget_allow", new=AsyncMock(return_value=False)),
        patch("services.llm.build_provider") as mock_build,
        caplog.at_level(logging.WARNING, logger="services.llm"),
    ):
        from services.structure import _CloudflareProvider
        fake_provider = MagicMock(spec=_CloudflareProvider)
        mock_build.return_value = fake_provider

        from services.llm import summarize
        await summarize("text")

    assert any("budget" in r.message.lower() for r in caplog.records)


