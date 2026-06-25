import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import Document, Message, Video, VideoNote

from handlers.audio import process_audio
from handlers.gate import enforce_limit
from handlers.limits import OVERSIZED_MESSAGE, is_oversized
from services.media import extract_audio

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")

NO_AUDIO_MESSAGE = "В этом видео нет звуковой дорожки — распознавать нечего."
DECODE_ERROR_MESSAGE = "Не удалось обработать видео. Попробуйте другой файл."


async def _process_video(message: Message, bot: Bot, attachment: Video | VideoNote | Document) -> None:
    if is_oversized(attachment.file_size):
        await message.answer(OVERSIZED_MESSAGE)
        return

    user_id = message.from_user.id if message.from_user else None
    if user_id is None or not await enforce_limit(message, user_id, is_private=True):
        return

    buffer = BytesIO()
    await bot.download(attachment, destination=buffer)

    try:
        audio = await extract_audio(buffer.getvalue())
    except Exception:
        logger.exception("Failed to extract audio from video")
        await message.answer(DECODE_ERROR_MESSAGE)
        return

    if audio is None:
        await message.answer(NO_AUDIO_MESSAGE)
        return

    await process_audio(message, message, bot, audio, progressive=True)


@router.message(F.video)
async def handle_video(message: Message, bot: Bot) -> None:
    assert message.video is not None
    await _process_video(message, bot, message.video)


@router.message(F.video_note)
async def handle_video_note(message: Message, bot: Bot) -> None:
    assert message.video_note is not None
    await _process_video(message, bot, message.video_note)


@router.message(F.document & F.document.mime_type & F.document.mime_type.startswith("video/"))
async def handle_video_document(message: Message, bot: Bot) -> None:
    assert message.document is not None
    await _process_video(message, bot, message.document)
