import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from unittest.mock import AsyncMock

from handlers import audio_router, commands_router, image_router, text_router
from handlers.commands import HELP_TEXT, START_TEXT
from handlers.text import STUB_TEXT


@pytest.fixture(scope="module")
def dp() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(commands_router)
    dispatcher.include_router(image_router)
    dispatcher.include_router(audio_router)
    dispatcher.include_router(text_router)
    return dispatcher


def test_routers_registered(dp: Dispatcher):
    """Т-3: роутеры из handlers/ зарегистрированы в диспетчере."""
    sub_routers = dp.sub_routers
    assert commands_router in sub_routers, "commands_router не подключён"
    assert text_router in sub_routers, "text_router не подключён"


def test_image_router_registered(dp: Dispatcher):
    """Т-3: image_router зарегистрирован в диспетчере."""
    sub_routers = dp.sub_routers
    assert image_router in sub_routers, "image_router не подключён"


def test_image_router_before_text_router(dp: Dispatcher):
    """Т-3: image_router зарегистрирован до text_router — изображение не перехватит заглушка."""
    sub_routers = list(dp.sub_routers)
    image_index = sub_routers.index(image_router)
    text_index = sub_routers.index(text_router)
    assert image_index < text_index, (
        f"image_router (позиция {image_index}) должен быть до text_router (позиция {text_index})"
    )


def test_audio_router_registered(dp: Dispatcher):
    """Т-3: audio_router зарегистрирован в диспетчере."""
    assert audio_router in dp.sub_routers, "audio_router не подключён"


def test_audio_router_before_text_router(dp: Dispatcher):
    """Т-3: audio_router зарегистрирован до text_router — аудио не перехватит заглушка."""
    sub_routers = list(dp.sub_routers)
    audio_index = sub_routers.index(audio_router)
    text_index = sub_routers.index(text_router)
    assert audio_index < text_index, (
        f"audio_router (позиция {audio_index}) должен быть до text_router (позиция {text_index})"
    )


def test_audio_router_has_voice_and_audio_handlers():
    """Т-3: в audio_router есть хендлеры для voice и audio (минимум 2)."""
    handlers = list(audio_router.message.handlers)
    assert len(handlers) >= 2, (
        f"Ожидали минимум 2 хендлера в audio_router (voice + audio), найдено: {len(handlers)}"
    )


def test_image_router_has_photo_and_document_handlers():
    """Т-3: в image_router есть хендлеры для фото и для image-документа."""
    handlers = list(image_router.message.handlers)
    assert len(handlers) >= 2, (
        f"Ожидали минимум 2 хендлера в image_router (фото + документ), найдено: {len(handlers)}"
    )


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
    """Т-4: /start отвечает текстом, содержащим START_TEXT с описанием актуальных функций."""
    from unittest.mock import MagicMock, patch
    message = AsyncMock()
    message.text = "/start"
    message.chat = MagicMock()
    message.chat.type = "private"
    message.from_user = MagicMock()
    message.from_user.id = 1
    command = MagicMock()
    command.args = None
    from handlers.commands import cmd_start
    with patch("handlers.commands.count_referrals", return_value=AsyncMock(return_value=0)()):
        await cmd_start(message, command, is_new_user=False)
    message.answer.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert START_TEXT in reply
    assert any(word in reply.lower() for word in ("аудио", "изображен", "распозна", "ocr"))


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


@pytest.mark.asyncio
async def test_setup_bot_profile():
    """Профиль бота: задаются меню команд, description и short description."""
    from handlers.commands import (
        BOT_COMMANDS,
        BOT_DESCRIPTION,
        BOT_SHORT_DESCRIPTION,
        setup_bot_profile,
    )

    assert len(BOT_DESCRIPTION) <= 512
    assert len(BOT_SHORT_DESCRIPTION) <= 120

    bot = AsyncMock()
    await setup_bot_profile(bot)
    bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    bot.set_my_description.assert_awaited_once_with(BOT_DESCRIPTION)
    bot.set_my_short_description.assert_awaited_once_with(BOT_SHORT_DESCRIPTION)
