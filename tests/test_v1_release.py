"""Тесты релиза v1.0.0: logging, семафор, ChatActionSender, README, Dockerfile."""
import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Задача 1: Логирование из LOG_LEVEL
# ---------------------------------------------------------------------------


def _reset_root_logger():
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


def test_log_level_debug_applied(monkeypatch):
    """LOG_LEVEL=DEBUG → корневой уровень DEBUG."""
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.DEBUG
    _reset_root_logger()


def test_log_level_info_applied(monkeypatch):
    """LOG_LEVEL=INFO → корневой уровень INFO."""
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.INFO
    _reset_root_logger()


def test_log_level_garbage_falls_back_to_info(monkeypatch):
    """Мусорное LOG_LEVEL → INFO, старт не падает."""
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "GARBAGE_VALUE_XYZ")
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.INFO
    _reset_root_logger()


def test_log_level_empty_falls_back_to_info(monkeypatch):
    """Пустое LOG_LEVEL → INFO."""
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "")
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.INFO
    _reset_root_logger()


def test_log_level_missing_falls_back_to_info(monkeypatch):
    """Отсутствующее LOG_LEVEL → INFO."""
    _reset_root_logger()
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.INFO
    _reset_root_logger()


def test_log_level_lowercase_normalized(monkeypatch):
    """LOG_LEVEL=debug (строчный) → корневой уровень DEBUG (нормализация к верхнему регистру)."""
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "debug")
    from bot import _setup_logging
    _setup_logging()
    assert logging.getLogger().level == logging.DEBUG
    _reset_root_logger()


def test_setup_logging_does_not_raise(monkeypatch):
    """_setup_logging никогда не бросает исключений при любом значении LOG_LEVEL."""
    _reset_root_logger()
    for val in ("", "BLAH", "none", "None", "0", "   ", "WARNING"):
        monkeypatch.setenv("LOG_LEVEL", val)
        from bot import _setup_logging
        _setup_logging()
    _reset_root_logger()


# ---------------------------------------------------------------------------
# Задача 4: Семафор сериализует тяжёлые локальные операции — OCR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_serializes_ocr():
    """N параллельных recognize_text: максимум одновременно активных = 1."""
    import services
    import services.ocr as ocr_mod

    active = 0
    max_active = 0

    async def slow_run_ocr(image_bytes: bytes) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return "text"

    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(1)
    ocr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    async def mock_to_thread(f, *args, **kwargs):
        return await slow_run_ocr(*args)

    try:
        with patch("services.ocr.asyncio.to_thread", side_effect=mock_to_thread):
            tasks = [ocr_mod.recognize_text(b"img") for _ in range(4)]
            await asyncio.gather(*tasks)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        ocr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert max_active == 1, f"Одновременно активных OCR: {max_active}, ожидали == 1"


@pytest.mark.asyncio
async def test_semaphore_ocr_sanity_without_semaphore():
    """Sanity: без семафора N параллельных OCR реально перекрываются (max_active > 1).

    Доказывает, что параллелизм в моках существует и строгий == 1 в основном тесте
    обусловлен именно семафором, а не его отсутствием в среде выполнения.
    """
    import services.ocr as ocr_mod

    active = 0
    max_active = 0

    async def slow_run_ocr(image_bytes: bytes) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return "text"

    async def mock_to_thread(f, *args, **kwargs):
        return await slow_run_ocr(*args)

    # Подменяем семафор на Semaphore(N) — ограничения нет при N == количеству задач
    import services
    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(4)
    ocr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    try:
        with patch("services.ocr.asyncio.to_thread", side_effect=mock_to_thread):
            tasks = [ocr_mod.recognize_text(b"img") for _ in range(4)]
            await asyncio.gather(*tasks)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        ocr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert max_active > 1, (
        f"Sanity failed: без ограничивающего семафора параллелизма нет (max_active={max_active}). "
        "Моки не дают реального перекрытия — основной тест семафора ненадёжен."
    )


@pytest.mark.asyncio
async def test_semaphore_serializes_transcribe_local():
    """N параллельных _transcribe_local: максимум одновременно активных = 1."""
    import services
    import services.transcribe as tr_mod

    active = 0
    max_active = 0

    async def slow_transcribe_sync(audio_bytes: bytes) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return "speech"

    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(1)
    tr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    async def mock_to_thread(f, *args, **kwargs):
        return await slow_transcribe_sync(*args)

    try:
        with patch("services.transcribe.asyncio.to_thread", side_effect=mock_to_thread):
            tasks = [tr_mod._transcribe_local(b"audio") for _ in range(4)]
            await asyncio.gather(*tasks)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        tr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert max_active == 1, f"Одновременно активных transcribe_local: {max_active}, ожидали == 1"


