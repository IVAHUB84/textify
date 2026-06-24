# Release Notes v1.8.0

- **Дата:** 2026-06-24
- **Тип релиза:** minor

## Кратко

Textify v1.8.0 вводит реферальную награду — второй независимый рычаг роста поверх subscription-gate v1.7.0. Эффективный дневной лимит пользователя теперь складывается из базового уровня и бонуса за приглашённых друзей: `база + min(рефералы × REFERRAL_BONUS_PER, REFERRAL_BONUS_CAP)`. Бонус действует каждый день, начисляется независимо от подписки на канал и при нуле рефералов не меняет поведения v1.7.0.

## Что нового

### Возможности

- **Реферальный бонус к дневному лимиту.** Каждый подтверждённый реферал добавляет `+REFERRAL_BONUS_PER` (дефолт 3) распознаваний в сутки; суммарный бонус ограничен потолком `REFERRAL_BONUS_CAP` (дефолт 30). При 10 друзьях неподписчик получает `3 + 30 = 33` распознавания/день, подписчик — `30 + 30 = 60`. Бонус начисляется независимо от подписки и складывается с уровнем подписчика.

- **Два пути в gate-сообщении (личка, неподписчик).** При исчерпании эффективного лимита в личке неподтверждённый пользователь видит дружелюбный текст с двумя путями повышения лимита: подписаться на канал и пригласить друзей. Клавиатура: ряд 1 — «Открыть канал» (url) + «Пригласить друзей» (url share-ссылка); ряд 2 — «Я подписался / Проверить» (callback `gate:chk`, без изменений v1.7.0). В группах и у подписчиков — прежнее нейтральное сообщение без второго пути.

- **Расшифровка лимита в `/start`.** Строка остатка считается от эффективного лимита. При наличии бонуса (реферальный счётчик > 0) выводится дополнительная строка: «Лимит: N базовых + B за K друзей». При нуле рефералов расшифровка отсутствует и вывод визуально совпадает с v1.7.0.

### Улучшения

- **TTL-кэш числа рефералов на горячем пути (`services/referrals.py`).** In-memory кэш `dict[user_id → (count, expiry)]`, TTL 600 с по аналогии с кэшем подписки v1.7.0. На горячем пути (`enforce_limit`) повторные распознавания в окне TTL не порождают новый `SELECT COUNT(*)`. Точечная инвалидация в `record_referral`: при фиксации нового реферала запись пригласившего немедленно удаляется из кэша — рост числа рефералов отражается без ожидания TTL. Добавлена новая функция `cached_referral_count(user_id)`.

- **Чистая функция эффективного лимита (`services/limits.py`).** Синхронная `effective_daily_limit(base_limit, referral_count) -> int` переиспользуется и в `enforce_limit` (`handlers/gate.py`), и в `/start` (`handlers/commands.py`) — единый источник истины, нет расхождения формулы.

- **Конфигурация через env.** `REFERRAL_BONUS_PER` и `REFERRAL_BONUS_CAP` читаются паттерном лимитов v1.7.0: `os.environ.get`, `int()`, при ≤ 0 или нечисловом значении — дефолт + `logger.warning`.

### Исправления

— (релиз вводит только новую функциональность; регрессий нет)

## Изменения публичного контракта

- **Новое поведение:** дневной лимит = `база (v1.7.0) + min(рефералы × REFERRAL_BONUS_PER, REFERRAL_BONUS_CAP)`. При исчерпании эффективного лимита в личке неподписчик видит gate-сообщение с двумя путями и url-кнопкой «Пригласить друзей». В `/start` строка остатка учитывает эффективный лимит; при бонусе > 0 — расшифровка слагаемых.
- **При нуле рефералов** поведение идентично v1.7.0 — регрессии нет.
- **Команды:** `/start` расширен эффективным лимитом и опциональной расшифровкой. `/stats` — **не меняется** (реферальные метрики были с v1.3.0). Входные каналы, доставка результата, точка списания, профиль поставки — **не меняются**.
- **Миграция БД:** не требуется — таблица `referrals` существует с v1.3.0, новой схемы нет.
- **Две новые env-переменные:** `REFERRAL_BONUS_PER` (дефолт 3), `REFERRAL_BONUS_CAP` (дефолт 30) — опциональны; фича работает сразу после деплоя без явного задания.
- Релиз — **MINOR**.

