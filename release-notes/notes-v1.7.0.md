# Release Notes v1.7.0

- **Дата:** 2026-06-24
- **Тип релиза:** minor

## Кратко

Textify v1.7.0 вводит дневной лимит распознаваний на пользователя и мягкий subscription-gate на Telegram-канал. Хеви-пользователям, упирающимся в базовый лимит (3/день), бот предлагает подписаться на канал и тем самым поднять лимит до 30/день — без навязчивости и жёстких блокировок. Обычный пользователь лимит не замечает; dev/CI и текущий прод без заданного `REQUIRED_CHANNEL` работают как прежде.

## Что нового

### Возможности

- **Дневной счётчик распознаваний.** Новая таблица `daily_usage` в существующем `stats.db` (сервис `services/limits.py`): атомарный UPSERT под WAL, ключ суток — календарный день UTC. Счётчик переживает рестарт и редеплой контейнера; кнопки-действия над результатом (ADR-016) лимит не расходуют.

- **Два уровня лимита из env.** `DAILY_LIMIT_FREE` (дефолт 3) — для неподтверждённых пользователей; `DAILY_LIMIT_SUBSCRIBED` (дефолт 30) — для подтверждённых подписчиков. Оба значения валидируются при старте, при некорректном значении применяется дефолт с предупреждением в лог.

- **Мягкий subscription-gate (`services/subscription.py`).** При исчерпании базового лимита неподтверждённым пользователем в личке — дружелюбное предложение подписаться на канал `REQUIRED_CHANNEL` с inline-кнопками «Открыть канал» (url) и «Я подписался / Проверить». В группах — нейтральное сообщение без кнопок. Подписчик при исчерпании повышенного лимита получает нейтральное сообщение без ссылок.

- **Проверка подписки по кнопке «Проверить».** По нажатию — `getChatMember(channel, user_id)`: статусы `member`/`administrator`/`creator` → подписчик подтверждён, лимит повышен; иначе — вежливый отказ. Медиа повторно не обрабатывается — пользователю предлагается прислать заново (ADR-017, Решение 5A).

- **TTL-кэш статуса подписки.** In-memory `dict[user_id → expiry]`, TTL 600 с. В окне TTL повторный вызов `getChatMember` не происходит. По истечении кэша отписавшийся снова считается неподтверждённым.

- **Выключенный режим.** Если `REQUIRED_CHANNEL` не задан — `is_gate_enabled()` = False: gate полностью выключен, проверок подписки нет. Текущий прод/dev/CI не ломаются.

- **Деградация при сбое `getChatMember`.** Недоступность канала / бот не администратор / ошибка Telegram API → `False` + `logger.warning(..., exc_info=True)`, бот не падает и обслуживает пользователя в базовом режиме.

### Улучшения

- **Остаток лимита в `/start` (личка).** Строка «Сегодня доступно N из M распознаваний» добавлена к ответу `/start` в приватном чате. Сбой чтения учёта не роняет команду (try/except).

- **Агрегат лимита в `/stats` (админ).** В ответе `/stats` появились «Дневные распознавания (UTC сегодня)» и «Подтверждённых подписчиков в кэше». Существующие поля не меняются.

- **Точка учёта перед загрузкой.** `enforce_limit` вызывается до `bot.download` во всех обработчиках входящего медиа (`handlers/audio.py`, `handlers/image.py`, `handlers/group.py`) — при исчерпанном лимите медиа не скачивается и не распознаётся.

### Исправления

— (релиз вводит только новую функциональность; регрессий нет)

## Изменения публичного контракта

