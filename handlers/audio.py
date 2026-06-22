from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import Message

from services.transcribe import transcribe

router = Router()

NO_SPEECH_MESSAGE = "Речь в аудио не распознана."


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.voice, destination=buffer)
    text = await transcribe(buffer.getvalue())
    if text.strip():
        await message.answer(text)
    else:
        await message.answer(NO_SPEECH_MESSAGE)


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.audio, destination=buffer)
    text = await transcribe(buffer.getvalue())
    if text.strip():
        await message.answer(text)
    else:
        await message.answer(NO_SPEECH_MESSAGE)


@router.message(F.document & F.document.mime_type & F.document.mime_type.startswith("audio/"))
async def handle_audio_document(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    text = await transcribe(buffer.getvalue())
    if text.strip():
        await message.answer(text)
    else:
        await message.answer(NO_SPEECH_MESSAGE)
