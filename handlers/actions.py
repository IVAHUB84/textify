from collections.abc import Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.chat_action import ChatActionSender

from services import result_cache
from services.llm import BUDGET_EXCEEDED, extract_tasks, summarize, translate
from services.ocr import recognize_pdf
from services.reply import send_result
from services.sentinel import _BudgetExceededType
from services.structure import structure_text
from services.transcribe import format_srt, format_timestamps

actions_router = Router()

_CB_SUMMARIZE = "act:sum"
_CB_FULL = "act:full"
_CB_TRANSLATE = "act:tr"
_CB_TASKS = "act:task"
_CB_TIMESTAMPS = "act:ts"
_CB_SRT = "act:srt"
_CB_PDF = "act:pdf"

_LLMAction = Callable[[str], Awaitable["str | None | _BudgetExceededType"]]


def actions_keyboard(
    progressive: bool = False, with_extras: bool = False, with_pdf: bool = False
) -> InlineKeyboardMarkup:
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
    if with_extras:
        rows.append(
            [
                InlineKeyboardButton(text="⏱ Тайм-коды", callback_data=_CB_TIMESTAMPS),
                InlineKeyboardButton(text="Субтитры", callback_data=_CB_SRT),
            ]
        )
    if with_pdf:
        rows.append([InlineKeyboardButton(text="📄 PDF", callback_data=_CB_PDF)])
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

    segments = result_cache.get_segments(raw_msg.chat.id, raw_msg.message_id)
    if not segments:
        await callback.answer("Тайм-коды недоступны", show_alert=True)
        return

    await send_result(raw_msg, format_timestamps(segments))


@actions_router.callback_query(F.data == _CB_SRT)
async def handle_srt(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = _cached_message(callback)
    if raw_msg is None:
        await callback.answer("Текст недоступен", show_alert=True)
        return

    segments = result_cache.get_segments(raw_msg.chat.id, raw_msg.message_id)
    if not segments:
        await callback.answer("Субтитры недоступны", show_alert=True)
        return

    srt = format_srt(segments)
    if not srt.strip():
        await callback.answer("Субтитры недоступны", show_alert=True)
        return

    await raw_msg.answer_document(
        BufferedInputFile(srt.encode("utf-8"), filename="subtitles.srt"),
        caption="Субтитры в формате .srt",
    )


@actions_router.callback_query(F.data == _CB_PDF)
async def handle_pdf(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю…")

    raw_msg = _cached_message(callback)
    if raw_msg is None:
        await callback.answer("Изображение недоступно", show_alert=True)
        return

    image_bytes = result_cache.get_image(raw_msg.chat.id, raw_msg.message_id)
    if not image_bytes:
        await callback.answer("Изображение недоступно (устарело)", show_alert=True)
        return

    bot: Bot = callback.bot  # type: ignore[assignment]
    async with ChatActionSender(
        bot=bot, chat_id=raw_msg.chat.id, action=ChatAction.UPLOAD_DOCUMENT
    ):
        pdf = await recognize_pdf(image_bytes)

    if not pdf:
        await raw_msg.answer("Не удалось сформировать PDF. Попробуйте позже.")
        return

    await raw_msg.answer_document(
        BufferedInputFile(pdf, filename="document.pdf"),
        caption="PDF с текстовым слоем (текст можно выделять и искать).",
    )
