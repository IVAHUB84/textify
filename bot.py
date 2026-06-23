import asyncio

from aiogram import Bot, Dispatcher

from config import config
from handlers import actions_router, audio_router, commands_router, image_router, text_router
from middlewares import StatsMiddleware
from services.stats import init_db


async def main() -> None:
    init_db()

    bot = Bot(token=config["BOT_TOKEN"])
    dp = Dispatcher()

    dp.message.outer_middleware(StatsMiddleware())

    dp.include_router(commands_router)
    dp.include_router(image_router)
    dp.include_router(audio_router)
    dp.include_router(text_router)
    dp.include_router(actions_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
