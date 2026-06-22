from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

STUB_TEXT = (
    "Распознавание текста из сообщений появится в следующих версиях бота. "
    "Пока я умею только отвечать на команды /start и /help."
)


@router.message(~Command("start", "help"))
async def handle_text(message: Message) -> None:
    await message.answer(STUB_TEXT)
