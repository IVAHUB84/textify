import asyncio
import re

from aiogram.types import BufferedInputFile, Message

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


async def send_result(message: Message, text: str) -> None:
    if not text or not text.strip():
        return

    if len(text) <= MAX_MESSAGE_LEN:
        await message.answer(text)
        return

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
