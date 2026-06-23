"""Тесты services/reply.py: split_text и send_result."""
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.reply import (
    MAX_MESSAGE_LEN,
    MAX_PARTS,
    PART_DELAY_SEC,
    split_text,
    send_result,
)


# ---------------------------------------------------------------------------
# split_text — чистая функция
# ---------------------------------------------------------------------------


def test_split_text_short_returns_single_part():
    """Короткий текст (len <= MAX_MESSAGE_LEN) — один элемент, равный исходнику."""
    text = "Короткий текст."
    parts = split_text(text)
    assert parts == [text]


def test_split_text_exactly_at_limit_returns_single_part():
    """Текст длиной ровно MAX_MESSAGE_LEN — один элемент."""
    text = "а" * MAX_MESSAGE_LEN
    parts = split_text(text)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_text_one_over_limit_returns_two_parts():
    """Текст длиной MAX_MESSAGE_LEN + 1 → две части, каждая <= MAX_MESSAGE_LEN."""
    word_a = "а" * (MAX_MESSAGE_LEN - 5)
    word_b = "б" * 6
    text = word_a + " " + word_b
    assert len(text) == MAX_MESSAGE_LEN + 2

    parts = split_text(text)
    assert len(parts) == 2
    for part in parts:
        assert len(part) <= MAX_MESSAGE_LEN


def test_split_text_long_all_parts_within_limit():
    """Длинный текст — все части <= MAX_MESSAGE_LEN."""
    paragraph = "Слово другое слово. Ещё предложение!\n"
    text = paragraph * 300
    parts = split_text(text)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= MAX_MESSAGE_LEN


def test_split_text_long_no_content_loss():
    """Конкатенация частей восстанавливает исходный текст точно без потерь и дублей."""
    paragraph = "Первый абзац содержит текст.\n\nВторой абзац тоже.\n"
    text = paragraph * 200
    parts = split_text(text)
    assert "".join(parts) == text


def test_split_text_cuts_on_paragraph_boundary():
    """Разбивка по абзацам (\n\n) — части не начинаются с середины слова."""
    block = "Текст абзаца здесь.\n\n"
    text = block * 300
    parts = split_text(text)
    for part in parts:
        stripped = part.strip()
        if stripped:
            first_char = stripped[0]
            assert first_char.isalpha() or first_char in "«„\""


def test_split_text_does_not_break_words():
    """Ни одна часть не начинается/не заканчивается на полуслово (кроме жёсткого среза)."""
    sentence = "Короткое предложение без длинных слов. "
    text = sentence * 200
    parts = split_text(text)
    for part in parts[:-1]:
        assert not part.endswith("-")
        last_char = part[-1] if part else ""
        assert last_char != "" and (last_char in ".!?\n " or last_char.isalpha())


def test_split_text_hard_cut_no_natural_boundary():
    """Одно «слово» без пробелов длиннее MAX_MESSAGE_LEN — жёсткий срез, без потерь."""
    long_word = "а" * (MAX_MESSAGE_LEN * 3)
    parts = split_text(long_word)
    for part in parts:
        assert len(part) <= MAX_MESSAGE_LEN
    assert "".join(parts) == long_word


def test_split_text_hard_cut_exact_multiple():
    """Строка ровно 2 * MAX_MESSAGE_LEN без границ → ровно 2 части."""
    long_word = "б" * (MAX_MESSAGE_LEN * 2)
    parts = split_text(long_word)
    assert len(parts) == 2
    assert "".join(parts) == long_word
    for part in parts:
        assert len(part) <= MAX_MESSAGE_LEN


def test_split_text_newline_boundary():
    """Разбивка по одиночному \n, если нет \n\n. Содержимое сохраняется точно без потерь."""
    line = "строка текста здесь\n"
    text = line * 250
    parts = split_text(text)
    for part in parts:
        assert len(part) <= MAX_MESSAGE_LEN
    assert "".join(parts) == text


def test_split_text_custom_limit():
    """split_text уважает кастомный limit."""
    text = "abc def ghi jkl mno"
    parts = split_text(text, limit=10)
    for part in parts:
        assert len(part) <= 10
    assert "".join(parts) == text


# ---------------------------------------------------------------------------
# send_result — через мок Message
# ---------------------------------------------------------------------------


