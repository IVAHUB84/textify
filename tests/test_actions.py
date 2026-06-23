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
    cache_mod._ts_cache.clear()
    yield
    cache_mod._cache.clear()
    cache_mod._ts_cache.clear()


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


def test_actions_keyboard_progressive_has_four_buttons():
    """actions_keyboard(True) → act:full, act:sum, act:tr, act:task."""
    from aiogram.types import InlineKeyboardMarkup

    kb = actions_keyboard(True)
    assert isinstance(kb, InlineKeyboardMarkup)
    data_values = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert data_values == {"act:full", "act:sum", "act:tr", "act:task"}


def test_actions_keyboard_non_progressive_has_three_buttons():
    """actions_keyboard(False) → act:sum, act:tr, act:task; первая — act:sum."""
    kb = actions_keyboard(False)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    data_values = {btn.callback_data for btn in buttons}
    assert data_values == {"act:sum", "act:tr", "act:task"}
    assert buttons[0].callback_data == "act:sum"


def test_actions_keyboard_timestamps_button_optional():
    """with_timestamps=True добавляет act:ts; по умолчанию его нет."""
    assert "act:ts" not in {
        btn.callback_data for row in actions_keyboard(True).inline_keyboard for btn in row
    }
    for progressive in (True, False):
        data_values = {
            btn.callback_data
            for row in actions_keyboard(progressive, with_timestamps=True).inline_keyboard
            for btn in row
        }
        assert "act:ts" in data_values


def test_actions_keyboard_callback_data_within_64_bytes():
    """callback_data кнопок ≤ 64 байт во всех режимах."""
    for progressive in (True, False):
        for with_ts in (True, False):
            kb = actions_keyboard(progressive, with_timestamps=with_ts)
            for row in kb.inline_keyboard:
                for btn in row:
                    assert btn.callback_data is not None
                    assert len(btn.callback_data.encode("utf-8")) <= 64


def test_actions_keyboard_default_is_non_progressive():
    """actions_keyboard() без аргумента → набор non-progressive (act:sum первая)."""
    kb = actions_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert buttons[0].callback_data == "act:sum"
    assert "act:full" not in {btn.callback_data for btn in buttons}


# ---------------------------------------------------------------------------
# handle_translate / act:tr — присутствуют в модуле
# ---------------------------------------------------------------------------


def test_handle_translate_in_module():
    """handle_translate экспортируется из handlers/actions."""
    import handlers.actions as mod
    assert hasattr(mod, "handle_translate")


def test_act_tr_in_module():
    """_CB_TRANSLATE / act:tr присутствует в handlers/actions."""
    import handlers.actions as mod
    assert mod._CB_TRANSLATE == "act:tr"


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


# ---------------------------------------------------------------------------
# act:tr — перевод
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_translate_cache_hit_calls_translate():
    """act:tr при кэш-хите → translate вызывается с исходным текстом, send_result без markup."""
    from handlers.actions import handle_translate

    callback = _make_callback(message_id=600)
    cache_mod.put(12345, 600, "исходный текст")

    with (
        patch("handlers.actions.translate", new=AsyncMock(return_value="translated")) as mock_tr,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_tr.assert_awaited_once_with("исходный текст")
    mock_send.assert_awaited_once()
    _, kwargs = mock_send.await_args
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_handle_translate_cache_miss_no_llm():
    """act:tr при пустом кэше → translate не вызывается, alert."""
    from handlers.actions import handle_translate

    callback = _make_callback(message_id=601)

    with (
        patch("handlers.actions.translate", new=AsyncMock()) as mock_tr,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_tr.assert_not_awaited()
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_translate_budget_exceeded_sends_service_message():
    """act:tr при BUDGET_EXCEEDED → message.answer с понятным сообщением."""
    from handlers.actions import handle_translate
    from services.llm import BUDGET_EXCEEDED

    callback = _make_callback(message_id=602)
    cache_mod.put(12345, 602, "текст")

    with (
        patch("handlers.actions.translate", new=AsyncMock(return_value=BUDGET_EXCEEDED)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_translate(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# act:task — задачи
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_tasks_cache_hit_calls_extract_tasks():
    """act:task при кэш-хите → extract_tasks вызывается, send_result без markup."""
    from handlers.actions import handle_tasks

    callback = _make_callback(message_id=700)
    cache_mod.put(12345, 700, "сделать отчёт")

    with (
        patch("handlers.actions.extract_tasks", new=AsyncMock(return_value="- Сделать отчёт")) as mock_tasks,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_tasks(callback)

    mock_tasks.assert_awaited_once_with("сделать отчёт")
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_tasks_none_result_sends_service_message():
    """act:task при None → message.answer с сообщением об ошибке."""
    from handlers.actions import handle_tasks

    callback = _make_callback(message_id=701)
    cache_mod.put(12345, 701, "текст")

    with (
        patch("handlers.actions.extract_tasks", new=AsyncMock(return_value=None)),
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_tasks(callback)

    mock_send.assert_not_awaited()
    callback.message.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# act:ts — тайм-коды (источник — отдельный кэш, без LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_timestamps_cache_hit_sends_result():
    """act:ts при наличии тайм-кодов → send_result с текстом тайм-кодов."""
    from handlers.actions import handle_timestamps

    callback = _make_callback(message_id=800)
    cache_mod.put_timestamps(12345, 800, "[00:00] привет\n[00:05] пока")

    with patch("handlers.actions.send_result", new=AsyncMock()) as mock_send:
        await handle_timestamps(callback)

    mock_send.assert_awaited_once()
    assert mock_send.await_args[0][1] == "[00:00] привет\n[00:05] пока"


@pytest.mark.asyncio
async def test_handle_timestamps_cache_miss_alert():
    """act:ts при отсутствии тайм-кодов → alert, send_result не вызывается."""
    from handlers.actions import handle_timestamps

    callback = _make_callback(message_id=801)

    with patch("handlers.actions.send_result", new=AsyncMock()) as mock_send:
        await handle_timestamps(callback)

    mock_send.assert_not_awaited()
    calls = callback.answer.await_args_list
    alert_calls = [c for c in calls if c[1].get("show_alert") is True]
    assert len(alert_calls) >= 1
