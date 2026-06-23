from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from services import result_cache
from services.llm import BUDGET_EXCEEDED, summarize
from services.reply import send_result
from services.structure import structure_text

actions_router = Router()

_CB_SUMMARIZE = "act:sum"
_CB_FULL = "act:full"


def actions_keyboard(progressive: bool = False) -> InlineKeyboardMarkup:
    if progressive:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Показать полностью", callback_data=_CB_FULL),
                    InlineKeyboardButton(text="Кратко", callback_data=_CB_SUMMARIZE),
                ]
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Кратко", callback_data=_CB_SUMMARIZE),
            ]
        ]
    )


@actions_router.callback_query(F.data == _CB_FULL)
async def handle_full(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = callback.message
    if not isinstance(raw_msg, Message):
        await callback.answer("Текст недоступен", show_alert=True)
        return

    raw_text = result_cache.get(raw_msg.chat.id, raw_msg.message_id)
    if raw_text is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    bot: Bot = callback.bot  # type: ignore[assignment]
    async with ChatActionSender(bot=bot, chat_id=raw_msg.chat.id, action=ChatAction.TYPING):
        result = await structure_text(raw_text)

    await send_result(raw_msg, result)


@actions_router.callback_query(F.data == _CB_SUMMARIZE)
async def handle_summarize(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = callback.message
    if not isinstance(raw_msg, Message):
        await callback.answer("Текст недоступен", show_alert=True)
        return

    raw_text = result_cache.get(raw_msg.chat.id, raw_msg.message_id)
    if raw_text is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    bot: Bot = callback.bot  # type: ignore[assignment]
    async with ChatActionSender(bot=bot, chat_id=raw_msg.chat.id, action=ChatAction.TYPING):
        result = await summarize(raw_text)

    if result is BUDGET_EXCEEDED:
        await raw_msg.answer("Дневной бесплатный лимит исчерпан, попробуйте завтра.")
        return

    if result is None:
        await raw_msg.answer("Не удалось выполнить действие. Попробуйте позже.")
        return

    assert isinstance(result, str)
    await send_result(raw_msg, result)
