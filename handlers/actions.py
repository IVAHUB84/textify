from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.llm import summarize, translate
from services.reply import send_result

actions_router = Router()

_CB_SUMMARIZE = "act:sum"
_CB_TRANSLATE = "act:tr"


def actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Кратко", callback_data=_CB_SUMMARIZE),
                InlineKeyboardButton(text="Перевести", callback_data=_CB_TRANSLATE),
            ]
        ]
    )


async def _handle_action(callback: CallbackQuery, action: str) -> None:
    raw_msg = callback.message
    text: str | None = getattr(raw_msg, "text", None)
    if not isinstance(raw_msg, Message) or not text or not text.strip():
        await callback.answer("Текст недоступен", show_alert=True)
        return

    await callback.answer("Готовлю…")

    if action == _CB_SUMMARIZE:
        result = await summarize(text)
    else:
        result = await translate(text)

    if result is None:
        await raw_msg.answer("Не удалось выполнить действие. Попробуйте позже.")
        return

    await send_result(raw_msg, result)


@actions_router.callback_query(F.data == _CB_SUMMARIZE)
async def handle_summarize(callback: CallbackQuery) -> None:
    await _handle_action(callback, _CB_SUMMARIZE)


@actions_router.callback_query(F.data == _CB_TRANSLATE)
async def handle_translate(callback: CallbackQuery) -> None:
    await _handle_action(callback, _CB_TRANSLATE)
