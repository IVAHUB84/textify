import time
from collections import OrderedDict

CACHE_MAX_SIZE = 500
CACHE_TTL_SECONDS = 3600

# Ключ (chat_id, message_id): message_id уникален только в пределах чата,
# поэтому для изоляции между чатами необходим составной ключ.
_cache: OrderedDict[tuple[int, int], tuple[str, float]] = OrderedDict()


def put(chat_id: int, message_id: int, text: str) -> None:
    key = (chat_id, message_id)
    # Удаляем просроченные записи с начала (они старейшие) до первой живой.
    now = time.monotonic()
    for k in list(_cache.keys()):
        _, ts = _cache[k]
        if now - ts > CACHE_TTL_SECONDS:
            del _cache[k]
        else:
            break
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = (text, now)
    while len(_cache) > CACHE_MAX_SIZE:
        _cache.popitem(last=False)


def get(chat_id: int, message_id: int) -> str | None:
    key = (chat_id, message_id)
    entry = _cache.get(key)
    if entry is None:
        return None
    text, ts = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return text
