"""Тесты handlers/actions.py: клавиатура, callback act:full, callback act:sum."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.result_cache as cache_mod
from handlers.actions import actions_keyboard, handle_full, handle_summarize


@pytest.fixture(autouse=True)
def mock_chat_action_sender():
    sender = MagicMock()
    sender.__aenter__ = AsyncMock(return_value=None)
    sender.__aexit__ = AsyncMock(return_value=False)
    with patch("handlers.actions.ChatActionSender", return_value=sender):
        yield sender


@pytest.fixture(autouse=True)
def clear_cache():
    cache_mod._cache.clear()
    yield
    cache_mod._cache.clear()


def _make_callback(message_id: int = 100) -> MagicMock:
    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.message_id = message_id
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 12345
    return callback


def _make_callback_inaccessible() -> MagicMock:
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock()
    callback.message.message_id = 100
    callback.message.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# Фабрика клавиатуры
# ---------------------------------------------------------------------------


def test_actions_keyboard_progressive_has_two_buttons():
    """actions_keyboard(True) → ровно две кнопки: act:full и act:sum."""
    from aiogram.types import InlineKeyboardMarkup

    kb = actions_keyboard(True)
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 2


def test_actions_keyboard_progressive_has_full_and_sum():
    """actions_keyboard(True) содержит act:full и act:sum."""
    kb = actions_keyboard(True)
    data_values = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "act:full" in data_values
    assert "act:sum" in data_values


def test_actions_keyboard_non_progressive_has_one_button():
    """actions_keyboard(False) → одна кнопка act:sum."""
    kb = actions_keyboard(False)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert buttons[0].callback_data == "act:sum"


def test_actions_keyboard_no_translate_in_progressive():
    """В progressive=True нет act:tr."""
    kb = actions_keyboard(True)
    data_values = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "act:tr" not in data_values


def test_actions_keyboard_no_translate_in_non_progressive():
    """В progressive=False нет act:tr."""
    kb = actions_keyboard(False)
    data_values = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "act:tr" not in data_values


def test_actions_keyboard_callback_data_within_64_bytes():
    """callback_data кнопок ≤ 64 байт в обоих режимах."""
    for progressive in (True, False):
        kb = actions_keyboard(progressive)
        for row in kb.inline_keyboard:
            for btn in row:
                assert btn.callback_data is not None
                assert len(btn.callback_data.encode("utf-8")) <= 64


def test_actions_keyboard_default_is_non_progressive():
    """actions_keyboard() без аргумента → одна кнопка (дефолт False)."""
    kb = actions_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1


# ---------------------------------------------------------------------------
# handle_translate / act:tr — удалены из модуля
# ---------------------------------------------------------------------------


def test_handle_translate_not_in_module():
    """handle_translate не экспортируется из handlers/actions."""
    import handlers.actions as mod
    assert not hasattr(mod, "handle_translate"), "handle_translate должен быть удалён"


def test_act_tr_not_in_module():
    """_CB_TRANSLATE / act:tr отсутствует в handlers/actions."""
    import handlers.actions as mod
    assert not hasattr(mod, "_CB_TRANSLATE"), "_CB_TRANSLATE должен быть удалён"


# ---------------------------------------------------------------------------
# act:full — текст в кэше → structure_text + send_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_full_cache_hit_calls_structure_text():
    """act:full при наличии текста в кэше → structure_text вызывается."""
    callback = _make_callback(message_id=100)
    cache_mod.put(12345, 100, "исходный текст")

    with (
        patch("handlers.actions.structure_text", new=AsyncMock(return_value="## полный")) as mock_st,
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_full(callback)

    mock_st.assert_awaited_once_with("исходный текст")


@pytest.mark.asyncio
async def test_handle_full_cache_hit_send_result_without_markup():
    """act:full при кэш-хите → send_result вызывается без reply_markup."""
    callback = _make_callback(message_id=100)
    cache_mod.put(12345, 100, "текст")

    with (
        patch("handlers.actions.structure_text", new=AsyncMock(return_value="результат")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_full(callback)

    mock_send.assert_awaited_once()
    _, kwargs = mock_send.await_args
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_handle_full_cache_miss_no_llm():
    """act:full при пустом кэше → structure_text не вызывается, callback.answer(show_alert=True)."""
    callback = _make_callback(message_id=999)

    with (
        patch("handlers.actions.structure_text", new=AsyncMock()) as mock_st,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_full(callback)

    mock_st.assert_not_awaited()
    mock_send.assert_not_awaited()
    calls = callback.answer.await_args_list
    alert_calls = [c for c in calls if c[1].get("show_alert") is True]
    assert len(alert_calls) >= 1
    assert alert_calls[-1][0][0] == "Текст недоступен"


@pytest.mark.asyncio
async def test_handle_full_inaccessible_message_no_llm():
    """act:full при не-Message → structure_text не вызывается."""
    callback = _make_callback_inaccessible()

    with (
        patch("handlers.actions.structure_text", new=AsyncMock()) as mock_st,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_full(callback)

    mock_st.assert_not_awaited()
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_full_answer_gotovlyu_first():
    """act:full вызывает callback.answer('Готовлю…') в начале."""
    callback = _make_callback(message_id=100)
    cache_mod.put(12345, 100, "текст")

    with (
        patch("handlers.actions.structure_text", new=AsyncMock(return_value="полный")),
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_full(callback)

    first_call = callback.answer.await_args_list[0]
    assert first_call[0][0] == "Готовлю…"


# ---------------------------------------------------------------------------
# act:sum — источник текста — кэш, а не callback.message.text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_summarize_uses_cache_not_message_text():
    """act:sum берёт текст из кэша (не из callback.message.text)."""
    callback = _make_callback(message_id=200)
    callback.message.text = "другой текст из сообщения"
    cache_mod.put(12345, 200, "исходный текст из кэша")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="саммари")) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)

    mock_sum.assert_awaited_once_with("исходный текст из кэша")


@pytest.mark.asyncio
async def test_handle_summarize_cache_hit_calls_summarize():
    """act:sum при кэш-хите → summarize вызывается с исходным текстом."""
    callback = _make_callback(message_id=300)
    cache_mod.put(12345, 300, "текст для саммари")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- краткий пункт")) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()),
    ):
        await handle_summarize(callback)

    mock_sum.assert_awaited_once_with("текст для саммари")


@pytest.mark.asyncio
async def test_handle_summarize_success_send_result_without_markup():
    """act:sum при успехе → send_result вызывается без reply_markup."""
    callback = _make_callback(message_id=300)
    cache_mod.put(12345, 300, "текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value="саммари")),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_awaited_once()
    _, kwargs = mock_send.await_args
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_handle_summarize_cache_miss_no_llm():
    """act:sum при пустом кэше → summarize не вызывается, callback.answer(show_alert=True)."""
    callback = _make_callback(message_id=9999)

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_sum.assert_not_awaited()
    mock_send.assert_not_awaited()
    calls = callback.answer.await_args_list
    alert_calls = [c for c in calls if c[1].get("show_alert") is True]
    assert len(alert_calls) >= 1
    assert alert_calls[-1][0][0] == "Текст недоступен"


@pytest.mark.asyncio
async def test_handle_summarize_budget_exceeded_sends_service_message():
    """act:sum при BUDGET_EXCEEDED → message.answer с понятным сообщением."""
    callback = _make_callback(message_id=400)
    cache_mod.put(12345, 400, "текст")

    from services.sentinel import BUDGET_EXCEEDED

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=BUDGET_EXCEEDED)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    msg = callback.message.answer.await_args[0][0]
    assert "лимит" in msg.lower() or "завтра" in msg.lower()


@pytest.mark.asyncio
async def test_handle_summarize_none_result_sends_service_message():
    """act:sum при None → message.answer с сообщением об ошибке."""
    callback = _make_callback(message_id=500)
    cache_mod.put(12345, 500, "текст")

    with (
        patch("handlers.actions.summarize", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    msg = callback.message.answer.await_args[0][0]
    assert len(msg) > 0


@pytest.mark.asyncio
async def test_handle_summarize_inaccessible_message_no_llm():
    """act:sum при не-Message → summarize не вызывается."""
    callback = _make_callback_inaccessible()

    with (
        patch("handlers.actions.summarize", new=AsyncMock()) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_sum.assert_not_awaited()
    mock_send.assert_not_awaited()
