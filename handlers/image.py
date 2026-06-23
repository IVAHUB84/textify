from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from handlers.actions import actions_keyboard
from services import result_cache
from services.llm import BUDGET_EXCEEDED, summarize_gist
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

_GIST_BUDGET_PREVIEW = "Суть недоступна (дневной лимит). Выберите действие на кнопках ниже."
_GIST_FAIL_PREVIEW = "Не удалось сформировать суть. Выберите действие на кнопках ниже."


async def process_photo(
    media_message: Message,
    reply_target: Message,
    bot: Bot,
    progressive: bool = False,
) -> None:
    assert media_message.photo is not None
    photo = media_message.photo[-1]
    buffer = BytesIO()
    await bot.download(photo, destination=buffer)
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.UPLOAD_DOCUMENT):
        text = await recognize_text(buffer.getvalue())
        if not text.strip():
            await reply_target.answer(NO_TEXT_MESSAGE)
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


async def process_image_document(
    media_message: Message,
    reply_target: Message,
    bot: Bot,
    progressive: bool = False,
) -> None:
    assert media_message.document is not None
    buffer = BytesIO()
    await bot.download(media_message.document, destination=buffer)
    async with ChatActionSender(bot=bot, chat_id=reply_target.chat.id, action=ChatAction.UPLOAD_DOCUMENT):
        text = await recognize_text(buffer.getvalue())
        if not text.strip():
            await reply_target.answer(NO_TEXT_MESSAGE)
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


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    await process_photo(message, message, bot, progressive=True)


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def handle_image_document(message: Message, bot: Bot) -> None:
    await process_image_document(message, message, bot, progressive=True)
