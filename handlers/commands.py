from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import BotCommand, Message

from config import config
from services.stats import get_stats

router = Router()

START_TEXT = (
    "Привет! Я Textify — превращаю голосовые, аудио и изображения в чистый текст.\n\n"
    "Что умею:\n"
    "• Голос и аудио — пришлите сообщение, верну транскрипт.\n"
    "• Фото и сканы — отправлю распознанный текст (OCR).\n"
    "• Готовый текст можно сократить или перевести одной кнопкой.\n\n"
    "Просто пришлите сообщение. Бесплатно, русский и английский. /help — справка."
)

# Профиль бота в Telegram (задаётся при старте).
# Description — экран пустого чата («Что умеет этот бот?»), лимит 512 символов.
BOT_DESCRIPTION = (
    "Textify — распознавание речи и OCR прямо в Telegram. Бесплатно, RU/EN.\n\n"
    "• Голос и аудио → транскрипция текста\n"
    "• Фото и сканы → распознавание текста (OCR)\n"
    "• Перевод RU↔EN и краткий пересказ одной кнопкой\n\n"
    "Поддерживает русский и английский язык. Голос в текст, фото в текст — "
    "просто отправьте сообщение."
)

# Short description — карточка профиля бота, лимит 120 символов.
BOT_SHORT_DESCRIPTION = (
    "Транскрипция голоса и OCR фото в текст. Перевод RU↔EN. Бесплатно."
)

BOT_COMMANDS = [
    BotCommand(command="start", description="О боте и как пользоваться"),
    BotCommand(command="help", description="Справка по возможностям"),
]


async def setup_bot_profile(bot: Bot) -> None:
    """Задаёт меню команд, description и short description в Telegram."""
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_description(BOT_DESCRIPTION)
    await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)

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
