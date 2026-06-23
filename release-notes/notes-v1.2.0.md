# Release Notes v1.2.0

- **Дата:** 2026-06-23
- **Тип релиза:** minor

## Кратко

Textify v1.2.0 открывает главный канал органического роста: бот теперь обрабатывает медиа в группах и супергруппах по явному запросу — reply на голосовое, аудио или фото плюс команда `/textify` или упоминание `@YourTextifyBot`. Поведение в личке (контракт v1.0.0) не изменилось. Групповой ASR по умолчанию идёт локальным faster-whisper, не расходуя Cloudflare-бюджет лички.

## Что нового

### Возможности

- **Режим групп (reply + `/textify` или упоминание).** В чате типа `group` / `supergroup` бот реагирует только на явный триггер: пользователь делает reply на сообщение с голосовым, аудио, фото или аудио-документом и добавляет команду `/textify` (в т. ч. `/textify@YourTextifyBot`) либо упоминание `@YourTextifyBot`. Бот берёт медиа из `reply_to_message`, прогоняет через существующий пайплайн OCR/ASR → структурирование → `send_result` и отвечает **reply на исходное медиа** с кнопками «Кратко» / «Перевести». Без явного триггера бот в группе молчит — спама нет.
- **Групповой ASR — локальный путь по умолчанию (`GROUP_ASR_LOCAL=true`).** При включённом флаге (дефолт) групповые голосовые и аудио транскрибируются faster-whisper локально под глобальным семафором, не расходуя дневной CF-бюджет (ADR-011). При `GROUP_ASR_LOCAL=false` группы идут общим путём (CF + бюджет + фолбэк). OCR в группах всегда локальный (Tesseract).
- **Кнопки работают в группе.** Inline-действия «Кратко» / «Перевести» (ADR-009) функционируют в группах без изменений: `callback.message` доступен в группе, `actions.py` не завязан на тип чата.
- **Подсказка при вызове без контекста.** Если триггер (`/textify` или упоминание) пришёл без reply на поддерживаемое медиа, бот отвечает короткой подсказкой: «Ответьте этой командой на голосовое, аудио или фото с текстом.» — исключительно в ответ на адресованный запрос.

### Улучшения

- **Рефактор хендлеров медиа.** Логика «скачать → распознать → структурировать → send_result» вынесена в переиспользуемые функции `process_photo`, `process_image_document`, `process_audio`. Приватные хендлеры и групповой хендлер вызывают одни и те же функции — дублирования пайплайна нет. Функция `process_audio` принимает `force_local: bool = False`.
- **Сужение приватных хендлеров до `private`.** `handlers/image.py`, `handlers/audio.py`, `handlers/text.py` теперь обрабатывают сообщения только в чатах типа `private` (роутер-уровневый фильтр). В группах эти хендлеры не матчатся — исключается авто-обработка группового трафика.
- **`transcribe()` принимает `force_local: bool = False`.** При `force_local=True` функция сразу переходит в `_transcribe_local` под семафором, минуя CF и не инкрементируя `cf_usage`. Дефолтное поведение (CF + бюджет + фолбэк) полностью сохраняется.
- **Username бота из `Bot.get_me()` на старте.** Фильтр упоминания получает реальный username через API, без хардкода строки. Упоминание распознаётся по `entities` типа `mention` / `text_mention` — надёжно и регистронезависимо.

### Исправления

- Нет багфиксов. Все изменения — новая функциональность и рефактор.

## Изменения публичного контракта

Публичный контракт v1.0.0 (ADR-010) для **лички сохраняется полностью**: команды `/start` / `/help` / `/stats`, входные каналы (авто-обработка медиа без reply), формат `send_result`, inline-действия `act:sum` / `act:tr` — без изменений.

**Добавления (обратимо-совместимые, MINOR):**

- Бот реагирует в `group` / `supergroup` на новый триггер (reply на медиа + `/textify` или упоминание бота); ответ — reply на исходное медиа с кнопками через тот же `send_result`.
- Команда `/textify` распознаётся как триггер в группах; в меню бота (`BOT_COMMANDS`) **не отображается** (бесполезна в личке; обратимо при необходимости).
- Новый опциональный env `GROUP_ASR_LOCAL` (булев, `true/1/yes` → True, `false/0/no` → False; некорректное/пустое → дефолт `True`). Отсутствие переменной не ломает старт. Добавлен в `.env.example` и `deploy/.env.example`.

