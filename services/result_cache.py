import time
from collections import OrderedDict

CACHE_MAX_SIZE = 500
CACHE_TTL_SECONDS = 3600

# Ключ (chat_id, message_id): message_id уникален только в пределах чата,
# поэтому для изоляции между чатами необходим составной ключ.
_cache: OrderedDict[tuple[int, int], tuple[str, float]] = OrderedDict()
# Отдельный кэш для версии транскрипта с тайм-кодами (кнопка «Тайм-коды»).
_ts_cache: OrderedDict[tuple[int, int], tuple[str, float]] = OrderedDict()


def _put(store: "OrderedDict[tuple[int, int], tuple[str, float]]", chat_id: int, message_id: int, text: str) -> None:
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
    store[key] = (text, now)
    while len(store) > CACHE_MAX_SIZE:
        store.popitem(last=False)


def _get(store: "OrderedDict[tuple[int, int], tuple[str, float]]", chat_id: int, message_id: int) -> str | None:
    key = (chat_id, message_id)
    entry = store.get(key)
    if entry is None:
        return None
    text, ts = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        del store[key]
        return None
    store.move_to_end(key)
    return text


def put(chat_id: int, message_id: int, text: str) -> None:
    _put(_cache, chat_id, message_id, text)


def get(chat_id: int, message_id: int) -> str | None:
    return _get(_cache, chat_id, message_id)


def put_timestamps(chat_id: int, message_id: int, text: str) -> None:
    _put(_ts_cache, chat_id, message_id, text)


def get_timestamps(chat_id: int, message_id: int) -> str | None:
    return _get(_ts_cache, chat_id, message_id)