## Известные ограничения

- TTL-кэш числа рефералов хранится in-memory и теряется при рестарте контейнера. После рестарта первое обращение к `enforce_limit` выполнит `COUNT` и заново заполнит кэш — ненаблюдаемо для пользователя.
- Уведомление пригласившему о новом реферале («по твоей ссылке пришёл друг, лимит вырос», ФТ-12) в v1.8.0 не включено (ADR-018, Решение 7A). Рост лимита пригласившему виден в его `/start`. Задача перенесена в технический долг.
- Анти-фрод по мультиаккаунтам не реализован (опора на `referred_id` PRIMARY KEY + `CAP`); серьёзный анти-фрод — вне рамок (ДОП-2).
- Mypy: 2 предсуществующие ошибки в `services/preprocess.py` (PIL, с v0.4.0) — к v1.8.0 не относятся, новых ошибок не добавлено.

## E2E / Playwright

Textify — Telegram-бот без web UI. **E2E-тесты на Playwright неприменимы.** Release gate в `.github/workflows/` для e2e не создаётся.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-018.md`
- ADR: `adrs/adr-018.md`
- Спецификация: `releases/release-spec-v1.8.0.md`
- Опорные ADR: `adrs/adr-001.md`, `adrs/adr-006.md`, `adrs/adr-017.md`

## Проверка

**Автотесты:** `pytest` — **535 passed, 3 skipped**, 0 failed.

Новые и расширенные тест-файлы:

- `tests/test_referral_bonus.py` (новый) — `effective_daily_limit`: `r=0 → base`; линейный рост `r·PER < CAP`; потолок CAP; обе базы (FREE/SUBSCRIBED). Кэш `cached_referral_count`: первый вызов делает COUNT и кэширует; повторный в окне TTL — не делает COUNT (счётчик вызовов `count_referrals` = 1); истёкший TTL — пересчитывает; `record_referral` инвалидирует запись пригласившего; сбой COUNT → возвращает 0, не падает; нет рефералов → 0.
- `tests/test_gate.py` (расширен) — `enforce_limit` с рефералами: неподписчик с 2 рефералами, used=9 (=effective) → заблокирован; used=7 < 9 → проходит; подписчик с 3 рефералами, used=35 < 39 → проходит; gate-сообщение в личке содержит кнопку «Пригласить друзей» и callback `gate:chk`; текст содержит оба пути + «+3»; нуль рефералов → поведение v1.7.0; сбой `cached_referral_count` → бонус 0, не падает; группа с рефералами → нейтральное без markup.
- `tests/test_config.py` (расширен) — `REFERRAL_BONUS_PER`/`REFERRAL_BONUS_CAP`: дефолты 3/30; custom; нечисловое/≤ 0 → дефолт.
- `tests/test_handlers.py` (расширен) — `/start` с 2 рефералами: `«из 9»`, `«3 базовых»`, `«+ 6 за»`, `«2 друга»`; 0 рефералов: `«из 3»`, нет «базовых»/«друзей»; подписчик с 4 рефералами: `«из 42»`, `«30 базовых»`, `«+ 12 за»`, `«4 друга»`.

**Линт:** `ruff check .` — All checks passed.

**Mypy:** `mypy . --ignore-missing-imports` — 2 предсуществующие ошибки `services/preprocess.py` (PIL, с v0.4.0); новых ошибок не добавлено.

**Критерии приёмки (КП-1…КП-14):**

| КП | Способ проверки | Статус |
|---|---|---|
| КП-1: эффективный лимит = база + min(r×PER, CAP) | `test_referral_bonus.py` — `test_effective_limit_linear_growth`, `test_effective_limit_cap_applied`, `test_effective_limit_subscribed_base_plus_bonus` | ✅ |
| КП-2: бонус независим от подписки, рычаги складываются | `test_gate.py::test_enforce_limit_subscribed_user_with_referrals_gets_bonus` — подписчик с 3 рефералами, effective=39, used=35 → проходит | ✅ |
| КП-3: потолок CAP ограничивает бонус | `test_referral_bonus.py` — `test_effective_limit_cap_applied`: r=10/11/100 → 3+30=33; `test_effective_limit_subscribed_base_plus_bonus`: r=10/11 → 30+30=60 | ✅ |
| КП-4: бонус действует каждый день (постоянная награда) | Архитектурно: `cached_referral_count` читается при каждом `enforce_limit`; счётчик `daily_usage` сбрасывается по дневному ключу UTC (v1.7.0); не разовый бонус (инспекция кода) | ✅ |
| КП-5: REFERRAL_BONUS_PER/CAP из env, дефолты 3/30, валидация | `test_config.py::test_referral_bonus_per_default`, `test_referral_bonus_cap_default`, `test_referral_bonus_per_invalid_string_uses_default`, `test_referral_bonus_cap_nonpositive_uses_default` | ✅ |
| КП-6: нуль рефералов → поведение v1.7.0, регрессии нет | `test_referral_bonus.py::test_effective_limit_zero_referrals_returns_base`; `test_gate.py::test_enforce_limit_zero_referrals_same_as_v170` — used=3 >= 3 → blocked | ✅ |
| КП-7: допуск/отказ и остаток в enforce_limit — по эффективному лимиту | `test_gate.py::test_enforce_limit_free_user_with_referrals_gets_bonus` (used=9=effective → False); `test_enforce_limit_free_user_with_referrals_within_effective_limit` (used=7<9 → True) | ✅ |
| КП-8: бонус по existing count_referrals, новой таблицы нет | `cached_referral_count` вызывает `count_referrals` → `_count_referrals_sync` → SELECT из таблицы `referrals` v1.3.0; новой таблицы не заводится (инспекция кода) | ✅ |
| КП-9: /start — эффективный лимит, расшифровка при бонусе, реф-ссылка сохранена | `test_handlers.py::test_start_shows_effective_limit_with_bonus` — «из 9», «3 базовых», «+ 6 за», «2 друга»; `test_start_subscribed_with_referrals_shows_effective` — «из 42», «30 базовых», «+ 12 за» | ✅ |
| КП-10: при исчерпании в личке неподписчику — два пути и кнопка «Пригласить» | `test_gate.py::test_enforce_limit_gate_message_has_invite_button` — кнопка «Пригласить» + `gate:chk`; `test_enforce_limit_gate_message_has_two_paths_text` — «подпишитесь»/«канал» + «пригласите»/«друзей» + «+3» | ✅ |
| КП-11: плейсхолдеры REFERRAL_BONUS_PER/CAP в .env.example и deploy/.env.example | Инспекция обоих файлов — `REFERRAL_BONUS_PER=3`, `REFERRAL_BONUS_CAP=30` с комментариями присутствуют | ✅ |
| КП-12: сбой COUNT → бонус 0, распознавание не падает | `test_referral_bonus.py::test_cached_referral_count_db_failure_returns_zero` — возвращает 0; `test_gate.py::test_enforce_limit_referral_count_failure_falls_back_to_base` — Exception в cached_referral_count → результат True, запись выполнена | ✅ |
| КП-13: повторные распознавания в TTL не порождают COUNT | `test_referral_bonus.py::test_cached_referral_count_second_call_uses_cache` — `count_referrals` вызван ровно 1 раз при двух `cached_referral_count`; `test_cached_referral_count_expired_ttl_requeries` — истёкший TTL пересчитывает | ✅ |
| КП-14 (ФТ-12): уведомление пригласившему — отложено | ADR-018, Решение 7A: ФТ-12 не входит в v1.8.0; КП-14 переносится в технический долг | — не в этом релизе |
