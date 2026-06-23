from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from handlers.actions import actions_keyboard
from services.reply import send_result
from services.structure import structure_text
from services.transcribe import transcribe

router = Router()
router.message.filter(F.chat.type == "private")

NO_SPEECH_MESSAGE = "Речь в аудио не распознана."


async def process_audio(
    media_message: Message,
    reply_target: Message,
    bot: Bot,
    audio_bytes: bytes,
    force_local: bool = False,
) -> None:
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.TYPING):
        text = await transcribe(audio_bytes, force_local=force_local)
        if text.strip():
            await send_result(reply_target, await structure_text(text), reply_markup=actions_keyboard())
        else:
            await reply_target.answer(NO_SPEECH_MESSAGE)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    assert message.voice is not None
    buffer = BytesIO()
    await bot.download(message.voice, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue())


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot) -> None:
    assert message.audio is not None
    buffer = BytesIO()
    await bot.download(message.audio, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue())


@router.message(F.document & F.document.mime_type & F.document.mime_type.startswith("audio/"))
async def handle_audio_document(message: Message, bot: Bot) -> None:
    assert message.document is not None
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue())
