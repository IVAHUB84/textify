from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from handlers.actions import actions_keyboard
from services.ocr import recognize_text
from services.reply import send_result
from services.structure import structure_text

router = Router()
router.message.filter(F.chat.type == "private")

NO_TEXT_MESSAGE = (
    "Текст на изображении не распознан.\n"
    "Совет: для лучшего качества отправляйте изображение как файл (📎 → Документ), "
    "а не обычным фото — так Telegram не пережимает его."
)


async def process_photo(media_message: Message, reply_target: Message, bot: Bot) -> None:
    assert media_message.photo is not None
    photo = media_message.photo[-1]
    buffer = BytesIO()
    await bot.download(photo, destination=buffer)
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.UPLOAD_DOCUMENT):
        text = await recognize_text(buffer.getvalue())
        if text.strip():
            await send_result(reply_target, await structure_text(text), reply_markup=actions_keyboard())
        else:
            await reply_target.answer(NO_TEXT_MESSAGE)


async def process_image_document(media_message: Message, reply_target: Message, bot: Bot) -> None:
    assert media_message.document is not None
    buffer = BytesIO()
    await bot.download(media_message.document, destination=buffer)
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.UPLOAD_DOCUMENT):
        text = await recognize_text(buffer.getvalue())
        if text.strip():
            await send_result(reply_target, await structure_text(text), reply_markup=actions_keyboard())
        else:
            await reply_target.answer(NO_TEXT_MESSAGE)


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    await process_photo(message, message, bot)


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def handle_image_document(message: Message, bot: Bot) -> None:
    await process_image_document(message, message, bot)
