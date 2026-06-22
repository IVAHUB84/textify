from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import Message

from services.ocr import recognize_text

router = Router()

NO_TEXT_MESSAGE = "Текст на изображении не распознан."


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    photo = message.photo[-1]
    buffer = BytesIO()
    await bot.download(photo, destination=buffer)
    text = await recognize_text(buffer.getvalue())
    if text.strip():
        await message.answer(text)
    else:
        await message.answer(NO_TEXT_MESSAGE)


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def handle_image_document(message: Message, bot: Bot) -> None:
    buffer = BytesIO()
    await bot.download(message.document, destination=buffer)
    text = await recognize_text(buffer.getvalue())
    if text.strip():
        await message.answer(text)
    else:
        await message.answer(NO_TEXT_MESSAGE)
