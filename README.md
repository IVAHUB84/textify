# Textify

Telegram-бот, который **бесплатно** превращает голосовые/аудио и изображения в чистый структурированный текст.

- Аудио → текст: распознавание речи через [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (локально, офлайн).
- Картинки → текст: OCR через [Tesseract](https://github.com/tesseract-ocr/tesseract) (`pytesseract`).
- Структурирование: распознанный текст приводится к читаемому виду (заголовки, списки, ключевые пункты) через [Groq](https://groq.com/) free API.
- Языки контента: **русский + английский** (Whisper определяет язык автоматически, для OCR подключены пакеты `rus` + `eng`).

Бот: [@YourTextifyBot](https://t.me/YourTextifyBot).

## Как это работает

```
Telegram (голос / аудио / фото)
        │
        ▼
   aiogram (bot.py)
        │
   ┌────┴─────────────┐
   ▼                  ▼
audio (faster-whisper)  image (Tesseract OCR)
   └────┬─────────────┘
        ▼
  Groq API — структурирование текста
        │
        ▼
  ответ пользователю (Markdown)
```

## Планируемая структура

```
Textify/
  bot.py                # точка входа, aiogram
  handlers/
    audio.py            # голос/аудио -> faster-whisper
    image.py            # фото -> Tesseract OCR
  services/
    transcribe.py       # обёртка над faster-whisper
    ocr.py              # обёртка над pytesseract
    structure.py        # Groq API -> структурированный текст
  requirements.txt
  .env                  # секреты (НЕ коммитится)
  .env.example          # шаблон переменных
```

> Структура актуальна начиная с v0.3.0. Документация workflow и артефакты (`adrs/`, `ba-req/`, `releases/` и т.д.) описаны в [`CLAUDE.md`](./CLAUDE.md).

## Окружение

### Системные зависимости (VPS, Linux)

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
```

Tesseract — для OCR. Декодирование аудио идёт через пакет `av` (транзитивная зависимость faster-whisper), системный `ffmpeg` не требуется.

### Python

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Переменные окружения

Скопировать `.env.example` → `.env` и заполнить:

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEY` | Ключ Groq free API для структурирования |

`.env` покрыт `.gitignore` — секреты в репозиторий не попадают.

## Запуск

```bash
python bot.py
```

## Разработка через workflow

Проект использует многоагентный workflow Claude Code (агенты BA → архитектор → разработчик → ревьюер → тестировщик → мейнтейнер → lead). Соглашения, команды (`/ba`, `/adr`, `/implement`, `/review`, `/release`, `/deploy`, `/lead`) и принципы описаны в [`CLAUDE.md`](./CLAUDE.md).

Первый цикл:

```
1. requirements/req-textify-001.md   (описать задачу вручную)
2. /ba 001
3. /adr 001 v0.1.0
4. /implement v0.1.0
5. /review v0.1.0
6. /release v0.1.0
7. /deploy v0.1.0       (после подтверждения)
```