def _make_message() -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_send_result_short_single_answer():
    """Короткий текст — ровно один message.answer (HTML), без answer_document и без asyncio.sleep."""
    from aiogram.enums import ParseMode

    message = _make_message()
    text = "Короткий ответ."

    with patch("services.reply.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await send_result(message, text)

    message.answer.assert_awaited_once_with(
        text, reply_markup=None, parse_mode=ParseMode.HTML
    )
    message.answer_document.assert_not_awaited()
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_result_series_calls_answer_for_each_part():
    """Серия частей (<=MAX_PARTS): message.answer вызывается по числу частей."""
    message = _make_message()
    paragraph = "Слово другое предложение здесь.\n\n"
    text = paragraph * 150
    parts = split_text(text)
    assert 1 < len(parts) <= MAX_PARTS, f"Нужно 2..{MAX_PARTS} частей для этого теста, получено {len(parts)}"

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text)

    assert message.answer.await_count == len(parts)
    message.answer_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_result_series_sleeps_between_parts():
    """Серия частей: asyncio.sleep вызывается между соседними частями (len(parts)-1 раз)."""
    message = _make_message()
    paragraph = "Слово другое предложение здесь.\n\n"
    text = paragraph * 150
    parts = split_text(text)
    assert 1 < len(parts) <= MAX_PARTS

    with patch("services.reply.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await send_result(message, text)

    assert mock_sleep.await_count == len(parts) - 1
    for c in mock_sleep.await_args_list:
        assert c == call(PART_DELAY_SEC)


@pytest.mark.asyncio
async def test_send_result_very_long_sends_document():
    """Очень длинный текст (>MAX_PARTS частей) — один answer_document, message.answer не вызывается."""
    message = _make_message()
    paragraph = "Длинный абзац текста для теста разбивки.\n\n"
    text = paragraph * 1000
    parts = split_text(text)
    assert len(parts) > MAX_PARTS, f"Нужно >MAX_PARTS частей, получено {len(parts)}"

    with patch("services.reply.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await send_result(message, text)

    message.answer_document.assert_awaited_once()
    message.answer.assert_not_awaited()
    mock_sleep.assert_not_awaited()

    call_kwargs = message.answer_document.await_args
    assert call_kwargs is not None
    doc_arg = call_kwargs[0][0]
    assert doc_arg.filename == "result.txt"
    assert text.encode("utf-8") == doc_arg.data

    caption = call_kwargs[1].get("caption") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None
    if caption is None:
        caption = message.answer_document.await_args.kwargs.get("caption")
    assert caption == "Результат целиком во вложении."


@pytest.mark.asyncio
async def test_send_result_empty_text_no_calls():
    """Пустой текст — тихая деградация, никаких вызовов."""
    message = _make_message()
    await send_result(message, "")
    message.answer.assert_not_awaited()
    message.answer_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_result_whitespace_text_no_calls():
    """Пробельный текст — тихая деградация."""
    message = _make_message()
    await send_result(message, "   \n\t  ")
    message.answer.assert_not_awaited()
    message.answer_document.assert_not_awaited()


# ---------------------------------------------------------------------------
# reply_markup: только при одиночном сообщении
# ---------------------------------------------------------------------------


def _make_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Кратко", callback_data="act:sum")]
        ]
    )


@pytest.mark.asyncio
async def test_send_result_short_passes_markup_to_answer():
    """Короткий текст + reply_markup → message.answer получает reply_markup."""
    message = _make_message()
    markup = _make_markup()

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, "Короткий текст", reply_markup=markup)

    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args.kwargs
    assert kwargs.get("reply_markup") is markup


@pytest.mark.asyncio
async def test_send_result_series_no_markup():
    """Длинный текст (серия) + reply_markup → части отправляются без markup."""
    message = _make_message()
    markup = _make_markup()
    paragraph = "Слово другое предложение здесь.\n\n"
    text = paragraph * 150
    parts = split_text(text)
    assert 1 < len(parts) <= MAX_PARTS

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text, reply_markup=markup)

    for c in message.answer.await_args_list:
        kwargs = c.kwargs
        assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_send_result_very_long_no_markup():
    """Очень длинный текст (файл) + reply_markup → answer_document без markup."""
    message = _make_message()
    markup = _make_markup()
    paragraph = "Длинный абзац текста для теста разбивки.\n\n"
    text = paragraph * 1000
    parts = split_text(text)
    assert len(parts) > MAX_PARTS

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text, reply_markup=markup)

    message.answer_document.assert_awaited_once()
    doc_kwargs = message.answer_document.await_args.kwargs
    assert doc_kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_send_result_no_markup_arg_defaults_to_none_html():
    """Вызов без reply_markup (дефолт None): один answer с reply_markup=None и parse_mode=HTML."""
    from aiogram.enums import ParseMode

    message = _make_message()

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, "Короткий текст")

    message.answer.assert_awaited_once_with(
        "Короткий текст", reply_markup=None, parse_mode=ParseMode.HTML
    )


@pytest.mark.asyncio
async def test_send_result_converts_markdown_to_html():
    """Markdown (## заголовок, **жирный**, список) конвертируется в Telegram-HTML."""
    message = _make_message()
    text = "## Итог\n- **раз**\n- два"

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, text)

    sent = message.answer.await_args.args[0]
    assert "<b>Итог</b>" in sent
    assert "<b>раз</b>" in sent
    assert "• два" in sent
    assert "##" not in sent
    assert "**" not in sent


