"""Тесты v1.5.0: прогрессивная выдача (audio + image), кэш по message_id."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.result_cache as cache_mod


@pytest.fixture(autouse=True)
def clear_cache():
    cache_mod._cache.clear()
    cache_mod._seg_cache.clear()
    yield
    cache_mod._cache.clear()
    cache_mod._seg_cache.clear()


def _make_sender_mock() -> MagicMock:
    sender = MagicMock()
    sender.__aenter__ = AsyncMock(return_value=None)
    sender.__aexit__ = AsyncMock(return_value=False)
    return sender


_CHAT_ID = 99999


def _make_message(message_id: int = 77) -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    msg.message_id = message_id
    msg.chat = AsyncMock()
    msg.chat.id = _CHAT_ID
    sent = AsyncMock()
    sent.message_id = message_id + 1000
    sent.chat = AsyncMock()
    sent.chat.id = _CHAT_ID
    msg.answer.return_value = sent
    return msg


def _make_bot_with_download(content: bytes = b"fake") -> AsyncMock:
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(content)

    bot.download = fake_download
    return bot


# ---------------------------------------------------------------------------
# handlers/audio.py — progressive=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audio_progressive_sends_preview_with_two_buttons():
    """progressive=True, непустой транскрипт → ответ с клавиатурой из двух кнопок."""
    from handlers.audio import process_audio
    from aiogram.types import InlineKeyboardMarkup

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("текст", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args[1]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
    buttons = [btn for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert len(buttons) == 4


@pytest.mark.asyncio
async def test_audio_long_adds_extras_buttons_and_caches_segments():
    """Длинное аудио (есть сегменты > порога) → кнопки act:ts/act:srt + put_segments."""
    from handlers.audio import process_audio

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()
    segments = [(0.0, 1.0, "начало"), (61.0, 65.0, "конец")]

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("начало конец", segments))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    kwargs = message.answer.await_args[1]
    data_values = {btn.callback_data for row in kwargs["reply_markup"].inline_keyboard for btn in row}
    assert "act:ts" in data_values
    assert "act:srt" in data_values
    sent_id = message.answer.return_value.message_id
    assert cache_mod.get_segments(_CHAT_ID, sent_id) == segments


@pytest.mark.asyncio
async def test_audio_short_no_timestamps_button():
    """Короткое аудио (длительность < порога) → нет act:ts."""
    from handlers.audio import process_audio

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()
    segments = [(0.0, 1.0, "коротко")]

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("коротко", segments))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    kwargs = message.answer.await_args[1]
    data_values = {btn.callback_data for row in kwargs["reply_markup"].inline_keyboard for btn in row}
    assert "act:ts" not in data_values


@pytest.mark.asyncio
async def test_audio_progressive_cache_put_called():
    """progressive=True → result_cache.put вызван с message_id отправленного сообщения и исходным текстом."""
    from handlers.audio import process_audio

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("исходный текст", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "исходный текст"


@pytest.mark.asyncio
async def test_audio_progressive_structure_text_not_called():
    """progressive=True → structure_text НЕ вызывается на этапе первичной выдачи."""
    from handlers.audio import process_audio

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("текст", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value="суть")),
        patch("handlers.audio.structure_text", new=AsyncMock()) as mock_st,
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    mock_st.assert_not_awaited()


@pytest.mark.asyncio
async def test_audio_progressive_gist_budget_exceeded_sends_service_preview():
    """progressive=True + BUDGET_EXCEEDED → служебное превью + кнопки + кэш заполнен."""
    from handlers.audio import process_audio, _GIST_BUDGET_PREVIEW
    from services.sentinel import BUDGET_EXCEEDED

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("исходный текст", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value=BUDGET_EXCEEDED)),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    message.answer.assert_awaited_once()
    preview_text = message.answer.await_args[0][0]
    assert preview_text == _GIST_BUDGET_PREVIEW

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "исходный текст"


@pytest.mark.asyncio
async def test_audio_progressive_gist_none_sends_service_preview():
    """progressive=True + summarize_gist=None → служебное превью + кнопки + кэш заполнен."""
    from handlers.audio import process_audio, _GIST_FAIL_PREVIEW

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("исходный текст", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock(return_value=None)),
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    preview_text = message.answer.await_args[0][0]
    assert preview_text == _GIST_FAIL_PREVIEW

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "исходный текст"


@pytest.mark.asyncio
async def test_audio_progressive_empty_transcript_no_preview_no_cache():
    """progressive=True, пустой транскрипт → NO_SPEECH_MESSAGE, без превью/кнопок/кэша."""
    from handlers.audio import process_audio, NO_SPEECH_MESSAGE

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("", None))),
        patch("handlers.audio.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await process_audio(message, message, bot, b"audio", progressive=True)

    mock_gist.assert_not_awaited()
    message.answer.assert_awaited_once_with(NO_SPEECH_MESSAGE)
    assert len(cache_mod._cache) == 0


@pytest.mark.asyncio
async def test_audio_non_progressive_sends_one_button():
    """progressive=False → клавиатура с одной кнопкой act:sum."""
    from handlers.audio import process_audio
    from aiogram.types import InlineKeyboardMarkup

    message = _make_message()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("текст", None))),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## текст")),
        patch("handlers.audio.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await process_audio(message, message, bot, b"audio", progressive=False)

    mock_gist.assert_not_awaited()
    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args[1]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
    buttons = [btn for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert len(buttons) == 3
    assert buttons[0].callback_data == "act:sum"


# ---------------------------------------------------------------------------
# handlers/image.py — progressive=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_progressive_sends_preview_with_two_buttons():
    """process_photo progressive=True → ответ с клавиатурой из двух кнопок."""
    from handlers.image import process_photo
    from aiogram.types import InlineKeyboardMarkup

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_photo(message, message, bot, progressive=True)

    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args[1]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
    buttons = [btn for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert len(buttons) == 4


@pytest.mark.asyncio
async def test_image_progressive_cache_put_called():
    """process_photo progressive=True → result_cache.put с message_id и исходным текстом."""
    from handlers.image import process_photo

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="исходный текст")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_photo(message, message, bot, progressive=True)

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "исходный текст"


@pytest.mark.asyncio
async def test_image_progressive_structure_text_not_called():
    """process_photo progressive=True → structure_text НЕ вызывается."""
    from handlers.image import process_photo

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
        patch("handlers.image.structure_text", new=AsyncMock()) as mock_st,
    ):
        await process_photo(message, message, bot, progressive=True)

    mock_st.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_progressive_gist_budget_exceeded():
    """process_photo progressive=True + BUDGET_EXCEEDED → служебное превью + кэш."""
    from handlers.image import process_photo, _GIST_BUDGET_PREVIEW
    from services.sentinel import BUDGET_EXCEEDED

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value=BUDGET_EXCEEDED)),
    ):
        await process_photo(message, message, bot, progressive=True)

    preview_text = message.answer.await_args[0][0]
    assert preview_text == _GIST_BUDGET_PREVIEW

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "текст"


@pytest.mark.asyncio
async def test_image_progressive_empty_ocr_no_preview_no_cache():
    """process_photo progressive=True + пустой OCR → NO_TEXT_MESSAGE, без превью/кэша."""
    from handlers.image import process_photo, NO_TEXT_MESSAGE

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
        patch("handlers.image.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await process_photo(message, message, bot, progressive=True)

    mock_gist.assert_not_awaited()
    message.answer.assert_awaited_once_with(NO_TEXT_MESSAGE)
    assert len(cache_mod._cache) == 0


@pytest.mark.asyncio
async def test_image_document_progressive_cache_put_called():
    """process_image_document progressive=True → result_cache.put с message_id."""
    from handlers.image import process_image_document

    message = _make_message()
    message.document = AsyncMock()
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст документа")),
        patch("handlers.image.summarize_gist", new=AsyncMock(return_value="суть")),
    ):
        await process_image_document(message, message, bot, progressive=True)

    sent_id = message.answer.return_value.message_id
    assert cache_mod.get(_CHAT_ID, sent_id) == "текст документа"


@pytest.mark.asyncio
async def test_image_non_progressive_sends_one_button():
    """process_photo progressive=False → клавиатура с одной кнопкой act:sum."""
    from handlers.image import process_photo
    from aiogram.types import InlineKeyboardMarkup

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = _make_bot_with_download()
    sender_mock = _make_sender_mock()

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## текст")),
        patch("handlers.image.summarize_gist", new=AsyncMock()) as mock_gist,
    ):
        await process_photo(message, message, bot, progressive=False)

    mock_gist.assert_not_awaited()
    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args[1]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
    buttons = [btn for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert len(buttons) == 3
    assert buttons[0].callback_data == "act:sum"
