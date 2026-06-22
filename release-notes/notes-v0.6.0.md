# Release Notes v0.6.0

- **Дата:** 2026-06-22
- **Тип релиза:** minor

## Кратко

Textify теперь ведёт учёт аудитории: каждое обращение пользователя фиксируется сквозным
outer-middleware aiogram без правки существующих хендлеров. Накопленная статистика хранится
в SQLite на персистентном volume и переживает передеплой. Владелец бота получает команду
`/stats` для просмотра сводки.

## Что нового

### Возможности

- **Учёт пользователей через outer-middleware** (`middlewares/stats.py`). На каждое входящее
  сообщение один раз (до хендлеров) фиксируется факт обращения: `user_id`, тип сообщения
  (command / photo / audio / text / other), время первого и последнего обращения. Содержимое
  сообщений и распознанный текст не сохраняются.
- **Команда `/stats` для администратора.** Выводит: число уникальных пользователей, суммарное
  число сообщений, разбивку по типам (фото/изображения, аудио/голос, текст, команды, прочее),
  дату первого и дату последнего обращения (UTC). Не-администратор получает ответ
  «Команда недоступна.» без раскрытия данных.
- **Персистентный сервис учёта** (`services/stats.py`): SQLite с WAL, `busy_timeout=5000 мс`,
  соединение-на-операцию; все вызовы — через `asyncio.to_thread` (не блокируют event loop).

### Улучшения

- Тихая деградация учёта: сбой записи в БД логируется и проглатывается; основная функция
  (OCR/аудио/текст/ответ пользователю) выполняется штатно.
- `config.py` расширен двумя опциональными переменными: `ADMIN_USER_ID` (авторизация `/stats`)
  и `STATS_DB_PATH` (путь к файлу БД, дефолт `/app/data/stats.db`). Нечисловое значение
  `ADMIN_USER_ID` не ломает старт бота — логируется предупреждение и игнорируется.
- `bot.py`: инициализация схемы БД (`init_db()`) и регистрация `StatsMiddleware` на
  `dp.message.outer_middleware` при старте.

## Изменения публичного контракта

- **Новая команда `/stats`** — только для администратора. Не-администратору — короткий отказ.
- **Новые переменные окружения:**
  - `ADMIN_USER_ID` — опциональна; без неё `/stats` недоступна никому.
  - `STATS_DB_PATH` — опциональна; дефолт `/app/data/stats.db`.
- **Первое персистентное состояние.** Осознанное расширение профиля поставки ADR-001 (см.
  ADR-006): добавлен локальный файловый volume, внешних БД/Redis/портов не добавляется.
  Профиль поставки (long-polling, без `ports:`/Traefik/`edge`, образ из GHCR,
  `restart: unless-stopped`) сохранён.

Миграция для эксплуатирующего инженера — **обязательные шаги на сервере перед деплоем:**

```bash
mkdir -p /opt/apps/textify/data
chown -R 10001:10001 /opt/apps/textify/data
```

В `.env` на ivahub добавить:

```
ADMIN_USER_ID=33030141
```

## Изменения артефактов поставки

- **`Dockerfile`:** `appuser` создаётся с фиксированным `UID/GID 10001:10001`; каталог
  `/app/data` создаётся и передаётся во владение `appuser` на случай запуска без bind-mount.
- **`deploy/docker-compose.yml`:** добавлен `volumes: ["/opt/apps/textify/data:/app/data"]`.
  Профиль в остальном без изменений.
- **`.env.example` и `deploy/.env.example`:** добавлен плейсхолдер `ADMIN_USER_ID=<telegram_user_id>`.

## Известные ограничения

- **КП-9 (персистентность после передеплоя)** — подтверждается только деплоем на ivahub; в
  локальной среде не проверяется. Требует выполнения шагов `mkdir`/`chown` на сервере и
  наличия `ADMIN_USER_ID` в `.env`.
