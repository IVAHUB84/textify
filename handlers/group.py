from io import BytesIO
from typing import Union

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Audio, Document, Message, MessageEntity, Voice

from config import config
from handlers.audio import process_audio
from handlers.image import process_image_document, process_photo
from services.bot_identity import get_bot_username, set_bot_username  # noqa: F401 (re-exported for tests)

group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))

_HINT_MESSAGE = "Ответьте этой командой на голосовое, аудио или фото с текстом."


def _is_bot_mention(entities: list[MessageEntity] | None, text: str | None) -> bool:
    _bot_username = get_bot_username().lower()
    if not entities or not _bot_username:
        return False
    for entity in entities:
        if entity.type == "mention" and text:
            mention_text = text[entity.offset : entity.offset + entity.length]
            if mention_text.lstrip("@").lower() == _bot_username:
                return True
        elif entity.type == "text_mention":
            if entity.user and entity.user.username and entity.user.username.lower() == _bot_username:
                return True
    return False


def _has_trigger(message: Message) -> bool:
    return _is_bot_mention(message.entities, message.text) or _is_bot_mention(
        message.caption_entities, message.caption
    )


def _has_supported_media(msg: Message) -> bool:
    if msg.voice or msg.audio or msg.photo:
        return True
    if msg.document and msg.document.mime_type:
        mime = msg.document.mime_type
        if mime.startswith("image/") or mime.startswith("audio/"):
            return True
    return False


async def _handle_trigger(message: Message, bot: Bot) -> None:
    reply = message.reply_to_message
    if not reply or not _has_supported_media(reply):
        await message.answer(_HINT_MESSAGE)
        return
    await _dispatch_media(reply, bot)


@group_router.message(Command("textify"))
async def handle_group_textify_command(message: Message, bot: Bot) -> None:
    await _handle_trigger(message, bot)


@group_router.message(F.func(_has_trigger))
async def handle_group_mention(message: Message, bot: Bot) -> None:
    await _handle_trigger(message, bot)


async def _dispatch_media(reply: Message, bot: Bot) -> None:
    force_local: bool = config["GROUP_ASR_LOCAL"]

    audio_attachment: Union[Voice, Audio, Document, None] = reply.voice or reply.audio
    if not audio_attachment and reply.document and reply.document.mime_type and reply.document.mime_type.startswith("audio/"):
        audio_attachment = reply.document

    if audio_attachment:
        buffer = BytesIO()
        await bot.download(audio_attachment, destination=buffer)
        await process_audio(reply, reply, bot, buffer.getvalue(), force_local=force_local)
        return

    if reply.photo:
        await process_photo(reply, reply, bot)
        return

    if reply.document and reply.document.mime_type and reply.document.mime_type.startswith("image/"):
        await process_image_document(reply, reply, bot)
        return
