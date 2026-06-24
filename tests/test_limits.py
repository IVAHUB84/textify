"""Тесты лимита на скачивание медиа (>20 МБ) и дневного лимита распознаваний."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.limits import MAX_DOWNLOAD_BYTES, is_oversized


def test_is_oversized_none_false():
    assert is_oversized(None) is False


def test_is_oversized_small_false():
    assert is_oversized(1024) is False


def test_is_oversized_at_limit_false():
    assert is_oversized(MAX_DOWNLOAD_BYTES) is False


def test_is_oversized_above_limit_true():
    assert is_oversized(MAX_DOWNLOAD_BYTES + 1) is True


def test_is_oversized_non_int_false():
    """MagicMock/нечисло не считается превышением (и не роняет сравнение)."""
    assert is_oversized(MagicMock()) is False


@pytest.mark.asyncio
async def test_handle_voice_oversized_answers_and_skips_download():
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.voice.file_size = MAX_DOWNLOAD_BYTES + 10
    message.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.audio.process_audio", new=AsyncMock()) as mock_proc:
        await handle_voice(message, bot)

    message.answer.assert_awaited_once()
    bot.download.assert_not_called()
    mock_proc.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_voice_normal_size_downloads():
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.voice.file_size = 1024
    message.from_user = MagicMock()
    message.from_user.id = 1
    message.answer = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    bot = MagicMock()
    bot.download = fake_download

    with (
        patch("handlers.audio.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.audio.process_audio", new=AsyncMock()) as mock_proc,
    ):
        await handle_voice(message, bot)

    mock_proc.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_voice_limit_exceeded_skips_download():
    """При исчерпанном лимите handle_voice не вызывает bot.download."""
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.voice.file_size = 1024
    message.from_user = MagicMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.audio.enforce_limit", new=AsyncMock(return_value=False)):
        await handle_voice(message, bot)

    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_handle_audio_limit_exceeded_skips_download():
    """При исчерпанном лимите handle_audio не вызывает bot.download."""
    from handlers.audio import handle_audio

    message = MagicMock()
    message.audio = MagicMock()
    message.audio.file_size = 1024
    message.from_user = MagicMock()
    message.from_user.id = 43
    message.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.audio.enforce_limit", new=AsyncMock(return_value=False)):
        await handle_audio(message, bot)

    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_handle_audio_document_limit_exceeded_skips_download():
    """При исчерпанном лимите handle_audio_document не вызывает bot.download."""
    from handlers.audio import handle_audio_document

    message = MagicMock()
    message.document = MagicMock()
    message.document.file_size = 1024
    message.from_user = MagicMock()
    message.from_user.id = 44
    message.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.audio.enforce_limit", new=AsyncMock(return_value=False)):
        await handle_audio_document(message, bot)

    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_process_audio_proceeds():
    """process_audio выполняет транскрипцию (enforce_limit вызывается в хендлере, не здесь)."""
    from handlers.audio import process_audio

    media_msg = MagicMock()
    media_msg.from_user = MagicMock()
    media_msg.from_user.id = 1
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.chat.id = 1
    bot = AsyncMock()

    with (
        patch("handlers.audio.transcribe_with_timestamps", new=AsyncMock(return_value=("", []))),
        patch("handlers.audio.ChatActionSender") as mock_sender,
    ):
        mock_sender.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_sender.return_value.__aexit__ = AsyncMock(return_value=False)
        reply_msg.answer = AsyncMock()
        await process_audio(media_msg, reply_msg, bot, b"audio")


@pytest.mark.asyncio
async def test_process_photo_limit_exceeded_skips_download():
    from handlers.image import process_photo

    media_msg = MagicMock()
    media_msg.from_user.id = 2
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.chat.id = 2
    bot = AsyncMock()

    with patch("handlers.image.enforce_limit", new=AsyncMock(return_value=False)):
        await process_photo(media_msg, reply_msg, bot)

    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_process_image_document_limit_exceeded_skips_download():
    from handlers.image import process_image_document

    media_msg = MagicMock()
    media_msg.from_user.id = 3
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.chat.id = 3
    bot = AsyncMock()

    with patch("handlers.image.enforce_limit", new=AsyncMock(return_value=False)):
        await process_image_document(media_msg, reply_msg, bot)

    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_process_photo_oversized_does_not_call_record_recognition():
    """Фото >20МБ не вызывает record_recognition — лимит не списывается."""
    from handlers.image import process_photo
    from handlers.limits import MAX_DOWNLOAD_BYTES

    media_msg = MagicMock()
    media_msg.photo = [MagicMock()]
    media_msg.photo[-1].file_size = MAX_DOWNLOAD_BYTES + 1
    media_msg.from_user.id = 10
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.chat.id = 10
    reply_msg.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.image.enforce_limit", new=AsyncMock(return_value=True)) as mock_enforce:
        await process_photo(media_msg, reply_msg, bot)

    mock_enforce.assert_not_awaited()
    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_process_image_document_oversized_does_not_call_record_recognition():
    """Image-документ >20МБ не вызывает record_recognition — лимит не списывается."""
    from handlers.image import process_image_document
    from handlers.limits import MAX_DOWNLOAD_BYTES

    media_msg = MagicMock()
    media_msg.document = MagicMock()
    media_msg.document.file_size = MAX_DOWNLOAD_BYTES + 1
    media_msg.from_user.id = 11
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.chat.id = 11
    reply_msg.answer = AsyncMock()
    bot = AsyncMock()

    with patch("handlers.image.enforce_limit", new=AsyncMock(return_value=True)) as mock_enforce:
        await process_image_document(media_msg, reply_msg, bot)

    mock_enforce.assert_not_awaited()
    bot.download.assert_not_called()


@pytest.mark.asyncio
async def test_group_grec_callback_limit_charged_to_initiator_not_media_author():
    """В группе enforce_limit вызывается с user_id инициатора callback, не с автора медиа."""
    import handlers.group as grp

    media_author_id = 100
    initiator_id = 200

    media_msg = MagicMock()
    media_msg.chat.type = "group"
    media_msg.chat.id = 300
    media_msg.voice = MagicMock()
    media_msg.voice.file_size = 1024
    media_msg.audio = None
    media_msg.photo = None
    media_msg.document = None
    media_msg.from_user = MagicMock()
    media_msg.from_user.id = media_author_id
    media_msg.answer = AsyncMock()

    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = initiator_id
    cb.message = MagicMock()
    cb.message.reply_to_message = media_msg

    captured_user_ids: list[int] = []

    async def fake_enforce_limit(message, user_id, is_private):
        captured_user_ids.append(user_id)
        return True

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    bot = AsyncMock()
    bot.download = fake_download

    with (
        patch("handlers.group.enforce_limit", new=fake_enforce_limit),
        patch("handlers.group.process_audio", new=AsyncMock()),
    ):
        await grp.handle_grec_callback(cb, bot)

    assert captured_user_ids, "enforce_limit не вызван"
    assert captured_user_ids[0] == initiator_id, (
        f"user_id должен быть {initiator_id} (инициатор callback), получен {captured_user_ids[0]}"
    )
    assert captured_user_ids[0] != media_author_id


@pytest.mark.asyncio
async def test_group_trigger_limit_charged_to_trigger_sender():
    """В группе /textify-триггер: enforce_limit вызывается с user_id отправителя команды."""
    import handlers.group as grp

    media_author_id = 100
    trigger_sender_id = 201

    media_msg = MagicMock()
    media_msg.chat.type = "group"
    media_msg.chat.id = 300
    media_msg.voice = MagicMock()
    media_msg.voice.file_size = 1024
    media_msg.audio = None
    media_msg.photo = None
    media_msg.document = None
    media_msg.from_user = MagicMock()
    media_msg.from_user.id = media_author_id
    media_msg.answer = AsyncMock()

    trigger_msg = MagicMock()
    trigger_msg.chat.type = "group"
    trigger_msg.reply_to_message = media_msg
    trigger_msg.from_user = MagicMock()
    trigger_msg.from_user.id = trigger_sender_id
    trigger_msg.answer = AsyncMock()
    trigger_msg.entities = None
    trigger_msg.caption = None
    trigger_msg.caption_entities = None

    captured_user_ids: list[int] = []

    async def fake_enforce_limit(message, user_id, is_private):
        captured_user_ids.append(user_id)
        return True

    async def fake_download(src, *, destination):
        destination.write(b"audio")

    bot = AsyncMock()
    bot.download = fake_download

    with (
        patch("handlers.group.enforce_limit", new=fake_enforce_limit),
        patch("handlers.group.process_audio", new=AsyncMock()),
    ):
        await grp.handle_group_textify_command(trigger_msg, bot)

    assert captured_user_ids, "enforce_limit не вызван"
    assert captured_user_ids[0] == trigger_sender_id
    assert captured_user_ids[0] != media_author_id


@pytest.mark.asyncio
async def test_actions_do_not_call_record_recognition():
    """Кнопки-действия не вызывают limits.record_recognition."""
    import services.limits as lm
    from unittest.mock import patch

    with patch.object(lm, "record_recognition", new=AsyncMock()) as rec:
        from handlers.actions import _run_llm_action
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.chat.id = 1
        callback.message.message_id = 1

        with patch("handlers.actions.result_cache.get", return_value=None):
            await _run_llm_action(callback, AsyncMock())

        rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_photo_no_user_id_skips_enforce_limit():
    """process_photo при отсутствии from_user в обоих сообщениях не вызывает enforce_limit и не падает."""
    from handlers.image import process_photo

    media_msg = MagicMock()
    media_msg.photo = [MagicMock()]
    media_msg.photo[-1].file_size = 1024
    media_msg.from_user = None
    media_msg.chat.type = "private"
    reply_msg = MagicMock()
    reply_msg.from_user = None
    reply_msg.chat.id = 99
    reply_msg.answer = AsyncMock()
    bot = AsyncMock()

    enforce_mock = AsyncMock(return_value=True)

    async def fake_download(src, *, destination):
        destination.write(b"img")
    bot.download = fake_download

    with (
        patch("handlers.image.enforce_limit", new=enforce_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
    ):
        await process_photo(media_msg, reply_msg, bot)

    enforce_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_dispatch_audio_limit_exceeded_skips_download():
    """В группе при исчерпанном лимите аудио bot.download не вызывается."""
    import handlers.group as grp

    media_msg = MagicMock()
    media_msg.chat.type = "group"
    media_msg.chat.id = 300
    media_msg.voice = MagicMock()
    media_msg.voice.file_size = 1024
    media_msg.audio = None
    media_msg.photo = None
    media_msg.document = None
    media_msg.from_user = MagicMock()
    media_msg.from_user.id = 77
    media_msg.answer = AsyncMock()

    bot = AsyncMock()

    with patch("handlers.group.enforce_limit", new=AsyncMock(return_value=False)):
        await grp._dispatch_media(media_msg, bot, initiator_id=77)

    bot.download.assert_not_called()