- **Новое поведение при заданном `REQUIRED_CHANNEL`:** каждое распознавание медиа расходует дневной лимит (базовый `DAILY_LIMIT_FREE` / подписчика `DAILY_LIMIT_SUBSCRIBED`); при исчерпании базового лимита в личке — мягкое предложение подписаться; в группе и для подписчика — нейтральное сообщение. Кнопки-действия над результатом лимит не расходуют.
- **При незаданном `REQUIRED_CHANNEL`:** поведение прода сохраняется; дневной лимит действует, но gate не строится и подписка не проверяется.
- **Команды:** `/start` дополнен строкой остатка лимита; `/stats` — агрегатом. Входные каналы, логика доставки результата, профиль поставки — **не меняются**.
- **Три новые переменные окружения:** `REQUIRED_CHANNEL` (строка, дефолт пусто), `DAILY_LIMIT_FREE` (int, дефолт 3), `DAILY_LIMIT_SUBSCRIBED` (int, дефолт 30) — в `.env.example` и `deploy/.env.example`.
- **Миграция БД:** не требуется — таблица `daily_usage` создаётся `init_limits_db()` на старте в существующем `stats.db`.
- Релиз — **MINOR**.

## Деплой-предусловие

При заданном `REQUIRED_CHANNEL` бот обязан быть **администратором** этого канала — иначе `getChatMember` вернёт ошибку, система деградирует к базовому лимиту без gate и залогирует предупреждение (КП-11). Предусловие включено в чек-лист `/deploy`.

## Известные ограничения

- TTL-кэш подписки хранится in-memory и теряется при рестарте контейнера. После рестарта пользователи временно на базовом лимите — по нажатию «Проверить» статус восстанавливается без ручного участия.
- Старые строки `daily_usage` за прошедшие сутки не чистятся автоматически. Объёмы малы (один ряд на пользователя в день), очистка — технический долг ADR-017.
- Mypy: 2 предсуществующие ошибки в `services/preprocess.py` (PIL-специфичные, с v0.4.0) — к v1.7.0 не относятся, новых ошибок не добавлено.

## E2E / Playwright

