import asyncio
import re

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

from config import config
from services.bot_identity import get_bot_username
from services.telegram_format import to_telegram_html

TELEGRAM_LIMIT = 4096
MAX_MESSAGE_LEN = 4000
MAX_PARTS = 5
PART_DELAY_SEC = 0.4


def split_text(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break

        chunk = remaining[:limit]
        cut = _find_cut(chunk, limit)
        parts.append(remaining[:cut])
        remaining = remaining[cut:]

    return parts


def _find_cut(chunk: str, limit: int) -> int:
    # Резать ПОСЛЕ \n\n — разделитель остаётся в конце части
    pos = chunk.rfind("\n\n")
    if pos > 0:
        return pos + 2

    # Резать ПОСЛЕ \n
    pos = chunk.rfind("\n")
    if pos > 0:
        return pos + 1

    # Резать после конца предложения (включая пробел после знака)
    pos = _find_sentence_end(chunk)
    if pos > 0:
        return pos

    # Резать после пробела (не рвём слово)
    pos = chunk.rfind(" ")
    if pos > 0:
        return pos + 1

    # Жёсткий срез — крайний случай (аномально длинное «слово»)
    return limit


def _find_sentence_end(chunk: str) -> int:
    last_end = 0
    for match in re.finditer(r"[.!?]\s+", chunk):
        last_end = match.end()
    return last_end


async def send_result(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    if not text or not text.strip():
        return None

    if len(text) <= MAX_MESSAGE_LEN:
        bot_username = get_bot_username()
        if config["ATTRIBUTION_FOOTER"] and bot_username:
            signature = "\n\n— @" + bot_username
            if len(text) + len(signature) <= MAX_MESSAGE_LEN:
                text = text + signature
        try:
            sent: Message = await message.answer(
                to_telegram_html(text),
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except TelegramBadRequest:
            # Невалидная разметка (несбалансированные теги и т. п.) — шлём как есть.
            sent = await message.answer(text, reply_markup=reply_markup)
        return sent

    parts = split_text(text)

    if len(parts) <= MAX_PARTS:
        for i, part in enumerate(parts):
            await message.answer(part)
            if i < len(parts) - 1:
                await asyncio.sleep(PART_DELAY_SEC)
    else:
        await message.answer_document(
            BufferedInputFile(text.encode("utf-8"), filename="result.txt"),
            caption="Результат целиком во вложении.",
        )
    return None
