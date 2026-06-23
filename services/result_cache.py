import json
import logging
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_MAX_SIZE = 500
CACHE_TTL_SECONDS = 3600
# Кэш байтов изображения (для кнопки «PDF») держим маленьким: на 1 vCPU/2 ГБ
# нельзя хранить 500 картинок. Только в памяти, без персистентности.
IMG_CACHE_MAX_SIZE = 50
_BUSY_TIMEOUT_MS = 5000

# Ключ (chat_id, message_id): message_id уникален только в пределах чата,
# поэтому для изоляции между чатами необходим составной ключ.
_cache: "OrderedDict[tuple[int, int], tuple[str, float]]" = OrderedDict()
# Сегменты транскрипции (start, end, text) для кнопок «Тайм-коды» и «Субтитры».
_seg_cache: "OrderedDict[tuple[int, int], tuple[Any, float]]" = OrderedDict()
# Байты исходного изображения для кнопки «PDF» (searchable PDF из фото).
_img_cache: "OrderedDict[tuple[int, int], tuple[bytes, float]]" = OrderedDict()

# Путь к SQLite для переживания рестартов. None → персистентность выключена
# (тесты и любые окружения без init_result_cache работают чисто в памяти).
_DB_PATH: str | None = None


def _put(
    store: "OrderedDict[tuple[int, int], tuple[Any, float]]",
    chat_id: int,
    message_id: int,
    value: Any,
    max_size: int = CACHE_MAX_SIZE,
) -> None:
    key = (chat_id, message_id)
    # Удаляем просроченные записи с начала (они старейшие) до первой живой.
    now = time.monotonic()
    for k in list(store.keys()):
        _, ts = store[k]
        if now - ts > CACHE_TTL_SECONDS:
            del store[k]
        else:
            break
    if key in store:
        store.move_to_end(key)
    store[key] = (value, now)
    while len(store) > max_size:
        store.popitem(last=False)


def _get(store: "OrderedDict[tuple[int, int], tuple[Any, float]]", chat_id: int, message_id: int) -> Any:
    key = (chat_id, message_id)
    entry = store.get(key)
    if entry is None:
        return None
    value, ts = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        del store[key]
        return None
    store.move_to_end(key)
    return value


# ---------------------------------------------------------------------------
# Персистентность (SQLite). Сквозная запись + загрузка на старте.
# ---------------------------------------------------------------------------


def init_result_cache(db_path: str) -> None:
    """Включает персистентность: создаёт таблицу и загружает свежие записи в память.

    Вызывается из bot.py на старте. Без вызова кэш остаётся чисто in-memory.
    """
    global _DB_PATH
    _DB_PATH = db_path
    try:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db_path)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS results (
                    chat_id    INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    kind       TEXT    NOT NULL,
                    payload    TEXT    NOT NULL,
                    created_at REAL    NOT NULL,
                    PRIMARY KEY (chat_id, message_id, kind)
                );
                """
            )
            con.commit()
            con.execute("DELETE FROM results WHERE created_at < ?", (time.time() - CACHE_TTL_SECONDS,))
            con.commit()
            rows = con.execute(
                "SELECT chat_id, message_id, kind, payload FROM results ORDER BY created_at"
            ).fetchall()
        finally:
            con.close()
    except Exception:
        logger.warning("init_result_cache: failed to init/load persistent cache", exc_info=True)
        return

    for chat_id, message_id, kind, payload in rows:
        if kind == "text":
            _put(_cache, chat_id, message_id, payload)
        elif kind == "seg":
            try:
                _put(_seg_cache, chat_id, message_id, json.loads(payload))
            except (ValueError, TypeError):
                continue


def _persist(kind: str, chat_id: int, message_id: int, payload: str) -> None:
    if _DB_PATH is None:
        return
    try:
        con = sqlite3.connect(_DB_PATH)
        try:
            con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            con.execute(
                """
                INSERT INTO results (chat_id, message_id, kind, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, message_id, kind)
                DO UPDATE SET payload = excluded.payload, created_at = excluded.created_at
                """,
                (chat_id, message_id, kind, payload, time.time()),
            )
            con.commit()
        finally:
            con.close()
    except Exception:
        logger.warning("result_cache: failed to persist %s entry", kind)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def put(chat_id: int, message_id: int, text: str) -> None:
    _put(_cache, chat_id, message_id, text)
    _persist("text", chat_id, message_id, text)


def get(chat_id: int, message_id: int) -> str | None:
    return _get(_cache, chat_id, message_id)


def put_segments(chat_id: int, message_id: int, segments: list) -> None:
    _put(_seg_cache, chat_id, message_id, segments)
    _persist("seg", chat_id, message_id, json.dumps(segments))


def get_segments(chat_id: int, message_id: int) -> list | None:
    return _get(_seg_cache, chat_id, message_id)


def put_image(chat_id: int, message_id: int, data: bytes) -> None:
    _put(_img_cache, chat_id, message_id, data, max_size=IMG_CACHE_MAX_SIZE)


def get_image(chat_id: int, message_id: int) -> bytes | None:
    return _get(_img_cache, chat_id, message_id)