Textify — Telegram-бот без web UI. **E2E-тесты на Playwright неприменимы.** Release gate в `.github/workflows/` для e2e не создаётся.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-017.md`
- ADR: `adrs/adr-017.md`
- Спецификация: `releases/release-spec-v1.7.0.md`
- Опорные ADR: `adrs/adr-001.md`, `adrs/adr-006.md`, `adrs/adr-016.md`

## Проверка

**Автотесты:** `pytest -q` — **504 passed, 3 skipped**, 0 failed (14.65s).

Новые тест-файлы:
- `tests/test_limits_daily.py` — `init_limits_db`, `record_recognition` (создаёт строку count=1, инкрементирует), `usage_today` (новый user/новый день = 0), 10 параллельных инкрементов = 10 (атомарность), UTC-ключ формата YYYY-MM-DD, `total_today`.
- `tests/test_subscription.py` — `is_gate_enabled` (пустой/непустой), `is_subscriber_cached` (нет/живой/истёкший), `check_subscription` (статусы member/administrator/creator → True + кэш; left/kicked/restricted → False; исключение → False, не падает; выключенный gate → False без API-вызова), `channel_url` (username/числовой/пустой).
- `tests/test_gate.py` — `enforce_limit` (в пределах лимита → True + запись; исчерпан в личке gate-on → False + gate-клавиатура; исчерпан в группе → False + нейтральное сообщение без кнопок; gate-off → нейтральное; подписчик с 5/5 лимита = не превышен; сбой записи → не блокирует); callback `gate:chk` с подпиской → «подтверждена + пришлите»; без подписки → «не вижу»; InaccessibleMessage/None → show_alert.

Расширены:
- `tests/test_config.py` — дефолты 3/30, custom, невалидные значения дают дефолты, пустой/заданный `REQUIRED_CHANNEL`.
- `tests/test_limits.py`, `test_v120_group.py`, `test_v140_proactive_group.py` — `enforce_limit` замокан, существующие сценарии групп проходят без изменений.

**Линт:** `ruff check .` — All checks passed.

**Mypy:** 2 предсуществующие ошибки `services/preprocess.py` (PIL, с v0.4.0); новых ошибок не добавлено.

**Критерии приёмки (КП-1…КП-16):**

| КП | Способ проверки | Статус |
|---|---|---|
| КП-1: распознавание медиа уменьшает лимит на единицу | `test_gate.py::test_enforce_limit_within_limit_returns_true` — `record_recognition` вызывается; `test_limits_daily.py::test_record_increments_on_repeat` | ✅ |
| КП-2: кнопки-действия не расходуют лимит | `enforce_limit` не вызывается в `handlers/actions.py` (инспекция кода); тесты `actions.py` не включают `record_recognition` | ✅ |
| КП-3: лимиты из env, дефолты 3/30, валидация | `test_config.py::test_daily_limit_free_default`, `test_daily_limit_subscribed_default`, `test_daily_limit_free_invalid_string_uses_default`, `test_daily_limit_free_nonpositive_uses_default`, `test_daily_limit_subscribed_invalid_uses_default` | ✅ |
| КП-4: учёт персистентен между рестартами | SQLite `daily_usage` в примонтированном volume; `init_limits_db` — CREATE IF NOT EXISTS; данные не сбрасываются при рестарте контейнера | ✅ |
| КП-5: по наступлении новых суток лимит восстанавливается | `test_limits_daily.py::test_usage_today_new_day_returns_zero` — запись на «2000-01-01» даёт count=0 для сегодня | ✅ |
| КП-6: gate-сообщение с кнопками только при исчерпании базового лимита в личке | `test_gate.py::test_enforce_limit_exhausted_private_gate_enabled_shows_gate` — markup c `gate:chk` присутствует; `test_enforce_limit_within_limit_returns_true` — msg.answer не вызывается | ✅ |
| КП-7: «Проверить» с подпиской → подписчик подтверждён, лимит повышен | `test_gate.py::test_callback_gate_check_subscribed` — текст содержит «подтверждена»/«пришлите»; `test_subscription.py::test_check_subscription_subscribed_statuses` → кэш заполнен | ✅ |
| КП-8: «Проверить» без подписки → вежливый отказ, лимит не повышается | `test_gate.py::test_callback_gate_check_not_subscribed` — текст содержит «не вижу»/«подписк»; кэш пуст | ✅ |
| КП-9: при незаданном `REQUIRED_CHANNEL` gate выключен | `test_subscription.py::test_check_subscription_gate_disabled_returns_false_no_api` — API не вызывается; `test_gate.py::test_enforce_limit_exhausted_gate_disabled_shows_neutral` — нет reply_markup | ✅ |
| КП-10: кэш TTL 600 с; повторная проверка в окне не вызывает getChatMember | `test_subscription.py::test_check_subscription_caches_on_second_call_no_extra_api` — `get_chat_member.call_count == 1`; `test_ttl_expiry_makes_user_unconfirmed` | ✅ |
| КП-11: сбой getChatMember → деградация без падения | `test_subscription.py::test_check_subscription_api_exception_returns_false` — `result is False`, `is_subscriber_cached == False`; `logger.warning` вызывается | ✅ |
| КП-12: сообщения на русском, дружелюбные, без давления | инспекция кода `handlers/gate.py` — все строки на русском; тексты не содержат ультиматумов; `test_gate.py` проверяет наличие слов «завтра», «лимит», «подтверждена», «не вижу» | ✅ |
| КП-13: остаток лимита в `/start` | `handlers/commands.py::cmd_start` — строка `limit_line` формируется через `usage_today`/`is_subscriber_cached`; инспекция кода | ✅ |
| КП-14: поведение групп не ломается; gate в группах не навязывается | `test_gate.py::test_enforce_limit_exhausted_group_shows_neutral` — нет reply_markup; `test_v120_group.py`, `test_v140_proactive_group.py` — все зелёные | ✅ |
| КП-15: параллельные инкременты — атомарность | `test_limits_daily.py::test_concurrent_increments_atomic` — 10 параллельных `gather` → count=10 | ✅ |
| КП-16: плейсхолдеры в .env.example и deploy/.env.example | инспекция `.env.example`, `deploy/.env.example` — `REQUIRED_CHANNEL=`, `DAILY_LIMIT_FREE=3`, `DAILY_LIMIT_SUBSCRIBED=30` присутствуют | ✅ |