@pytest.mark.asyncio
async def test_semaphore_transcribe_sanity_without_semaphore():
    """Sanity: без семафора N параллельных _transcribe_local реально перекрываются (max_active > 1).

    Доказывает, что параллелизм в моках существует и строгий == 1 в основном тесте
    обусловлен именно семафором, а не его отсутствием в среде выполнения.
    """
    import services
    import services.transcribe as tr_mod

    active = 0
    max_active = 0

    async def slow_transcribe_sync(audio_bytes: bytes) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return "speech"

    async def mock_to_thread(f, *args, **kwargs):
        return await slow_transcribe_sync(*args)

    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(4)
    tr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    try:
        with patch("services.transcribe.asyncio.to_thread", side_effect=mock_to_thread):
            tasks = [tr_mod._transcribe_local(b"audio") for _ in range(4)]
            await asyncio.gather(*tasks)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        tr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert max_active > 1, (
        f"Sanity failed: без ограничивающего семафора параллелизма нет (max_active={max_active}). "
        "Моки не дают реального перекрытия — основной тест семафора ненадёжен."
    )


# ---------------------------------------------------------------------------
# Задача 4: CF-путь не держит семафор
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cf_path_does_not_serialize_through_semaphore(monkeypatch):
    """При ASR_PROVIDER=cloudflare успешный CF-ответ: семафор не захватывается параллельными вызовами."""
    pytest.importorskip("httpx")
    import services
    import services.transcribe as tr_mod

    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    monkeypatch.delenv("CF_WHISPER_MODEL", raising=False)

    start_times = []
    end_times = []

    async def tracked_cf(audio_bytes, account_id, api_token, model):
        import time
        start_times.append(time.monotonic())
        await asyncio.sleep(0.03)
        end_times.append(time.monotonic())
        return "cf result"

    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(1)
    tr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    try:
        with patch.object(tr_mod, "_transcribe_cloudflare", side_effect=tracked_cf):
            tasks = [tr_mod.transcribe(b"audio") for _ in range(3)]
            results = await asyncio.gather(*tasks)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        tr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert all(r == "cf result" for r in results)

    assert len(start_times) == 3, (
        f"Ожидали 3 CF-вызова, состоялось {len(start_times)}. "
        "Если CF-вызовы не запустились, тест не доказывает отсутствие сериализации."
    )
    overlap = start_times[1] < end_times[0]
    assert overlap, "CF-вызовы должны выполняться параллельно, а не сериализованно через семафор"


# ---------------------------------------------------------------------------
# Задача 4: Фолбэк CF→local захватывает семафор ровно один раз, без дедлока
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cf_fallback_to_local_no_deadlock(monkeypatch):
    """CF падает → _transcribe_local вызывается через семафор, без дедлока."""
    pytest.importorskip("httpx")
    import services
    import services.transcribe as tr_mod

    monkeypatch.setenv("ASR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")

    original_semaphore = services.HEAVY_LOCAL_SEMAPHORE
    services.HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(1)
    tr_mod.HEAVY_LOCAL_SEMAPHORE = services.HEAVY_LOCAL_SEMAPHORE

    mock_model = MagicMock()
    from types import SimpleNamespace
    mock_model.transcribe.return_value = (iter([SimpleNamespace(text="local fallback")]), MagicMock())

    try:
        with (
            patch.object(tr_mod, "_transcribe_cloudflare", side_effect=Exception("CF failed")),
            patch("services.transcribe._get_model", return_value=mock_model),
        ):
            result = await asyncio.wait_for(tr_mod.transcribe(b"audio"), timeout=5.0)
    finally:
        services.HEAVY_LOCAL_SEMAPHORE = original_semaphore
        tr_mod.HEAVY_LOCAL_SEMAPHORE = original_semaphore

    assert result == "local fallback"


