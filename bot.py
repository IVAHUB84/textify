import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from config import config
from handlers import (
    actions_router,
    audio_router,
    commands_router,
    image_router,
    setup_bot_profile,
    text_router,
)
from middlewares import StatsMiddleware
from services.stats import init_db

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _setup_logging() -> None:
    raw = os.getenv("LOG_LEVEL", "INFO") or "INFO"
    level_name = raw.strip().upper()
    if level_name not in _VALID_LOG_LEVELS:
        level_name = "INFO"
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def main() -> None:
    _setup_logging()
    logging.getLogger(__name__).info("Textify bot starting")
    init_db()

    bot = Bot(token=config["BOT_TOKEN"])
    dp = Dispatcher()

    dp.message.outer_middleware(StatsMiddleware())

    dp.include_router(commands_router)
    dp.include_router(image_router)
    dp.include_router(audio_router)
    dp.include_router(text_router)
    dp.include_router(actions_router)

    try:
        await setup_bot_profile(bot)
    except Exception:
        logging.getLogger(__name__).warning("Failed to set bot profile", exc_info=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
