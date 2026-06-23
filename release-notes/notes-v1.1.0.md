# Release Notes v1.1.0

- **Дата:** 2026-06-23
- **Тип релиза:** minor

## Кратко

Textify v1.1.0 гарантирует бесплатность владельца при росте трафика: введён персистентный дневной счётчик обращений к Cloudflare Workers AI с авто-деградацией на локальные бесплатные движки при достижении дневного бюджета. Параллельно усилены метаданные бота под поиск Telegram и подготовлен готовый листинг для бесплатных каталогов ботов.

## Что нового

### Возможности

- **Дневной бюджет Cloudflare с авто-деградацией.** При достижении дневного лимита обращений к Cloudflare Workers AI (`CF_DAILY_BUDGET`, дефолт 300) бот автоматически переключается на локальные/фолбэк-пути без отказа пользователю:
  - ASR → локальный faster-whisper (транскрипция продолжается, качество модели `base`);
  - LLM-структурирование → тихий фолбэк на сырой текст (текст возвращается без разметки);
  - Действия «Кратко»/«Перевести» → понятное сообщение «Дневной бесплатный лимит исчерпан, попробуйте завтра.» (локальной LLM-замены нет).
  - После 00:00 UTC бюджет восстанавливается автоматически без ручного вмешательства.
  - Переход в деградацию логируется (`docker logs`) для наблюдаемости.
- **Новый документ `docs/listing.md`.** Готовый текст для ручной подачи бота в каталоги (BotoStore, TeleHunt и аналогичные): название, короткое и полное описание на русском и английском, категории, теги/ключевые слова. Подача — ручной шаг владельца (зафиксирован в чек-листе деплоя).

### Улучшения

- **Усиление ключевых слов в метаданных бота** (`BOT_DESCRIPTION`, `BOT_SHORT_DESCRIPTION` в `handlers/commands.py`): добавлены «транскрипция», «OCR», «голос в текст», «перевод», «RU/EN» под поиск Telegram. Лимиты соблюдены (description: 301 символ ≤ 512; short: 65 символов ≤ 120). Набор команд не изменился.
- **Sentinel `BUDGET_EXCEEDED` вынесен в `services/sentinel.py`.** Осознанное архитектурное решение: синглтон-объект отделён от `services/llm` для переиспользования. Обратная совместимость сохранена — `from services.llm import BUDGET_EXCEEDED` продолжает работать.

### Исправления

- Нет багфиксов. Все изменения — новая функциональность и усиление метаданных.

## Изменения публичного контракта

Публичный контракт 1.0.0 (ADR-010) **сохраняется** — релиз MINOR:

- Команды (`/start`, `/help`, `/stats`), входные каналы, формат ответа (`send_result`), inline-действия (`act:sum`/`act:tr`) — без изменений.
- **Новое поведение при исчерпании дневного бюджета** (обратимо-совместимое, без отказа): ASR → локальный whisper; структурирование → сырой текст; «Кратко»/«Перевести» → сообщение «Дневной бесплатный лимит исчерпан, попробуйте завтра.».
- **Новая опциональная env `CF_DAILY_BUDGET`** (целое, дефолт 300): несекретная конфигурация; отсутствие или некорректное значение не ломает старт бота.
- **Миграция БД:** добавляется таблица `cf_usage` через `CREATE TABLE IF NOT EXISTS` в существующем файле `STATS_DB_PATH` (тот же volume `/opt/apps/textify/data`) — обратно совместимо, ручных миграций не требуется.
- Профиль поставки «бот без HTTP-порта» (ADR-001) сохранён без изменений: long-polling, без `ports:`/Traefik/`edge`, образ из GHCR, `restart: unless-stopped`, пиннинг Telegram, volume данных.

## Известные ограничения

