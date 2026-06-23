from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from handlers.actions import actions_keyboard
from services import result_cache
from services.llm import BUDGET_EXCEEDED, summarize_gist
from services.reply import send_result
from services.structure import structure_text
from services.transcribe import transcribe

router = Router()
router.message.filter(F.chat.type == "private")

NO_SPEECH_MESSAGE = "Речь в аудио не распознана."

_GIST_BUDGET_PREVIEW = "Суть недоступна (дневной лимит). Доступны «Показать полностью» и «Кратко»."
_GIST_FAIL_PREVIEW = "Не удалось сформировать суть. Доступны «Показать полностью» и «Кратко»."


async def process_audio(
    media_message: Message,
    reply_target: Message,
    bot: Bot,
    audio_bytes: bytes,
    force_local: bool = False,
    progressive: bool = False,
) -> None:
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.TYPING):
        text = await transcribe(audio_bytes, force_local=force_local)
        if not text.strip():
            await reply_target.answer(NO_SPEECH_MESSAGE)
            return

        if progressive:
            gist = await summarize_gist(text)
            if isinstance(gist, str):
                preview = gist
            elif gist is BUDGET_EXCEEDED:
                preview = _GIST_BUDGET_PREVIEW
            else:
                preview = _GIST_FAIL_PREVIEW
            sent: Message = await reply_target.answer(preview, reply_markup=actions_keyboard(progressive=True))
            result_cache.put(sent.chat.id, sent.message_id, text)
        else:
            structured = await structure_text(text)
            result_msg = await send_result(reply_target, structured, reply_markup=actions_keyboard(progressive=False))
            if result_msg is not None:
                result_cache.put(result_msg.chat.id, result_msg.message_id, text)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    assert message.voice is not None
    buffer = BytesIO()
    await bot.download(message.voice, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue(), progressive=True)


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot) -> None:
    assert message.audio is not None
    buffer = BytesIO()
    await bot.download(message.audio, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue(), progressive=True)


@router.message(F.document & F.document.mime_type & F.document.mime_type.startswith("audio/"))
async def handle_audio_document(message: Message, bot: Bot) -> None:
    assert message.document is not None
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    await process_audio(message, message, bot, buffer.getvalue(), progressive=True)
