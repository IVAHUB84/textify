from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import Message

from handlers.actions import actions_keyboard
from services.ocr import recognize_text
from services.reply import send_result
from services.structure import structure_text

router = Router()

NO_TEXT_MESSAGE = (
    "Текст на изображении не распознан.\n"
    "Совет: для лучшего качества отправляйте изображение как файл (📎 → Документ), "
    "а не обычным фото — так Telegram не пережимает его."
)


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    photo = message.photo[-1]
    buffer = BytesIO()
    await bot.download(photo, destination=buffer)
    text = await recognize_text(buffer.getvalue())
    if text.strip():
        await send_result(message, await structure_text(text), reply_markup=actions_keyboard())
    else:
        await message.answer(NO_TEXT_MESSAGE)


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def handle_image_document(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    text = await recognize_text(buffer.getvalue())
    if text.strip():
        await send_result(message, await structure_text(text), reply_markup=actions_keyboard())
    else:
        await message.answer(NO_TEXT_MESSAGE)
