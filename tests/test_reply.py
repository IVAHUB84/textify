"""Тесты services/reply.py: split_text и send_result."""
from unittest.mock import AsyncMock, call, patch

import pytest

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
    """Короткий текст — ровно один message.answer, без answer_document и без asyncio.sleep."""
    message = _make_message()
    text = "Короткий ответ."

    with patch("services.reply.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await send_result(message, text)

    message.answer.assert_awaited_once_with(text)
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

    with (
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

    with (
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)