@pytest.mark.asyncio
async def test_send_result_falls_back_to_plain_on_bad_request():
    """TelegramBadRequest (невалидная разметка) → повторная отправка plain-текстом."""
    from aiogram.exceptions import TelegramBadRequest

    message = _make_message()
    message.answer = AsyncMock(side_effect=[TelegramBadRequest(method=MagicMock(), message="bad"), AsyncMock()])

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        await send_result(message, "## Текст")

    assert message.answer.await_count == 2
    # второй вызов — без parse_mode, plain исходный текст
    fallback_kwargs = message.answer.await_args.kwargs
    assert "parse_mode" not in fallback_kwargs
    assert message.answer.await_args.args[0] == "## Текст"


# ---------------------------------------------------------------------------
# Регресс служебных сообщений — хендлеры не пропускают заглушки через send_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_text_message_via_direct_answer():
    """NO_TEXT_MESSAGE идёт через прямой message.answer, send_result не вызывается."""
    from unittest.mock import patch, AsyncMock
    from handlers.image import handle_photo, NO_TEXT_MESSAGE

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
        patch("handlers.image.structure_text", new=AsyncMock()),
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_TEXT_MESSAGE)


@pytest.mark.asyncio
async def test_no_speech_message_via_direct_answer():
    """NO_SPEECH_MESSAGE идёт через прямой message.answer, send_result не вызывается."""
    from handlers.audio import handle_voice, NO_SPEECH_MESSAGE

    message = _make_message()
    message.voice = AsyncMock()
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("", None))),
        patch("handlers.audio.structure_text", new=AsyncMock()),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


# ---------------------------------------------------------------------------
# send_result — возврат Message / None (для кэширования по message_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_result_short_returns_message():
    """Короткий текст → send_result возвращает объект Message (результат answer)."""
    message = _make_message()
    sent_msg = AsyncMock()
    message.answer.return_value = sent_msg

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        result = await send_result(message, "Короткий текст")

    assert result is sent_msg


@pytest.mark.asyncio
async def test_send_result_series_returns_none():
    """Текст, разбитый на серию частей, → send_result возвращает None."""
    message = _make_message()
    paragraph = "Слово другое предложение здесь.\n\n"
    text = paragraph * 150
    parts = split_text(text)
    assert 1 < len(parts) <= MAX_PARTS

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        result = await send_result(message, text)

    assert result is None


@pytest.mark.asyncio
async def test_send_result_very_long_returns_none():
    """Очень длинный текст (файл) → send_result возвращает None."""
    message = _make_message()
    paragraph = "Длинный абзац текста для теста разбивки.\n\n"
    text = paragraph * 1000
    parts = split_text(text)
    assert len(parts) > MAX_PARTS

    with patch("services.reply.asyncio.sleep", new=AsyncMock()):
        result = await send_result(message, text)

    assert result is None


@pytest.mark.asyncio
async def test_send_result_empty_returns_none():
    """Пустой текст → send_result возвращает None."""
    message = _make_message()
    result = await send_result(message, "")
    assert result is None


# ---------------------------------------------------------------------------
# Атрибуция ATTRIBUTION_FOOTER в non-progressive (групповой) ветке
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audio_non_progressive_attribution_footer_present():
    """progressive=False (группы): короткий результат содержит подпись ATTRIBUTION_FOOTER."""
    from handlers.audio import process_audio
    import services.result_cache as cache_mod

    cache_mod._cache.clear()

    message = _make_message()
    sent_msg = AsyncMock()
    sent_msg.message_id = 999
    message.answer.return_value = sent_msg

    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("текст", None))),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## структура")),
        patch("services.reply.config", {"ATTRIBUTION_FOOTER": True}),
        patch("services.reply.get_bot_username", return_value="TestifyBot"),
    ):
        await process_audio(message, message, bot, b"audio", progressive=False)

    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args[0][0]
    assert "@TestifyBot" in sent_text


@pytest.mark.asyncio
async def test_image_non_progressive_attribution_footer_present():
    """process_photo progressive=False (группы): короткий результат содержит подпись ATTRIBUTION_FOOTER."""
    from handlers.image import process_photo
    import services.result_cache as cache_mod

    cache_mod._cache.clear()

    message = _make_message()
    message.photo = [AsyncMock(file_id="fid")]
    sent_msg = AsyncMock()
    sent_msg.message_id = 888
    message.answer.return_value = sent_msg

    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="текст")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## структура")),
        patch("services.reply.config", {"ATTRIBUTION_FOOTER": True}),
        patch("services.reply.get_bot_username", return_value="TestifyBot"),
    ):
        await process_photo(message, message, bot, progressive=False)

    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args[0][0]
    assert "@TestifyBot" in sent_text
