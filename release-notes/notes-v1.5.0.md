# Release Notes v1.5.0

- **Дата:** 2026-06-23
- **Тип релиза:** minor

## Кратко

Textify v1.5.0 переходит к прогрессивному раскрытию результата в личных чатах: вместо немедленной «стены текста» бот присылает короткую суть (1–2 предложения) с кнопками «Показать полностью» и «Кратко» — детали выдаются лениво, только по запросу. Кнопка «Перевести» и функция перевода удалены. Группы сохраняют прежнюю немедленную выдачу полного текста, но без кнопки «Перевести».

## Что нового

### Возможности

- **Прогрессивное раскрытие в личке.** При успешно распознанном голосовом/аудио/изображении бот первым сообщением присылает суть (1–2 предложения на языке оригинала) с двумя кнопками: «Показать полностью» и «Кратко». Полный структурированный текст и саммари формируются только по нажатию соответствующей кнопки.

- **In-memory LRU+TTL кэш (`services/result_cache.py`).** Новый модуль хранит исходный распознанный текст по ключу `(chat_id, message_id)` для callback-обработчиков. Максимальный размер — 500 записей, TTL — 1 час. Заменяет прежнюю схему чтения `callback.message.text` (которое теперь содержит суть, а не полный текст).

- **LLM-операция `summarize_gist` (`services/llm.py`).** Новая асинхронная операция генерации сути на языке оригинала — один вызов CF Workers AI, тот же бюджетный гейт, что у `summarize`/`structure_text`.

### Улучшения

- **Деградация при недоступности LLM/бюджета.** При исчерпании дневного CF-бюджета или любом сбое операции `summarize_gist` бот присылает понятное служебное превью («Суть недоступна (дневной лимит). Доступны «Показать полностью» и «Кратко».» или аналог) и рабочие кнопки — без падения и потери медиа.

- **Группы: одна кнопка «Кратко».** В групповом режиме прежняя немедленная выдача полного текста сохраняется; кнопка «Перевести» убрана, клавиатура теперь состоит из одной кнопки «Кратко» (`act:sum`). Источник текста для кнопки «Кратко» — тот же кэш по `message_id`.

- **Ленивый расчёт «Полностью»/«Кратко».** Операции `structure_text` и `summarize` вызываются только по тапу, а не на каждое входящее медиа, что частично компенсирует добавленный CF-вызов «сути».

### Исправления

- **Удалена кнопка «Перевести» и функция `translate`.** Из `services/llm.py` удалены: `translate`, `_TRANSLATE_SYSTEM`, `_has_cyrillic`, `_target_language`. Из `handlers/actions.py` удалены: `handle_translate`, `_CB_TRANSLATE`. `__all__` обновлён: `["BUDGET_EXCEEDED", "summarize", "summarize_gist"]`.

- **Источник текста для кнопок.** Callback-обработчики «Показать полностью» и «Кратко» теперь читают исходный текст из кэша по `message_id`, а не из `callback.message.text` (которое теперь содержит суть или служебное превью).

## Изменения публичного контракта

Контракт 1.0.0 (ADR-010) — раздел «Inline-действия» и форма немедленной выдачи лички:

- **Немедленная выдача (личка):** теперь суть (1–2 предложения), а не полный текст.
- **Inline-действия (личка):** «Показать полностью» (`act:full`) + «Кратко» (`act:sum`).
- **Inline-действия (группы):** только «Кратко» (`act:sum`).
- **«Перевести» (`act:tr`) и функция `translate` — удалены безвозвратно.** Клиентский код, опиравшийся на наличие кнопки «Перевести», перестанет её получать.
- **Источник текста для кнопок:** in-memory кэш `(chat_id, message_id) → исходный текст`; при отсутствии/истечении записи — сообщение «Текст недоступен», без падения.

Входные каналы, команды `/start`/`/help`/`/stats`, формат отдачи `send_result`, профиль поставки — **не меняются**. Миграция БД не требуется (кэш — in-memory). Релиз — MINOR.

## Известные ограничения

- In-memory кэш не переживает рестарт процесса: повторный тап по кнопке после рестарта бота даёт «Текст недоступен» — ожидаемое поведение, не ошибка. TTL — 1 час; сообщения старше часа теряют кнопки.
- Дополнительный LLM-вызов «суть» на каждое входящее медиа в личке сверх `structure_text` расходует CF-бюджет (`CF_DAILY_BUDGET`). Ленивый расчёт «Полностью»/«Кратко» частично компенсирует это — эффект нейтрален при умеренном трафике.
- Повторные тапы «Показать полностью» / «Кратко» формируют новый ответ каждый раз (идемпотентность не реализована — отдельная итерация).
- Прогрессивное раскрытие (суть + кнопки) в группах — вне рамок текущего релиза, отдельная итерация.

