import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher

from announcements import ANNOUNCEMENTS
from config import config
from handlers import (
    actions_router,
    announce_router,
    audio_router,
    commands_router,
    group_router,
    image_router,
    setup_bot_profile,
    text_router,
)
from handlers.announce import build_admin_preview_keyboard
from handlers.gate import gate_router
from middlewares import StatsMiddleware
from services.announce import get_last_announced_version, init_announce_db, set_last_announced_version
from services.bot_identity import set_bot_username
from services.budget import init_cf_usage_db
from services.limits import init_limits_db
from services.referrals import init_referrals_db
from services.result_cache import init_result_cache
from services.stats import init_db
from version import __version__, parse_version

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


async def _check_pending_announcement(bot: Bot) -> None:
    logger = logging.getLogger(__name__)
    if not config.get("ANNOUNCEMENTS_ENABLED"):
        return
    admin_id = config.get("ADMIN_USER_ID")
    if not admin_id:
        return

    cur = __version__
    last = await get_last_announced_version()
    if parse_version(cur) <= parse_version(last or "0.0.0"):
        return

    text = ANNOUNCEMENTS.get(cur)
    if text is None:
        await set_last_announced_version(cur)
        logger.info("нет текста анонса для версии %s — рассылка не запускается", cur)
        return

    await bot.send_message(
        admin_id,
        f"Новая версия {cur} — превью анонса:\n\n{text}",
        reply_markup=build_admin_preview_keyboard(),
    )


async def main() -> None:
    _setup_logging()
    logging.getLogger(__name__).info("Textify bot starting")
    init_db()
    init_announce_db()
    init_referrals_db()
    init_limits_db()
    init_cf_usage_db()
    init_result_cache(str(Path(config["STATS_DB_PATH"]).parent / "results.db"))

    bot = Bot(token=config["BOT_TOKEN"])

    me = await bot.get_me()
    if me.username:
        set_bot_username(me.username)

    dp = Dispatcher()

    dp.message.outer_middleware(StatsMiddleware())

    dp.include_router(gate_router)
    dp.include_router(announce_router)
    dp.include_router(commands_router)
    dp.include_router(actions_router)
    dp.include_router(group_router)
    dp.include_router(image_router)
    dp.include_router(audio_router)
    dp.include_router(text_router)

    try:
        await setup_bot_profile(bot)
    except Exception:
        logging.getLogger(__name__).warning("Failed to set bot profile", exc_info=True)

    try:
        await _check_pending_announcement(bot)
    except Exception:
        logging.getLogger(__name__).warning("Failed to check pending announcement", exc_info=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
