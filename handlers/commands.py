import logging
import urllib.parse

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config
from services.bot_identity import get_bot_username
from services.limits import effective_daily_limit, total_today, usage_today
from services.referrals import cached_referral_count, record_referral, top_referrers, total_referrals
from services.stats import get_stats
from services.subscription import cached_subscriber_count, is_subscriber_cached

logger = logging.getLogger(__name__)

router = Router()

START_TEXT = (
    "Привет! Я Textify — превращаю голосовые, аудио и изображения в чистый текст.\n\n"
    "Что умею:\n"
    "• Голос и аудио → транскрипт. Кнопками: ⏱ Тайм-коды и Субтитры (.srt).\n"
    "• Фото и сканы → распознанный текст (OCR), плюс searchable PDF или Скан (ч/б).\n"
    "• Над любым результатом: Кратко, Перевести (RU↔EN), Задачи.\n"
    "• В группах: ответьте на медиа и упомяните меня — предложу распознать.\n\n"
    "Бесплатно, русский и английский. Дневной лимит можно поднять — подпишитесь "
    "на канал или пригласите друзей по ссылке ниже. /help — справка."
)

# Профиль бота в Telegram (задаётся при старте).
# Description — экран пустого чата («Что умеет этот бот?»), лимит 512 символов.
BOT_DESCRIPTION = (
    "Textify — распознавание речи и OCR прямо в Telegram. Бесплатно, RU/EN.\n\n"
    "• Голос и аудио → транскрипт (+ тайм-коды и субтитры .srt)\n"
    "• Фото и сканы → текст (OCR), searchable PDF или скан ч/б\n"
    "• Кратко, перевод RU↔EN и «Задачи» одной кнопкой\n"
    "• Работает и в группах\n\n"
    "Отправьте голос, аудио или фото — верну чистый текст."
)

# Short description — карточка профиля бота, лимит 120 символов.
BOT_SHORT_DESCRIPTION = (
    "Голос и фото → текст в Telegram. OCR, PDF, перевод RU↔EN, субтитры. Бесплатно."
)

async def setup_bot_profile(bot: Bot) -> None:
    """Задаёт description и short description; убирает меню команд (кнопку Menu)."""
    await bot.delete_my_commands()
    await bot.set_my_description(BOT_DESCRIPTION)
    await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)

HELP_TEXT = (
    "Доступные команды:\n"
    "/start — о боте, ваш лимит и реферальная ссылка\n"
    "/help — эта справка\n\n"
    "Как пользоваться:\n"
    "• Аудио и голос — пришлите сообщение, верну транскрипт. Кнопки «⏱ Тайм-коды» "
    "и «Субтитры» (.srt) — для аудио.\n"
    "• Фото и сканы — отправьте фото или документ, верну текст (OCR). Кнопки "
    "«📄 PDF» (с выделяемым текстом) и «📄 Скан (ч/б)».\n"
    "• Над результатом: «Кратко» — пересказ, «Перевести» — RU↔EN, «Задачи» — "
    "список дел из текста, «Полностью» — полный текст.\n"
    "• В группах — ответьте на медиа и упомяните меня (@бот), затем нажмите «Распознать».\n\n"
    "Лимит распознаваний в день ограничен. Поднять — подпишитесь на канал или "
    "пригласите друзей (/start → ваша ссылка).\n\n"
    "Совет: для лучшего OCR отправляйте изображение как файл (📎 → Документ), "
    "а не обычным фото — так Telegram его не пережимает."
)

_SHARE_TEXT = "Попробуй Textify — бесплатный бот для транскрипции голоса и OCR фото!"


def _friends_word(n: int) -> str:
    mod10 = n % 10
    mod100 = n % 100
    if mod10 == 1 and mod100 != 11:
        return "друга"
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return "друга"
    return "друзей"


def _build_ref_link(user_id: int) -> str:
    bot_username = get_bot_username()
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def build_share_url(user_id: int) -> str:
    ref_link = _build_ref_link(user_id)
    return (
        "https://t.me/share/url"
        f"?url={urllib.parse.quote(ref_link, safe='')}"
        f"&text={urllib.parse.quote(_SHARE_TEXT, safe='')}"
    )


def _build_share_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поделиться ботом", url=build_share_url(user_id))]
        ]
    )


def _parse_referrer_id(args: str | None) -> int | None:
    if not args:
        return None
    if args.startswith("ref_"):
        tail = args[4:]
        try:
            return int(tail)
        except ValueError:
            return None
    return None


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, is_new_user: bool = False) -> None:
    if message.from_user is None:
        await message.answer(START_TEXT)
        return

    user_id = message.from_user.id

    if message.chat.type != "private":
        await message.answer(START_TEXT)
        return

    if is_new_user:
        referrer_id = _parse_referrer_id(command.args)
        if referrer_id is not None and referrer_id != user_id:
            try:
                await record_referral(referrer_id, user_id)
                logger.info(
                    "Реферал зафиксирован: referrer=%d referred=%d",
                    referrer_id,
                    user_id,
                )
            except Exception:
                logger.exception(
                    "Ошибка фиксации реферала: referrer=%d referred=%d",
                    referrer_id,
                    user_id,
                )

    invited_count = 0
    try:
        invited_count = await cached_referral_count(user_id)
    except Exception:
        logger.exception(
            "Ошибка чтения счётчика рефералов для user_id=%d", user_id
        )

    limit_line = ""
    try:
        subscriber = is_subscriber_cached(user_id)
        base = config["DAILY_LIMIT_SUBSCRIBED"] if subscriber else config["DAILY_LIMIT_FREE"]
        effective = effective_daily_limit(base, invited_count)
        used = await usage_today(user_id)
        remaining = max(0, effective - used)
        bonus = effective - base
        limit_line = f"\nСегодня доступно {remaining} из {effective} распознаваний."
        if bonus > 0:
            limit_line += f"\nЛимит: {base} базовых + {bonus} за {invited_count} {_friends_word(invited_count)}."
    except Exception:
        logger.exception("Ошибка чтения дневного лимита для user_id=%d", user_id)

    ref_link = _build_ref_link(user_id)
    text = (
        f"{START_TEXT}\n\n"
        f"Ваша реферальная ссылка:\n{ref_link}\n"
        f"Приглашено: {invited_count}"
        f"{limit_line}"
    )

    markup = _build_share_keyboard(user_id)
    await message.answer(text, reply_markup=markup)


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

    ref_total = await total_referrals()
    top = await top_referrers(5)

    if top:
        top_lines = "\n".join(f"  {rid}: {cnt}" for rid, cnt in top)
        ref_block = f"Всего рефералов: {ref_total}\nТоп приглашающих:\n{top_lines}"
    else:
        ref_block = f"Всего рефералов: {ref_total}\nТоп приглашающих:\n  пока нет рефералов"

    limits_block = ""
    try:
        recognitions_today = await total_today()
        subscribers_cached = cached_subscriber_count()
        limits_block = (
            f"\nДневные распознавания (UTC сегодня): {recognitions_today}\n"
            f"Подтверждённых подписчиков в кэше: {subscribers_cached}"
        )
    except Exception:
        logger.exception("Ошибка чтения статистики лимитов")

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
        f"Последнее обращение (UTC): {last_seen}\n\n"
        f"{ref_block}"
        f"{limits_block}"
    )
    await message.answer(text)
