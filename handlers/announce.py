import asyncio
import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from announcements import ANNOUNCEMENTS
from config import config
from services.announce import run_broadcast, set_last_announced_version
from services.stats import set_announcements_optout
from version import __version__

logger = logging.getLogger(__name__)

announce_router = Router()

_background_tasks: set[asyncio.Task] = set()


def build_admin_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Разослать", callback_data="ann:send"),
                InlineKeyboardButton(text="Пропустить", callback_data="ann:skip"),
            ]
        ]
    )


async def _do_broadcast(bot: Bot, admin_id: int) -> None:
    text = ANNOUNCEMENTS.get(__version__)
    if text is None:
        return
    try:
        sent, skipped, errors = await run_broadcast(bot, text)
        await bot.send_message(
            admin_id,
            f"Рассылка v{__version__} завершена: отправлено {sent}, "
            f"пропущено/заблокировано {skipped}, ошибок {errors}.",
        )
    except Exception:
        logger.warning("Ошибка фоновой рассылки", exc_info=True)
        try:
            await bot.send_message(
                admin_id,
                f"Рассылка v{__version__} не выполнена, подробности в логах.",
            )
        except Exception:
            logger.warning("Не удалось уведомить админа об ошибке рассылки", exc_info=True)


@announce_router.callback_query(lambda c: c.data == "ann:send")
async def handle_ann_send(callback: CallbackQuery, bot: Bot) -> None:
    admin_id = config.get("ADMIN_USER_ID")
    if callback.from_user is None or callback.from_user.id != admin_id:
        await callback.answer("Недоступно.")
        return

    await set_last_announced_version(__version__)
    await callback.answer("Рассылка запущена.")

    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    task = asyncio.create_task(_do_broadcast(bot, admin_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@announce_router.callback_query(lambda c: c.data == "ann:skip")
async def handle_ann_skip(callback: CallbackQuery) -> None:
    admin_id = config.get("ADMIN_USER_ID")
    if callback.from_user is None or callback.from_user.id != admin_id:
        await callback.answer("Недоступно.")
        return

    await set_last_announced_version(__version__)
    await callback.answer("Версия помечена анонсированной без рассылки.")

    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


@announce_router.callback_query(lambda c: c.data == "ann:off")
async def handle_ann_off(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    await set_announcements_optout(callback.from_user.id, True)
    await callback.answer("Больше не будем присылать анонсы. Вернуть — /announces_on.")


@announce_router.message(Command("announces_off"))
async def cmd_announces_off(message: Message) -> None:
    if message.from_user is None:
        return
    await set_announcements_optout(message.from_user.id, True)
    await message.answer("Анонсы новых версий отключены. Вернуть — /announces_on.")


@announce_router.message(Command("announces_on"))
async def cmd_announces_on(message: Message) -> None:
    if message.from_user is None:
        return
    await set_announcements_optout(message.from_user.id, False)
    await message.answer("Снова будем присылать анонсы новых версий.")