- **КП-12 (roadmap.md)** — обновление roadmap (`v0.6.0` → «Учёт пользователей и /stats»;
  «UX и устойчивость» → `v0.7.0`) выполняет maintainer отдельным коммитом в рамках `/deploy`.
- Один администратор (`ADMIN_USER_ID` — одно целое). Несколько администраторов — вне рамок.
- Учёт ведётся с момента внедрения; ретроспективные данные недоступны.
- `mypy` фиксирует 11 предсуществующих ошибок в `handlers/audio.py`, `handlers/image.py`,
  `services/preprocess.py`, `services/ocr.py`, `services/transcribe.py` — не из v0.6.0.
  Все файлы релиза (`services/stats.py`, `middlewares/`, `config.py`, `handlers/commands.py`,
  `bot.py`) mypy-чисты.

## Связанные документы

- BA-требования: `ba-req/ba-requirements-006.md`
- ADR: `adrs/adr-006.md`
- Спецификация: `releases/release-spec-v0.6.0.md`
- Исходное требование: `requirements/req-textify-006.md`

## Проверка

**Frontend:** отсутствует. Textify — Telegram-бот на long-polling (Python + aiogram).
Playwright/e2e не применимы; e2e-гейт в GitHub Actions не требуется.

**ruff:** зелёный, 0 ошибок.

**mypy:** 11 ошибок в предсуществующих файлах (pre-existing, не из v0.6.0). Файлы релиза
чисты.

**pytest:** 103 passed, 3 skipped (Tesseract/faster-whisper/cv2 пропускаются без бинарей —
не блокер).

**Критерии приёмки КП-1..КП-12:**

| Критерий | Статус | Как проверено |
|---|---|---|
| КП-1 | Выполнен | `StatsMiddleware` зарегистрирован как outer на `dp.message` в `bot.py`; существующие хендлеры не изменены; тесты `test_middleware_silent_degradation_on_error`, `test_middleware_no_from_user_still_calls_handler` |
| КП-2 | Выполнен | `record_message` создаёт строку с `first_seen==last_seen` при первом обращении; повторный вызов не меняет `first_seen`, обновляет `last_seen`; тесты `test_record_message_new_user`, `test_first_seen_immutable_last_seen_updated` |
| КП-3 | Выполнен | Параметризованный тест `test_record_message_increments_correct_column` проверяет все 5 типов; классификация — `test_classify_*` (11 тестов) |
| КП-4 | Выполнен | `cmd_stats` вызывает `get_stats()` и форматирует все поля на русском; тест `test_stats_admin_gets_report` |
| КП-5 | Выполнен | Не-админ → «Команда недоступна.»; тест `test_stats_non_admin_gets_denied` |
| КП-6 | Выполнен | `config.py`: `ADMIN_USER_ID` из `os.environ`, не хардкодится; плейсхолдер в `.env.example` и `deploy/.env.example`; тест `test_stats_no_admin_configured_gets_denied` |
| КП-7 | Выполнен | Схема БД (`services/stats.py`): только `user_id`, `first_seen`, `last_seen`, счётчики; содержимое сообщений отсутствует — проверено ревью кода |
| КП-8 | Выполнен | `record_message` и `get_stats` — `asyncio.to_thread`; ревью кода `services/stats.py` |
| КП-9 | Не проверено в этой среде | Персистентность после передеплоя подтверждается только деплоем на ivahub (volume + chown) |
| КП-10 | Выполнен | `deploy/docker-compose.yml` содержит `volumes: /opt/apps/textify/data:/app/data`; нет `ports:`/Traefik/`edge`; `restart: unless-stopped`; образ из GHCR — проверено ревью файла |
| КП-11 | Выполнен | `try/except` в `StatsMiddleware.__call__` + всегда вызывается `handler`; тест `test_middleware_silent_degradation_on_error` |
| КП-12 | Не выполнено в этом релизе | `roadmap.md` обновляет maintainer отдельным коммитом в `/deploy` (по явному заданию) |
