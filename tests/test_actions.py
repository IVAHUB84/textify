"""Тесты handlers/actions.py: диспетч callback'ов, граничные случаи."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.actions import (
    actions_keyboard,
    handle_summarize,
    handle_translate,
)


def _make_callback(text: str | None = "Распознанный текст") -> MagicMock:
    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.text = text
    callback.message.answer = AsyncMock()
    return callback


def _make_callback_inaccessible() -> MagicMock:
    """callback.message не является Message (InaccessibleMessage или None)."""
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()  # без spec=Message — не пройдёт isinstance
    callback.message.text = "какой-то текст"
    callback.message.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# Диспетч: act:sum вызывает summarize, act:tr вызывает translate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_summarize_calls_summarize_and_send_result():
    """act:sum → summarize вызывается, результат уходит через send_result."""
    callback = _make_callback("Какой-то текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- Пункт 1")) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_sum.assert_awaited_once_with("Какой-то текст")
    mock_send.assert_awaited_once()
    send_args = mock_send.await_args
    assert send_args[0][1] == "- Пункт 1"
    assert send_args[1].get("reply_markup") is None or len(send_args[0]) == 2


@pytest.mark.asyncio
async def test_handle_translate_calls_translate_and_send_result():
    """act:tr → translate вызывается, результат уходит через send_result."""
    callback = _make_callback("Hello world")

    with (
        patch("handlers.actions.translate", new=AsyncMock(return_value="Привет мир")) as mock_tr,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_tr.assert_awaited_once_with("Hello world")
    mock_send.assert_awaited_once()
    send_args = mock_send.await_args
    assert send_args[0][1] == "Привет мир"


@pytest.mark.asyncio
async def test_handle_summarize_answer_called_once_with_gotovlyu():
    """callback.answer("Готовлю…") вызывается ровно один раз на нормальном пути."""
    callback = _make_callback("текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="саммари")),
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Готовлю…"


@pytest.mark.asyncio
async def test_handle_translate_answer_called_once_with_gotovlyu():
    """callback.answer("Готовлю…") вызывается ровно один раз на нормальном пути."""
    callback = _make_callback("текст")

    with (
        patch("handlers.actions.translate", new=AsyncMock(return_value="перевод")),
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_translate(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Готовлю…"


# ---------------------------------------------------------------------------
# send_result при success вызывается БЕЗ reply_markup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_summarize_send_result_without_markup():
    """send_result вызывается без reply_markup (нет цепочки кнопок над производным текстом)."""
    callback = _make_callback("текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- п1\n- п2")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    _, kwargs = mock_send.await_args
    assert kwargs.get("reply_markup") is None


# ---------------------------------------------------------------------------
# Пустой/None текст — LLM не вызывается, служебный ответ
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_text_no_llm_call_summarize():
    """callback.message.text пуст → summarize НЕ вызывается, единственный callback.answer с "Текст недоступен"."""
    callback = _make_callback("")

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_sum.assert_not_awaited()
    mock_send.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Текст недоступен"
    assert callback.answer.await_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_none_text_no_llm_call_summarize():
    """callback.message.text is None → summarize НЕ вызывается, единственный callback.answer с "Текст недоступен"."""
    callback = _make_callback(None)

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)

    mock_sum.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Текст недоступен"


@pytest.mark.asyncio
async def test_empty_text_no_llm_call_translate():
    """callback.message.text пуст → translate НЕ вызывается, единственный callback.answer с "Текст недоступен"."""
    callback = _make_callback("   ")

    with (
        patch("handlers.actions.translate", new=AsyncMock()) as mock_tr,
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_translate(callback)

    mock_tr.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Текст недоступен"


@pytest.mark.asyncio
async def test_none_text_no_crash():
    """None текст → бот не падает."""
    callback = _make_callback(None)

    with (
        patch("handlers.actions.summarize", new=AsyncMock()),
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)


# ---------------------------------------------------------------------------
# InaccessibleMessage / None message → callback.answer("Текст недоступен"), LLM не вызывается
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inaccessible_message_no_llm_no_crash():
    """callback.message не является Message → callback.answer("Текст недоступен") один раз, LLM не вызывается."""
    callback = _make_callback_inaccessible()

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.translate", new=AsyncMock()) as mock_tr,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Текст недоступен"
    assert callback.answer.await_args[1].get("show_alert") is True
    mock_sum.assert_not_awaited()
    mock_tr.assert_not_awaited()
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_none_message_no_llm_no_crash():
    """callback.message is None → callback.answer("Текст недоступен") один раз, LLM не вызывается."""
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = None

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Текст недоступен"
    assert callback.answer.await_args[1].get("show_alert") is True
    mock_sum.assert_not_awaited()
    mock_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Сбой LLM (None) → служебное сообщение, бот не падает, callback.answer вызван один раз
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_llm_failure_sends_service_message():
    """summarize вернул None → message.answer с сообщением об ошибке, бот не падает."""
    callback = _make_callback("некий текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    error_text = callback.message.answer.await_args[0][0]
    assert len(error_text) > 0


@pytest.mark.asyncio
async def test_translate_llm_failure_sends_service_message():
    """translate вернул None → message.answer с сообщением об ошибке."""
    callback = _make_callback("some text")

    with (
        patch("handlers.actions.translate", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_failure_callback_answer_called_once():
    """При сбое LLM callback.answer() вызывается ровно один раз (снятие индикатора), не через callback.answer."""
    callback = _make_callback("текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args[0][0] == "Готовлю…"


# ---------------------------------------------------------------------------
# Фабрика клавиатуры
# ---------------------------------------------------------------------------


def test_actions_keyboard_returns_inline_keyboard():
    """actions_keyboard возвращает InlineKeyboardMarkup с двумя кнопками."""
    from aiogram.types import InlineKeyboardMarkup

    kb = actions_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 2


def test_actions_keyboard_callback_data_within_64_bytes():
    """callback_data кнопок не превышает 64 байта."""
    kb = actions_keyboard()
    for row in kb.inline_keyboard:
        for btn in row:
            assert btn.callback_data is not None
            assert len(btn.callback_data.encode("utf-8")) <= 64


def test_actions_keyboard_has_sum_and_tr():
    """Кнопки клавиатуры содержат act:sum и act:tr."""
    kb = actions_keyboard()
    data_values = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "act:sum" in data_values
    assert "act:tr" in data_values
