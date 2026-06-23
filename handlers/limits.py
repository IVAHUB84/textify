"""Лимит на скачивание медиа.

Боты Telegram через getFile качают файлы не больше 20 МБ (стандартный Bot API
сервер). Файл крупнее — bot.download падает, и без явной проверки пользователь
просто не получает ответа. Эти хелперы дают понятное сообщение вместо тишины.
"""

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

OVERSIZED_MESSAGE = (
    "Файл больше 20 МБ — Telegram не даёт ботам скачивать такие файлы. "
    "Пришлите вариант поменьше (например, сожмите аудио или обрежьте запись)."
)


def is_oversized(file_size: int | None) -> bool:
    # isinstance(int) — не только про None: в тестах file_size бывает MagicMock,
    # а сравнение MagicMock > int падает с TypeError. Реальный Telegram даёт int.
    return isinstance(file_size, int) and file_size > MAX_DOWNLOAD_BYTES
