"""Тесты v1.1.0: actions/config/metadata/listing."""
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Задача 5: handlers/actions.py — BUDGET_EXCEEDED
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_chat_action_sender():
    sender = MagicMock()
    sender.__aenter__ = AsyncMock(return_value=None)
    sender.__aexit__ = AsyncMock(return_value=False)
    with patch("handlers.actions.ChatActionSender", return_value=sender):
        yield sender


@pytest.fixture(autouse=True)
def clear_cache():
    import services.result_cache as cache_mod
    cache_mod._cache.clear()
    yield
    cache_mod._cache.clear()


def _make_callback(cached_text: str = "Распознанный текст", message_id: int = 6001) -> MagicMock:
    import services.result_cache as cache_mod
    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.message_id = message_id
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 12345
    if cached_text:
        cache_mod.put(12345, message_id, cached_text)
    return callback


@pytest.mark.asyncio
async def test_handle_action_budget_exceeded_message():
    """BUDGET_EXCEEDED → raw_msg.answer с точным текстом о лимите."""
    from services.sentinel import BUDGET_EXCEEDED
    from handlers.actions import handle_summarize

    callback = _make_callback("некий текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=BUDGET_EXCEEDED)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    assert callback.message.answer.await_args[0][0] == (
        "Дневной бесплатный лимит исчерпан, попробуйте завтра."
    )


@pytest.mark.asyncio
async def test_handle_action_none_result_original_message():
    """None → прежнее сообщение «Не удалось выполнить действие. Попробуйте позже.»"""
    from handlers.actions import handle_summarize

    callback = _make_callback("текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    assert callback.message.answer.await_args[0][0] == (
        "Не удалось выполнить действие. Попробуйте позже."
    )


@pytest.mark.asyncio
async def test_handle_action_text_result_calls_send_result():
    """Текстовый результат → send_result вызван."""
    from handlers.actions import handle_summarize

    callback = _make_callback("текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- пункт 1")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_awaited_once()
    assert mock_send.await_args[0][1] == "- пункт 1"


# ---------------------------------------------------------------------------
# Задача 7: config — CF_DAILY_BUDGET
# ---------------------------------------------------------------------------

def _reload_config(monkeypatch, envs: dict) -> object:
    for key, val in envs.items():
        monkeypatch.setenv(key, val)
    if "config" in sys.modules:
        del sys.modules["config"]
    return importlib.import_module("config")


def test_config_cf_daily_budget_default(monkeypatch):
    """Отсутствие CF_DAILY_BUDGET → 300."""
    monkeypatch.setenv("BOT_TOKEN", "tok")
    monkeypatch.delenv("CF_DAILY_BUDGET", raising=False)
    if "config" in sys.modules:
        del sys.modules["config"]
    cfg = importlib.import_module("config")
    assert cfg.config["CF_DAILY_BUDGET"] == 300


def test_config_cf_daily_budget_nonnumeric_defaults(monkeypatch):
    """CF_DAILY_BUDGET=abc → 300 без падения."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "CF_DAILY_BUDGET": "abc"})
    assert module.config["CF_DAILY_BUDGET"] == 300


def test_config_cf_daily_budget_negative_defaults(monkeypatch):
    """CF_DAILY_BUDGET=-5 → 300 без падения."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "CF_DAILY_BUDGET": "-5"})
    assert module.config["CF_DAILY_BUDGET"] == 300


def test_config_cf_daily_budget_zero_defaults(monkeypatch):
    """CF_DAILY_BUDGET=0 → 300 без падения."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "CF_DAILY_BUDGET": "0"})
    assert module.config["CF_DAILY_BUDGET"] == 300


def test_config_cf_daily_budget_valid(monkeypatch):
    """CF_DAILY_BUDGET=100 → 100."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "CF_DAILY_BUDGET": "100"})
    assert module.config["CF_DAILY_BUDGET"] == 100


def test_config_cf_daily_budget_nonnumeric_no_crash(monkeypatch):
    """Нечисловое CF_DAILY_BUDGET не роняет старт."""
    module = _reload_config(monkeypatch, {"BOT_TOKEN": "tok", "CF_DAILY_BUDGET": "notanumber"})
    assert module.config["CF_DAILY_BUDGET"] == 300


# ---------------------------------------------------------------------------
# Задача 6: лимиты метаданных BOT_DESCRIPTION / BOT_SHORT_DESCRIPTION
# ---------------------------------------------------------------------------

def test_bot_description_within_limit():
    """len(BOT_DESCRIPTION) <= 512."""
    from handlers.commands import BOT_DESCRIPTION
    assert len(BOT_DESCRIPTION) <= 512


def test_bot_short_description_within_limit():
    """len(BOT_SHORT_DESCRIPTION) <= 120."""
    from handlers.commands import BOT_SHORT_DESCRIPTION
    assert len(BOT_SHORT_DESCRIPTION) <= 120


def test_bot_description_contains_keywords():
    """BOT_DESCRIPTION содержит ключевые слова транскрипция/OCR/перевод/RU."""
    from handlers.commands import BOT_DESCRIPTION
    text = BOT_DESCRIPTION.lower()
    assert any(kw in text for kw in ("транскрипц", "распознавани", "ocr"))
    assert any(kw in text for kw in ("перевод", "перевест", "ru", "ru↔en", "ru/en"))


def test_bot_short_description_contains_keywords():
    """BOT_SHORT_DESCRIPTION содержит ключевые слова."""
    from handlers.commands import BOT_SHORT_DESCRIPTION
    text = BOT_SHORT_DESCRIPTION.lower()
    assert any(kw in text for kw in ("транскрипц", "ocr", "голос"))


# ---------------------------------------------------------------------------
# Задача 9: docs/listing.md существует
# ---------------------------------------------------------------------------

def test_listing_md_exists():
    """docs/listing.md существует."""
    listing = Path(__file__).parent.parent / "docs" / "listing.md"
    assert listing.exists(), f"docs/listing.md not found at {listing}"


def test_listing_md_has_required_sections():
    """docs/listing.md содержит все обязательные разделы."""
    listing = Path(__file__).parent.parent / "docs" / "listing.md"
    content = listing.read_text(encoding="utf-8")
    for section in ("Название", "Короткое описание", "Полное описание", "Категории", "Теги"):
        assert section in content, f"Раздел '{section}' не найден в listing.md"


# ---------------------------------------------------------------------------
# sentinel BUDGET_EXCEEDED — уникальный объект
# ---------------------------------------------------------------------------

def test_budget_exceeded_is_singleton():
    """BUDGET_EXCEEDED — синглтон."""
    from services.sentinel import BUDGET_EXCEEDED, _BudgetExceededType
    assert BUDGET_EXCEEDED is _BudgetExceededType()


def test_budget_exceeded_is_not_none():
    """BUDGET_EXCEEDED is not None."""
    from services.sentinel import BUDGET_EXCEEDED
    assert BUDGET_EXCEEDED is not None


def test_budget_exceeded_is_not_string():
    """BUDGET_EXCEEDED — не строка."""
    from services.sentinel import BUDGET_EXCEEDED
    assert not isinstance(BUDGET_EXCEEDED, str)


def test_budget_exceeded_accessible_from_llm():
    """BUDGET_EXCEEDED импортируется из services.llm (обратная совместимость)."""
    from services.llm import BUDGET_EXCEEDED as llm_sentinel
    from services.sentinel import BUDGET_EXCEEDED as base_sentinel
    assert llm_sentinel is base_sentinel
