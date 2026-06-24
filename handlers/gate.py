import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config
from services import limits, subscription

logger = logging.getLogger(__name__)

gate_router = Router()

_CB_GATE_CHECK = "gate:chk"

_MSG_LIMIT_NEUTRAL = "Дневной лимит распознаваний исчерпан, попробуйте завтра."
_MSG_GATE_PROMPT = (
    "Вы исчерпали бесплатный дневной лимит распознаваний.\n\n"
    "Подпишитесь на наш канал — и лимит существенно вырастет!"
)
_MSG_SUBSCRIBED = (
    "Подписка подтверждена, лимит повышен — пришлите медиа ещё раз."
)
_MSG_NOT_SUBSCRIBED = (
    "Пока не вижу подписку. Подпишитесь на канал и нажмите «Проверить» ещё раз."
)


def _gate_keyboard() -> InlineKeyboardMarkup:
    buttons: list[InlineKeyboardButton] = []
    url = subscription.channel_url()
    if url:
        buttons.append(InlineKeyboardButton(text="Открыть канал", url=url))
    buttons.append(
        InlineKeyboardButton(text="Я подписался / Проверить", callback_data=_CB_GATE_CHECK)
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def enforce_limit(message: Message, user_id: int, is_private: bool) -> bool:
    subscriber = subscription.is_subscriber_cached(user_id)
    limit = (
        config["DAILY_LIMIT_SUBSCRIBED"] if subscriber else config["DAILY_LIMIT_FREE"]
    )
    used = await limits.usage_today(user_id)

    if used >= limit:
        if is_private and subscription.is_gate_enabled() and not subscriber:
            await message.answer(_MSG_GATE_PROMPT, reply_markup=_gate_keyboard())
        else:
            await message.answer(_MSG_LIMIT_NEUTRAL)
        return False

    try:
        await limits.record_recognition(user_id)
    except Exception:
        logger.warning(
            "enforce_limit: failed to record recognition for user=%d", user_id, exc_info=True
        )

    return True


@gate_router.callback_query(F.data == _CB_GATE_CHECK)
async def handle_gate_check(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    user_id = callback.from_user.id
    ok = await subscription.check_subscription(bot, user_id)

    if callback.message is None or isinstance(callback.message, InaccessibleMessage):
        text = _MSG_SUBSCRIBED if ok else _MSG_NOT_SUBSCRIBED
        await callback.answer(text, show_alert=True)
        return

    await callback.answer()
    if ok:
        await callback.message.answer(_MSG_SUBSCRIBED)
    else:
        await callback.message.answer(_MSG_NOT_SUBSCRIBED)
