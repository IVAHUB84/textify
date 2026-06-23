# Release Notes v0.8.0

- **Дата:** 2026-06-23
- **Тип релиза:** minor

## Кратко

Основная транскрипция аудио переведена с локального faster-whisper на облачный Cloudflare Workers AI
`whisper-large-v3-turbo`: модель точнее, мультиязычнее и отвечает быстрее, а нагрузка на CPU/RAM
сервера при штатной работе снимается. Локальная модель сохраняется как надёжный фолбэк — при любом
сбое облака пользователь получает результат без ошибки.

## Что нового

### Возможности

- **Облачная транскрипция через Cloudflare Workers AI.** По умолчанию аудио распознаётся моделью
  `whisper-large-v3-turbo` через Cloudflare Workers AI — той же инфраструктурой, что используется для
  структурирования (ADR-005). Качество и скорость распознавания выше по сравнению с локальной
  моделью `base`; нагрузка на CPU/RAM ivahub в штатном пути снимается. Обращение к Cloudflare —
  нативный async через `httpx`, event loop не блокируется.

- **Переключатель `ASR_PROVIDER`.** Значение `cloudflare` (дефолт) направляет транскрипцию в
  Cloudflare; значение `local` возвращает к поведению v0.3.0–v0.7.0 (только локальная модель, без
  обращений к Cloudflare). Смена — конфигурацией, без правки кода.

- **Отдельная переменная модели `CF_WHISPER_MODEL`.** Модель ASR переопределяется независимо от
  `CF_MODEL` структурирования; дефолт — `@cf/openai/whisper-large-v3-turbo`.

### Улучшения

- **Фолбэк на локальную faster-whisper при любом сбое облака.** Сетевой сбой, таймаут, HTTP-ошибка
  (4xx/5xx), превышение лимита free-tier (429) или некорректный ответ — всё трактуется как сбой:
  оркестратор переходит на локальную модель и возвращает результат без ошибки пользователю. Факт
  фолбэка логируется (`logger.warning`/`logger.exception`) — деградация качества (turbo → base)
  видна в логах, а не скрыта.

- **Порог размера для крупных файлов.** Файлы крупнее 8 МБ сразу идут локальным путём без
  обращения к Cloudflare (base64 раздувает объём запроса на ~33 %; лимит Cloudflare AI run
  учтён заранее). Это не пользовательский лимит — файл не отвергается, распознаётся локально.

- **Единичная попытка, таймаут 60 с.** Без агрессивных ретраев — исчерпание free-tier бережётся;
  быстрый детерминированный фолбэк при любом зависании.

### Исправления

Нет — релиз вводит новую функциональность без изменения существующего поведения.

## Изменения публичного контракта

Изменение обратимо-совместимое (minor). Контракт канала аудио **не меняется**:

- Приём `message.voice` / `message.audio` / audio-документов, скачивание через запиннённый
  `api.telegram.org`, последующее структурирование (ADR-005) и отдача результата (ADR-007) работают
  как прежде при любом провайдере.
- Внутренняя сигнатура `transcribe(audio_bytes: bytes) -> str` сохранена; `handlers/audio.py` не
  знает о провайдере.

**Новые переменные окружения** (необязательны — имеют рабочие дефолты, бот стартует без них):

| Переменная | Дефолт | Описание |
|---|---|---|
| `ASR_PROVIDER` | `cloudflare` | Провайдер транскрипции: `cloudflare` или `local` |
| `CF_WHISPER_MODEL` | `@cf/openai/whisper-large-v3-turbo` | Модель ASR в Cloudflare Workers AI |

Новых обязательных секретов нет. `CF_ACCOUNT_ID` и `CF_API_TOKEN` переиспользуются из v0.5.0 (ADR-005);
они уже есть в `.env` на сервере. Миграция не требуется: дефолт `cloudflare` активируется
автоматически при отсутствии `ASR_PROVIDER` в `.env`.

## Известные ограничения

- Крупные файлы (> 8 МБ) не выигрывают от облака — распознаются локальной моделью `base`. Чанкинг
  аудио для облачного пути не реализован (технический долг).
