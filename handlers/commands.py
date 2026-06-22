from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

START_TEXT = (
    "Привет! Я Textify — бот, который превращает аудио и изображения в текст.\n\n"
    "Пока я только знакомлюсь с тобой. В следующих версиях появятся:\n"
    "• распознавание голосовых и аудиосообщений\n"
    "• распознавание текста на изображениях (OCR)\n"
    "• структурирование текста (заголовки, списки, ключевые пункты)\n\n"
    "Следи за обновлениями!"
)

HELP_TEXT = (
    "Доступные команды:\n"
    "/start — информация о боте\n"
    "/help — эта справка\n\n"
    "Функции распознавания появятся в следующих релизах."
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