# ---------------------------------------------------------------------------
# Задача 3: ChatActionSender не ломает отправку результата — image handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_action_sender_image_text_sends_result():
    """handle_photo: при непустом OCR send_result вызывается как раньше."""
    from handlers.image import handle_photo

    message = MagicMock()
    message.photo = [MagicMock(file_id="fid")]
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 42
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="распознанный текст")),
        patch("handlers.image.structure_text", new=AsyncMock(return_value="## структурированный")),
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_send.assert_awaited_once()
    args, kwargs = mock_send.await_args
    assert args[1] == "## структурированный"
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_chat_action_sender_image_empty_sends_service_message():
    """handle_photo: при пустом OCR message.answer вызывается, send_result — нет."""
    from handlers.image import handle_photo, NO_TEXT_MESSAGE

    message = MagicMock()
    message.photo = [MagicMock(file_id="fid")]
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 42
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.image.ChatActionSender", return_value=sender_mock),
        patch("handlers.image.recognize_text", new=AsyncMock(return_value="")),
        patch("handlers.image.structure_text", new=AsyncMock()),
        patch("handlers.image.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_photo(message, bot)

    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_TEXT_MESSAGE)


@pytest.mark.asyncio
async def test_chat_action_sender_audio_text_sends_result():
    """handle_voice: при непустом транскрипте send_result вызывается как раньше."""
    from handlers.audio import handle_voice

    message = MagicMock()
    message.voice = MagicMock()
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 42
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="транскрипт")),
        patch("handlers.audio.structure_text", new=AsyncMock(return_value="## структура")),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_send.assert_awaited_once()
    args, kwargs = mock_send.await_args
    assert args[1] == "## структура"


@pytest.mark.asyncio
async def test_chat_action_sender_audio_empty_sends_service_message():
    """handle_voice: при пустом транскрипте message.answer вызывается, send_result — нет."""
    from handlers.audio import handle_voice, NO_SPEECH_MESSAGE

    message = MagicMock()
    message.voice = MagicMock()
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 42
    bot = AsyncMock()

    async def fake_download(src, *, destination):
        destination.write(b"fake")

    bot.download = fake_download

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.audio.ChatActionSender", return_value=sender_mock),
        patch("handlers.audio.transcribe", new=AsyncMock(return_value="")),
        patch("handlers.audio.structure_text", new=AsyncMock()),
        patch("handlers.audio.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_voice(message, bot)

    mock_send.assert_not_awaited()
    message.answer.assert_called_once_with(NO_SPEECH_MESSAGE)


@pytest.mark.asyncio
async def test_chat_action_sender_actions_text_sends_result():
    """_handle_action: при непустом результате send_result вызывается как раньше."""
    from handlers.actions import handle_summarize

    from aiogram.types import Message

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.text = "некий текст"
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 42

    sender_mock = MagicMock()
    sender_mock.__aenter__ = AsyncMock(return_value=None)
    sender_mock.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("handlers.actions.ChatActionSender", return_value=sender_mock),
        patch("handlers.actions.summarize", new=AsyncMock(return_value="- пункт 1")) as mock_sum,
        patch("handlers.actions.send_result", new=AsyncMock()) as mock_send,
    ):
        await handle_summarize(callback)

    mock_sum.assert_awaited_once_with("некий текст")
    mock_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Задача 5: README содержит все 10 env-переменных и три команды
# ---------------------------------------------------------------------------


def test_readme_contains_all_env_variables():
    """README.md содержит все 10 env-переменных."""
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()

    env_vars = [
        "BOT_TOKEN",
        "CF_ACCOUNT_ID",
        "CF_API_TOKEN",
        "CF_MODEL",
        "CF_WHISPER_MODEL",
        "LLM_PROVIDER",
        "ASR_PROVIDER",
        "ADMIN_USER_ID",
        "LOG_LEVEL",
        "STATS_DB_PATH",
    ]
    for var in env_vars:
        assert var in content, f"README.md не содержит переменную {var}"


def test_readme_contains_all_commands():
    """README.md содержит команды /start, /help, /stats."""
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()

    for cmd in ("/start", "/help", "/stats"):
        assert cmd in content, f"README.md не содержит команду {cmd}"


# ---------------------------------------------------------------------------
# Задача 2: Dockerfile содержит PYTHONUNBUFFERED=1
# ---------------------------------------------------------------------------


def test_dockerfile_contains_pythonunbuffered():
    """Dockerfile содержит ENV PYTHONUNBUFFERED=1."""
    dockerfile_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Dockerfile")
    with open(dockerfile_path, encoding="utf-8") as f:
        content = f.read()
    assert "PYTHONUNBUFFERED=1" in content, "Dockerfile не содержит PYTHONUNBUFFERED=1"