- Без summary, перевода транскрипта, диаризации, таймкодов в ответе — вне scope релиза.
- Фолбэк молча снижает качество (turbo → base) — виден только в логах; пользователь не уведомляется.
- Суточные лимиты бесплатного tier Cloudflare вне контроля проекта; превышение (429) покрывается
  фолбэком на локальную модель.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-008.md`
- ADR: `adrs/adr-008.md`
- Спецификация: `releases/release-spec-v0.8.0.md`
- Исходное требование: `requirements/req-textify-008.md`

## Проверка

**Тесты:** `ruff check .` — All checks passed. `pytest -v` — **136 passed, 3 skipped, 0 failed**.
`CF_ACCOUNT_ID=fake CF_API_TOKEN=fake pytest tests/test_transcribe.py -v` — **20 passed** (изоляция
от окружения подтверждена: autouse-фикстура удаляет CF/ASR-переменные, сеть не задействована).
`mypy services/transcribe.py config.py --ignore-missing-imports` — Success: no issues found.

3 skipped — tesseract и faster-whisper не установлены в среде разработки; не являются провалом.

**Критерии приёмки КП-1..КП-12:**

- КП-1 ✅ При дефолте/`ASR_PROVIDER=cloudflare` запрос идёт на CF-эндпоинт с `whisper-large-v3-turbo`.
  Тест `test_cf_provider_success`, `test_default_provider_is_cloudflare`.
- КП-2 ✅ `CF_WHISPER_MODEL` из окружения используется в URL запроса к CF; дефолт `@cf/openai/whisper-large-v3-turbo`.
  Тест `test_cf_whisper_model_env_used_in_url`, `test_cf_whisper_model_env_var_is_independent_from_cf_model`.
- КП-3 ✅ Переключатель `ASR_PROVIDER`: `cloudflare` → CF, `local` → только локальная модель.
  Тест `test_asr_provider_local_skips_cf`, `test_default_provider_is_cloudflare`.
- КП-4 ✅ Фолбэк на локальный faster-whisper при сбоях: ConnectError, TimeoutException, HTTP 500, HTTP 429.
  Тест `test_cf_fallback_on_connect_error`, `test_cf_fallback_on_timeout`,
  `test_cf_fallback_on_http_status_error`, `test_cf_fallback_on_429`.
- КП-5 ✅ `ASR_PROVIDER=local` → Cloudflare не вызывается; локальный путь используется.
  Тест `test_asr_provider_local_skips_cf`.
- КП-6 ✅ Файлы > `_CF_MAX_AUDIO_BYTES` (8 МБ) идут локальным путём без обращения к Cloudflare.
  Тест `test_large_file_uses_local_skips_cf`.
- КП-7 ✅ Облачный путь — нативный async `httpx.AsyncClient`/`await`, без `to_thread` → event loop
  не блокируется. Тест `test_cloudflare_branch_uses_httpx_async_client_not_to_thread`.
- КП-8 ✅ Секреты читаются из окружения; `.env.example` и `deploy/.env.example` содержат плейсхолдеры
  `ASR_PROVIDER` и `CF_WHISPER_MODEL`; реальный `.env` в `.gitignore`, не коммитится.
- КП-9 ✅ Контракт канала аудио сохранён: `handlers/audio.py` не менялся, вызывает `transcribe` и
  `send_result` как прежде. `test_handle_voice_*`, `test_handle_audio_*` проходят.
- КП-10 ✅ Пустой `result.text` (2xx, тишина) → возвращается `""`, хендлер выдаёт `NO_SPEECH_MESSAGE`.
  Тест `test_cf_empty_text_returns_empty_string`, `test_no_speech_message_via_direct_answer`.
- КП-11 ✅ Профиль поставки ADR-001 сохранён: `Dockerfile`, `deploy/docker-compose.yml`,
  `.github/workflows/deploy.yml` не изменены; `requirements.txt` без изменений (httpx, faster-whisper
  уже присутствовали).
- КП-12 — Проверяется при `/deploy` на проде с реальным аудио и искусственным сбоем облака.
  Не блокирует этап release. (ОВ-3, НФТ-4 — достижимость CF Whisper с ivahub подтверждена вживую,
  HTTP 200.)

**Frontend:** Textify — Telegram-бот на long-polling, без HTTP-порта и без frontend-части (ADR-001).
Playwright/e2e не применимы по природе проекта — не пропуск, а отсутствие frontend.
