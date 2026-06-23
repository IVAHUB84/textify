from collections.abc import Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from services import result_cache
from services.llm import BUDGET_EXCEEDED, extract_tasks, summarize, translate
from services.reply import send_result
from services.sentinel import _BudgetExceededType
from services.structure import structure_text

actions_router = Router()

_CB_SUMMARIZE = "act:sum"
_CB_FULL = "act:full"
_CB_TRANSLATE = "act:tr"
_CB_TASKS = "act:task"
_CB_TIMESTAMPS = "act:ts"

_LLMAction = Callable[[str], Awaitable["str | None | _BudgetExceededType"]]


def actions_keyboard(progressive: bool = False, with_timestamps: bool = False) -> InlineKeyboardMarkup:
    if progressive:
        rows = [
            [
                InlineKeyboardButton(text="Полностью", callback_data=_CB_FULL),
                InlineKeyboardButton(text="Кратко", callback_data=_CB_SUMMARIZE),
            ],
            [
                InlineKeyboardButton(text="Перевести", callback_data=_CB_TRANSLATE),
                InlineKeyboardButton(text="Задачи", callback_data=_CB_TASKS),
            ],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton(text="Кратко", callback_data=_CB_SUMMARIZE),
                InlineKeyboardButton(text="Перевести", callback_data=_CB_TRANSLATE),
            ],
            [
                InlineKeyboardButton(text="Задачи", callback_data=_CB_TASKS),
            ],
        ]
    if with_timestamps:
        rows.append([InlineKeyboardButton(text="⏱ Тайм-коды", callback_data=_CB_TIMESTAMPS)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cached_message(callback: CallbackQuery) -> Message | None:
    raw_msg = callback.message
    if not isinstance(raw_msg, Message):
        return None
    return raw_msg


async def _run_llm_action(callback: CallbackQuery, action: _LLMAction) -> None:
    await callback.answer("Готовлю…")

    raw_msg = _cached_message(callback)
    if raw_msg is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    raw_text = result_cache.get(raw_msg.chat.id, raw_msg.message_id)
    if raw_text is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    bot: Bot = callback.bot  # type: ignore[assignment]
    async with ChatActionSender(bot=bot, chat_id=raw_msg.chat.id, action=ChatAction.TYPING):
        result = await action(raw_text)

    if result is BUDGET_EXCEEDED:
        await raw_msg.answer("Дневной бесплатный лимит исчерпан, попробуйте завтра.")
        return

    if result is None:
        await raw_msg.answer("Не удалось выполнить действие. Попробуйте позже.")
        return

    assert isinstance(result, str)
    await send_result(raw_msg, result)


@actions_router.callback_query(F.data == _CB_FULL)
async def handle_full(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = _cached_message(callback)
    if raw_msg is None:
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
    await _run_llm_action(callback, summarize)


@actions_router.callback_query(F.data == _CB_TRANSLATE)
async def handle_translate(callback: CallbackQuery) -> None:
    await _run_llm_action(callback, translate)


@actions_router.callback_query(F.data == _CB_TASKS)
async def handle_tasks(callback: CallbackQuery) -> None:
    await _run_llm_action(callback, extract_tasks)


@actions_router.callback_query(F.data == _CB_TIMESTAMPS)
async def handle_timestamps(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = _cached_message(callback)
    if raw_msg is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    ts_text = result_cache.get_timestamps(raw_msg.chat.id, raw_msg.message_id)
    if ts_text is None:
        await callback.answer("Тайм-коды недоступны", show_alert=True)
        return

    await send_result(raw_msg, ts_text)
