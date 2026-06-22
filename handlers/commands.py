from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import config
from services.stats import get_stats

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
    "Что умею:\n"
    "• Изображения — отправьте фото или документ, верну распознанный текст.\n"
    "• Аудио — пришлите голосовое или аудиофайл, верну транскрипт.\n\n"
    "Совет: для лучшего качества OCR отправляйте изображение как файл (📎 → Документ), "
    "а не обычным фото — так Telegram не пережимает его."
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    admin_id = config["ADMIN_USER_ID"]
    if admin_id is None or message.from_user is None or message.from_user.id != admin_id:
        await message.answer("Команда недоступна.")
        return

    stats = await get_stats()

    first_seen = stats["first_seen"] or "нет данных"
    last_seen = stats["last_seen"] or "нет данных"

    text = (
        "Статистика Textify\n\n"
        f"Уникальных пользователей: {stats['unique_users']}\n"
        f"Всего сообщений: {stats['total_messages']}\n\n"
        "Разбивка по типам:\n"
        f"  Фото/изображения: {stats['photo']}\n"
        f"  Аудио/голос: {stats['audio']}\n"
        f"  Текст: {stats['text']}\n"
        f"  Команды: {stats['command']}\n"
        f"  Прочее: {stats['other']}\n\n"
        f"Первое обращение (UTC): {first_seen}\n"
        f"Последнее обращение (UTC): {last_seen}"
    )
    await message.answer(text)