- Overshoot счётчика при конкурентных CF-вызовах: несколько корутин, прошедших `allow` до `consume`, каждая запишет инкремент. На ivahub (единицы одновременных запросов) несущественно; допускается осознанно (ADR-011 Решение 6), бюджет консервативен.
- Индикатор остатка дневного бюджета (например, в `/stats`) не введён — деградация прозрачна через `docker logs`; явная индикация запланирована при необходимости.
- При длительном сбое SQLite (fail-open) страховка бюджета временно неактивна, но бот продолжает работать; сбой логируется.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-011.md`
- ADR: `adrs/adr-011.md`
- Спецификация: `releases/release-spec-v1.1.0.md`
- Исходное требование: `requirements/req-textify-011.md`

## Проверка

- Линт `ruff check .` — все проверки прошли без замечаний.
- Автотесты `pytest -q` — **242 passed, 3 skipped** (skipped: 3 OCR-теста с реальным Tesseract — пропущены по отсутствию системного бинарника на Windows; на VPS с `tesseract-ocr` пройдут).
- КП-1..КП-16 проверены на уровне кода и документов:
  - КП-1: `services/budget.py`, таблица `cf_usage` в SQLite, `init_cf_usage_db()` в `bot.py`.
  - КП-2: гейт только на CF-ветках `transcribe`/`structure`/`llm`; локальные пути (`ASR_PROVIDER=local`, Groq, Tesseract-OCR) счётчик не трогают.
  - КП-3: атомарный UPSERT, WAL, `busy_timeout`, `asyncio.to_thread` — по образцу `services/stats.py`; тест на конкурентность (10 параллельных `consume`) проходит.
  - КП-4: счётчик ведётся по UTC-дате; тест `test_date_rollover_resets_counter` — зелёный.
  - КП-5: дефолт 300, `_DEFAULT_CF_DAILY_BUDGET` в `config.py`; нечисловое/неположительное → 300 + warning; плейсхолдер в обоих `.env.example`.
  - КП-6: штатный режим не изменён — подтверждено всей существующей тест-базой (нет регрессий).
  - КП-7: при `allow=False` CF не вызывается — подтверждено тестами `test_transcribe_cf_budget_exhausted_degrades_to_local`, `test_structure_cf_budget_exhausted_returns_raw`, `test_summarize_cf_budget_exhausted_returns_sentinel`, `test_translate_cf_budget_exhausted_returns_sentinel`.
  - КП-8: деградация ASR → `_transcribe_local` под `HEAVY_LOCAL_SEMAPHORE`; тест `test_transcribe_cf_budget_exhausted_degrades_to_local`.
  - КП-9: деградация структурирования → `return raw_text`; тест `test_structure_cf_budget_exhausted_returns_raw`.
  - КП-10: `handlers/actions.py` возвращает точное сообщение «Дневной бесплатный лимит исчерпан, попробуйте завтра.»; тесты `test_handle_action_budget_exceeded_message`, `test_handle_action_budget_exceeded_translate`.
  - КП-11: `logger.warning(...)` в каждой точке деградации; тесты `test_transcribe_cf_budget_exhausted_warning_logged`, `test_structure_cf_exhausted_warning_logged`, `test_summarize_cf_exhausted_warning_logged`, `test_translate_cf_exhausted_warning_logged`.
  - КП-12: fail-open — `cf_budget_allow` возвращает `True` при сбое БД; тест `test_allow_fail_open_on_db_error`; `cf_budget_consume` не бросает исключение — тест `test_consume_no_raise_on_db_error`.
  - КП-13: `deploy/docker-compose.yml` без изменений профиля поставки; только `CF_DAILY_BUDGET` добавлен в `deploy/.env.example`.
  - КП-14: `len(BOT_DESCRIPTION)=301 ≤ 512`, `len(BOT_SHORT_DESCRIPTION)=65 ≤ 120`; тесты `test_bot_description_within_limit`, `test_bot_short_description_within_limit`, `test_bot_description_contains_keywords`.
  - КП-15: `docs/listing.md` создан; тесты `test_listing_md_exists`, `test_listing_md_has_required_sections`.
  - КП-16: ручной шаг подачи листинга зафиксирован в чек-листе деплоя `releases/release-spec-v1.1.0.md` (раздел «Чек-лист готовности»).
- Frontend/Playwright: не применимо — Textify является Telegram-ботом (long-polling) без web-UI и HTTP-фронтенда. e2e-тесты на Playwright не требуются; release gate GitHub Actions для e2e не создаётся.
- КП-7..КП-11 в части живого продакшн-поведения (сброс по UTC, деградация при реальном исчерпании, видимость в `docker logs`) верифицируются после деплоя (ОВ-7).
