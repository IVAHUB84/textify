import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from services.stats import record_message

logger = logging.getLogger(__name__)


def classify_message(message: Message) -> str:
    doc = message.document
    if message.text and message.text.startswith("/"):
        return "command"
    if message.photo:
        return "photo"
    if doc and doc.mime_type and doc.mime_type.startswith("image/"):
        return "photo"
    if message.voice or message.audio:
        return "audio"
    if doc and doc.mime_type and doc.mime_type.startswith("audio/"):
        return "audio"
    if message.text:
        return "text"
    return "other"


class StatsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user is not None:
            user_id = event.from_user.id
            msg_type = classify_message(event)
            try:
                data["is_new_user"] = await record_message(user_id, msg_type)
            except Exception:
                logger.exception("Ошибка записи статистики для user_id=%d", user_id)
                data["is_new_user"] = False
        return await handler(event, data)
