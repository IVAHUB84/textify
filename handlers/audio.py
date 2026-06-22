from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import Message

from services.structure import structure_text
from services.transcribe import transcribe

router = Router()

NO_SPEECH_MESSAGE = "Речь в аудио не распознана."


async def _handle_audio_bytes(message: Message, audio_bytes: bytes) -> None:
    text = await transcribe(audio_bytes)
    if text.strip():
        await message.answer(await structure_text(text))
    else:
        await message.answer(NO_SPEECH_MESSAGE)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.voice, destination=buffer)
    await _handle_audio_bytes(message, buffer.getvalue())


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.audio, destination=buffer)
    await _handle_audio_bytes(message, buffer.getvalue())


@router.message(F.document & F.document.mime_type & F.document.mime_type.startswith("audio/"))
async def handle_audio_document(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    await _handle_audio_bytes(message, buffer.getvalue())