**Схема БД, профиль поставки ADR-001, новые зависимости:** не изменяются. Миграций нет.

## Известные ограничения

- Локальный ASR в группах медленнее и менее точен, чем Cloudflare large-v3-turbo; при всплеске голосовых сериализуется семафором (лимит 1 на ivahub). Приоритет — защита бесплатности и сервера.
- Паттерн «фото с подписью-упоминанием» (ФТ-4) в этот релиз не входит — запланировано к рассмотрению при появлении спроса.
- Виральная петля / рефералы / шеринг — v1.3.0.
- Статистика `/stats` не различает личку и группы — схема `user_stats` не меняется (ОВ-7, отложено).

## Ручные шаги деплоя

1. **Privacy mode в @BotFather.** Открыть @BotFather → выбрать бота → `Edit Bot` → `Group Privacy`. Нужно: бот получает **команды, упоминания и ответы на свои сообщения** (настройка «получать только команды/упоминания» — стандартное поведение после создания бота). Полное отключение privacy mode **не делать** — бот не должен получать весь трафик группы.
2. **Добавить бота в тестовую группу** и проверить:
   - reply + `/textify` на голосовое/фото → ответ с кнопками;
   - reply + `@YourTextifyBot` → то же;
   - голосовое без триггера → молчание;
   - `/textify` без reply → подсказка.
3. **`GROUP_ASR_LOCAL`** — опциональный env (дефолт `true`). Добавить в реальный `.env` на сервере только при необходимости сменить поведение.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-012.md`
- ADR: `adrs/adr-012.md`
- Спецификация: `releases/release-spec-v1.2.0.md`
- Исходное требование: `requirements/req-textify-012.md`

## Проверка

- Линт `ruff check .` — все проверки прошли без замечаний.
- Автотесты `pytest -q` — **295 passed, 3 skipped** (skipped: 3 OCR-теста с реальным Tesseract — пропускаются по отсутствию системного бинарника на Windows; на VPS с `tesseract-ocr` пройдут).
- Typecheck `mypy .` — 7 pre-existing ошибок (pytesseract/faster_whisper без стабов, preprocess.py PIL-типы, actions.py sentinel-тип); в рамках данного релиза не введены новые ошибки (в базе до релиза было 15 ошибок включая незафиксированные изменения; после реализации стало 7 — рефактор улучшил покрытие типами).
- Все 53 теста `tests/test_v120_group.py` зелёные, покрывают все критерии приёмки:
  - КП (авто-медиа без триггера не обрабатывается): `test_group_router_has_no_catch_all`, `test_image_router_blocks_group_chat`, `test_audio_router_blocks_group_chat`, `test_text_router_blocks_group_chat`.
  - КП (reply + `/textify` → обработка): `test_group_textify_command_voice_reply`, `test_group_textify_command_photo_reply`.
  - КП (reply + упоминание → обработка): `test_group_mention_audio_reply`, `test_group_mention_photo_reply`.
  - КП (триггер без reply/медиа → подсказка): `test_group_textify_no_reply_sends_hint`, `test_group_textify_reply_no_media_sends_hint`, `test_group_mention_no_reply_sends_hint`.
  - КП (регресс лички): `test_private_photo_handled_without_reply`, `test_private_voice_handled_without_reply`, `test_private_audio_handled_without_reply`, `test_private_text_stub_reply`.
  - КП (кнопки в группе): `test_group_result_has_actions_keyboard`, `test_group_callback_sum_works`, `test_group_callback_tr_works`.
  - КП (GROUP_ASR_LOCAL force_local): `test_group_asr_force_local_true`, `test_group_asr_force_local_false`, `test_transcribe_force_local_skips_cf`, `test_transcribe_force_local_false_uses_cf`.
  - КП (фильтр упоминания корректен): `test_mention_filter_*` (8 тестов).
  - КП (порядок роутеров): `test_bot_router_order`.
  - КП (config GROUP_ASR_LOCAL): 9 тестов с различными значениями env.
- Frontend/Playwright: не применимо — Textify является Telegram-ботом (long-polling, без HTTP-порта, без web-UI). E2e-тесты на Playwright не требуются; release gate GitHub Actions для e2e не создаётся.
- Артефакты поставки (Dockerfile, `deploy/docker-compose.yml`, `.github/workflows/deploy.yml`) не изменялись — профиль ADR-001 сохранён; `GROUP_ASR_LOCAL` добавлен в `deploy/.env.example`.