## E2E / Playwright

Textify — Telegram-бот без web UI. E2E-тесты на Playwright неприменимы. Release gate в `.github/workflows/` для e2e не создаётся.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-015.md`
- ADR: `adrs/adr-015.md`
- Спецификация: `releases/release-spec-v1.5.0.md`
- Опорные ADR: `adrs/adr-001.md`, `adrs/adr-002.md`, `adrs/adr-003.md`, `adrs/adr-005.md`, `adrs/adr-007.md`, `adrs/adr-009.md`, `adrs/adr-010.md`, `adrs/adr-011.md`, `adrs/adr-014.md`, `adrs/adr-015.md`

## Проверка

**Автотесты:** `pytest -q` — 388 passed, 3 skipped, 0 failed (9.19s). Включая 29 новых тестов `test_v150_progressive.py` и `test_result_cache.py`. Регрессионный набор: `test_actions.py`, `test_llm.py`, `test_reply.py`, `test_structure_handlers.py`, `test_v110_release.py`, `test_v120_group.py`, `test_v1_release.py`, `test_budget_gates.py` — все зелёные. Линт: `ruff check .` — All checks passed. Mypy: 6 предсуществующих ошибок в `preprocess.py` (2), `ocr.py`, `transcribe.py`, `test_ocr_v4.py`, `test_transcribe.py` — к v1.5.0 не относятся, новых ошибок нет.

**Критерии приёмки (КП-1…КП-12):**

| КП | Способ проверки | Статус |
|---|---|---|
| КП-1: аудио в личке → первое сообщение с сутью | `test_audio_progressive_sends_preview_with_two_buttons` — `answer` вызван с превью и `reply_markup` до любого вызова `structure_text` | ✅ |
| КП-2: изображение в личке → первое сообщение с сутью | `test_image_progressive_sends_preview_with_two_buttons` | ✅ |
| КП-3: ровно две кнопки «Показать полностью» и «Кратко»; «Перевести» нет | `test_actions_keyboard_progressive_two_buttons`, `test_actions_keyboard_no_translate_in_progressive` | ✅ |
| КП-4: «Показать полностью» → полный структурированный текст через `structure_text` + `send_result` | `test_handle_full_calls_structure_and_send_result` | ✅ |
| КП-5: «Кратко» → саммари через `summarize` | `test_handle_summarize_calls_summarize_and_send_result` | ✅ |
| КП-6: длинный текст через `send_result` (части/файл) | ревью `handlers/actions.py`: `handle_full` → `send_result(raw_msg, result)` без `reply_markup`; `send_result` использует ADR-007 (`split_text`, файл); тесты `test_reply.py` | ✅ |
| КП-7: нераспознанное медиа → прежнее служебное сообщение без превью/кнопок/кэша | `test_audio_progressive_empty_transcript_no_preview_no_cache`, `test_image_progressive_empty_ocr_no_preview_no_cache` | ✅ |
| КП-8: атрибуция/подпись (`ATTRIBUTION_FOOTER`) присутствует | ревью `services/reply.py` — сигнатура сохранена в `send_result`; `test_v1_release.py::test_chat_action_sender_actions_text_sends_result` | ✅ |
| КП-9: объёмы монотонно различимы (суть < кратко < полностью) | архитектурная проверка: суть — `summarize_gist` (1–2 предл.), кратко — `summarize` (3–5 пунктов), полностью — `structure_text` (полный Markdown); промпты `_GIST_SYSTEM`/`_SUMMARIZE_SYSTEM`/`_SYSTEM_PROMPT` закрепляют это | ✅ |
| КП-10: кнопка «Перевести» отсутствует во всех сценариях | grep по `act:tr`/`handle_translate`/`translate` в `services/`+`handlers/` — пусто; `test_actions_keyboard_no_translate_in_non_progressive`, `test_handle_translate_not_in_module`, `test_translate_not_in_module` | ✅ |
| КП-11: исчерпан CF-бюджет → понятное сообщение, без падения | `test_audio_progressive_gist_budget_exceeded_sends_service_preview` (суть), `test_handle_summarize_budget_exceeded` («Кратко»), `test_handle_full_calls_structure_and_send_result` (деградация `structure_text` — ADR-005) | ✅ |
| КП-12: повторные/некорректные нажатия → без падения; пустой кэш → «Текст недоступен» | `test_handle_full_cache_miss_shows_alert`, `test_handle_summarize_cache_miss_shows_alert` | ✅ |
