import asyncio

from aiogram import Bot, Dispatcher

from config import config
from handlers import commands_router, text_router


async def main() -> None:
    bot = Bot(token=config["BOT_TOKEN"])
    dp = Dispatcher()

    dp.include_router(commands_router)
    dp.include_router(text_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
