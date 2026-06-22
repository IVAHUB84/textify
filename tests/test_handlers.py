import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from unittest.mock import AsyncMock

from handlers import commands_router, text_router
from handlers.commands import START_TEXT, HELP_TEXT
from handlers.text import STUB_TEXT


def make_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands_router)
    dp.include_router(text_router)
    return dp


def test_routers_registered():
    """Т-3: роутеры из handlers/ зарегистрированы в диспетчере."""
    dp = make_dispatcher()
    sub_routers = dp.sub_routers
    assert commands_router in sub_routers, "commands_router не подключён"
    assert text_router in sub_routers, "text_router не подключён"


def test_start_handler_registered():
    """Т-3: хендлер /start присутствует в commands_router."""
    handlers = commands_router.message.handlers
    assert any(handlers), "В commands_router нет message-хендлеров"


def test_help_handler_registered():
    """Т-3: хендлер /help присутствует в commands_router."""
    handlers = commands_router.message.handlers
    assert len(list(handlers)) >= 2, "В commands_router меньше двух хендлеров (/start и /help)"


def test_text_handler_registered():
    """Т-3: хендлер текста присутствует в text_router."""
    handlers = text_router.message.handlers
    assert any(handlers), "В text_router нет message-хендлеров"


@pytest.mark.asyncio
async def test_start_reply():
    """Т-4: /start отвечает точным текстом START_TEXT с упоминанием будущих функций."""
    message = AsyncMock()
    message.text = "/start"
    from handlers.commands import cmd_start
    await cmd_start(message)
    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert reply == START_TEXT
    assert "следующих" in reply.lower()
    assert any(word in reply.lower() for word in ("аудио", "изображен", "распознавани"))


@pytest.mark.asyncio
async def test_help_reply():
    """Т-4: /help отвечает точным текстом HELP_TEXT."""
    message = AsyncMock()
    message.text = "/help"
    from handlers.commands import cmd_help
    await cmd_help(message)
    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert reply == HELP_TEXT


@pytest.mark.asyncio
async def test_text_stub_reply():
    """Т-4: обычный текст получает точный текст заглушки STUB_TEXT."""
    message = AsyncMock()
    message.text = "привет"
    from handlers.text import handle_text
    await handle_text(message)
    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert reply == STUB_TEXT
