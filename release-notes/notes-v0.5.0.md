# Release Notes v0.5.0

- **Дата:** 2026-06-22
- **Тип релиза:** minor

## Кратко

Textify теперь доводит распознанный текст до заявленного ценностного обещания: на вход голос/аудио или
фото, на выходе — структурированный Markdown (заголовки, списки, ключевые пункты). Провайдер по
умолчанию — бесплатный Cloudflare Workers AI, работающий с RU-IP ivahub без прокси. При любом сбое
LLM пользователь по-прежнему получает сырой распознанный текст.

## Что нового

### Возможности

- **Сервис структурирования `services/structure.py`** — новый модуль-оркестратор с абстракцией
  провайдера (Protocol `LLMProvider`). Публичная функция `async def structure_text(raw_text: str) -> str`
  принимает сырой OCR/транскрипт и возвращает структурированный Markdown.
- **Провайдер по умолчанию — Cloudflare Workers AI** (`@cf/meta/llama-3.1-8b-instruct`). Не блокирует
  RU-IP, работает с ivahub напрямую без прокси.
- **Groq — переключаемая опция** (`LLM_PROVIDER=groq`): код-путь реализован и покрыт тестами; боевое
  использование не требуется до решения проблемы гео-блокировки Groq по RU IP.
- **Структурирование подключено к обоим каналам**: изображения (`handlers/image.py`) и аудио
  (`handlers/audio.py`). Сырой результат OCR/транскрипции перед отправкой пользователю проходит через
  `structure_text`.

### Улучшения

- `handlers/audio.py` рефакторинг: три хендлера (`handle_voice`, `handle_audio`,
  `handle_audio_document`) объединены через внутренний хелпер `_handle_audio_bytes`, исключающий
  дублирование.
- Входной текст усекается до 8 000 символов перед отправкой в LLM (защита от превышения лимита
  запроса); при фолбэке пользователю возвращается полный исходный текст.
- Новая зависимость `httpx>=0.27.0` — нативный асинхронный HTTP-клиент; вендорские SDK провайдеров
  не добавляются.

### Исправления

- Удалены неиспользуемые импорты в `tests/test_ocr.py` (`ImageFont`) и `tests/test_ocr_v4.py`
  (`asyncio`), выявленные ruff F401.

## Изменения публичного контракта

Пользовательский контракт **не ломается**: те же входные каналы (фото, voice, audio, audio-document),
тот же тип ответа. Ответ теперь — структурированный Markdown при доступности LLM либо сырой
распознанный текст при фолбэке. Сообщения `NO_TEXT_MESSAGE` / `NO_SPEECH_MESSAGE` при нераспознанном
вводе сохранены.

Новые переменные окружения (все опциональны — бот стартует без них, структурирование деградирует в
фолбэк):

| Переменная | Дефолт | Назначение |
|---|---|---|
| `LLM_PROVIDER` | `cloudflare` | Выбор провайдера (`cloudflare` / `groq`) |
| `CF_ACCOUNT_ID` | — | Cloudflare Account ID |
| `CF_API_TOKEN` | — | Cloudflare API Token |
| `CF_MODEL` | `@cf/meta/llama-3.1-8b-instruct` | Модель Cloudflare Workers AI |
| `GROQ_API_KEY` | — | Groq API Key (опция) |

Миграция: обновить образ через CI/CD и добавить `CF_ACCOUNT_ID` / `CF_API_TOKEN` в `.env` на ivahub.

## Известные ограничения

- **КП-13 не проверено в этой среде:** реальная достижимость Cloudflare Workers AI с ivahub (RU IP)
  подтверждается только деплоем (ОВ-1/НФТ-4). Если эндпоинт окажется недостижим — фолбэк на сырой
  текст работает, выбор провайдера по умолчанию пересматривается отдельным ADR.
- **Groq-ветка** реализована и протестирована на уровне переключения кода, но боевая работоспособность
  с ivahub не проверяется (Groq гео-блокирует RU IP).
- **Качество структурирования (КП-9 / НФТ-7)** зависит от модели и промпта; абсолютная точность
  оформления не гарантируется. На плохо распознанном (шумном) OCR результат может быть ограниченным.
- **mypy** фиксирует 11 предсуществующих предупреждений (отсутствие стабов у faster_whisper,
  pytesseract, PIL; Optional-типы в handlers). Ни одна из ошибок не из v0.5.0; новый модуль
  `services/structure.py` проходит mypy чисто.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-005.md`
- ADR: `adrs/adr-005.md`
- Спецификация: `releases/release-spec-v0.5.0.md`
- Требование: `requirements/req-textify-005.md`

## Проверка

**pytest:** 73 passed, 3 skipped (Tesseract не установлен в среде — допустимо).

**ruff:** зелёный (2 предсуществующих F401 исправлены chore-коммитом перед релизом).

**mypy `services/structure.py`:** Success, no issues.

**Критерии приёмки КП-1..КП-13:**

| Критерий | Статус | Как проверено |
|---|---|---|
| КП-1 | Выполнен | `services/structure.py` существует; `structure_text` принимает str, возвращает str; тест `test_structure_text_cloudflare_success` |
| КП-2 | Выполнен | При незаданном `LLM_PROVIDER` → Cloudflare URL; тест `test_structure_text_default_provider_is_cloudflare` |
| КП-3 | Выполнен | `LLM_PROVIDER=groq` → Groq URL; тест `test_structure_text_groq_provider_selected` |
| КП-4 | Выполнен | `handlers/image.py` и `handlers/audio.py` вызывают `structure_text`; тесты `test_handle_photo_calls_structure_text_on_nonempty_ocr` и `test_handle_voice_calls_structure_text_on_nonempty_transcript` |
| КП-5 | Выполнен | Сетевая ошибка/таймаут/5xx/пустой ответ → возврат сырого текста без исключения; тесты fallback-серии |
| КП-6 | Выполнен | `structure_text` — `async def`, использует `httpx.AsyncClient` (не `to_thread`); тесты `test_structure_text_is_async`, `test_structure_text_uses_httpx_async_client` |
| КП-7 | Выполнен | Чтение секретов через `os.environ`; плейсхолдеры в `.env.example` и `deploy/.env.example`; реальные значения не закоммичены (`.gitignore` покрывает `.env`) |
| КП-8 | Выполнен | Пустой OCR/транскрипт → `NO_TEXT_MESSAGE`/`NO_SPEECH_MESSAGE`, `structure_text` не вызывается; тесты `test_handle_photo_no_structure_on_empty_ocr` и аналоги |
| КП-9 | Не проверено в этой среде | Требует живого LLM-вызова (нет ключей в CI-среде). По условию ОВ-5 — качественная проверка при деплое |
| КП-10 | Выполнен | Вход > 8000 символов усекается до `_MAX_INPUT_CHARS` перед отправкой; фолбэк отдаёт полный текст; тесты `test_structure_text_truncates_long_input` и `test_structure_text_truncates_long_input_sent_to_provider` |
| КП-11 | Выполнен | `roadmap.md` обновлён: v0.5.0 описывает Cloudflare-дефолт + Groq-опцию + причину смены провайдера; статус «выпущен 2026-06-22» |
| КП-12 | Выполнен | Профиль поставки ADR-001 не изменён: long-polling, `deploy/docker-compose.yml` без `ports:`/Traefik/`edge`; новых системных пакетов нет |
| КП-13 | Не проверено в этой среде | Реальная достижимость Cloudflare с ivahub — проверяется только деплоем (ОВ-1) |
