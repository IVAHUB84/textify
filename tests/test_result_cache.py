"""Тесты services/result_cache.py."""
import time
import pytest

import services.result_cache as cache_mod
from services.result_cache import get, get_segments, put, put_segments


def _clear_cache():
    cache_mod._cache.clear()
    cache_mod._seg_cache.clear()


@pytest.fixture(autouse=True)
def clear():
    _clear_cache()
    yield
    _clear_cache()


def test_put_get_round_trip():
    put(1, 1, "текст")
    assert get(1, 1) == "текст"


def test_get_unknown_id_returns_none():
    assert get(9999, 9999) is None


def test_get_after_overwrite_returns_latest():
    put(1, 1, "первый")
    put(1, 1, "второй")
    assert get(1, 1) == "второй"


def test_eviction_on_size_limit():
    limit = cache_mod.CACHE_MAX_SIZE
    for i in range(limit + 1):
        put(1, i, f"text_{i}")

    assert get(1, 0) is None
    assert get(1, limit) == f"text_{limit}"


def test_lru_eviction_order():
    limit = cache_mod.CACHE_MAX_SIZE
    for i in range(limit):
        put(1, i, f"v{i}")

    get(1, 0)
    put(1, limit, "new")

    assert get(1, 1) is None
    assert get(1, 0) == "v0"
    assert get(1, limit) == "new"


def test_ttl_expired_returns_none():
    put(1, 42, "данные")
    past = time.monotonic() - cache_mod.CACHE_TTL_SECONDS - 1
    cache_mod._cache[(1, 42)] = ("данные", past)
    assert get(1, 42) is None


def test_ttl_not_expired_returns_text():
    put(1, 43, "свежие данные")
    assert get(1, 43) == "свежие данные"


def test_multiple_entries_independent():
    put(10, 1, "A")
    put(20, 1, "B")
    assert get(10, 1) == "A"
    assert get(20, 1) == "B"


def test_put_returns_none():
    result = put(1, 1, "x")
    assert result is None


def test_different_chats_same_message_id_isolated():
    """Одинаковый message_id в разных чатах не перекрывает друг друга."""
    put(100, 42, "чат A")
    put(200, 42, "чат B")
    assert get(100, 42) == "чат A"
    assert get(200, 42) == "чат B"


def test_lazy_eviction_removes_expired_on_put():
    """put удаляет просроченные записи с начала OrderedDict."""
    past = time.monotonic() - cache_mod.CACHE_TTL_SECONDS - 1
    cache_mod._cache[(1, 1)] = ("старый", past)
    cache_mod._cache[(1, 2)] = ("старый2", past)

    put(1, 3, "новый")

    assert (1, 1) not in cache_mod._cache
    assert (1, 2) not in cache_mod._cache
    assert get(1, 3) == "новый"


def test_segments_round_trip():
    segs = [[0.0, 2.0, "привет"], [2.0, 4.0, "пока"]]
    put_segments(1, 1, segs)
    assert get_segments(1, 1) == segs


def test_segments_cache_independent_from_text_cache():
    """put в текстовый кэш не пишет в кэш сегментов и наоборот."""
    put(1, 1, "текст")
    put_segments(1, 1, [[0.0, 1.0, "сегмент"]])
    assert get(1, 1) == "текст"
    assert get_segments(1, 1) == [[0.0, 1.0, "сегмент"]]
    assert get_segments(2, 2) is None


def test_lazy_eviction_stops_at_first_live_entry():
    """put прекращает обход при первой не-просроченной записи."""
    past = time.monotonic() - cache_mod.CACHE_TTL_SECONDS - 1
    cache_mod._cache[(1, 1)] = ("просрочен", past)
    cache_mod._cache[(1, 2)] = ("живой", time.monotonic())
    cache_mod._cache[(1, 3)] = ("просрочен после живого", past)

    put(1, 4, "новый")

    assert (1, 1) not in cache_mod._cache
    assert (1, 2) in cache_mod._cache
    assert (1, 3) in cache_mod._cache


def test_persistence_survives_restart(tmp_path):
    """init_result_cache + put → после очистки памяти и повторного init данные восстановлены."""
    db = str(tmp_path / "results.db")
    saved = cache_mod._DB_PATH
    try:
        cache_mod.init_result_cache(db)
        put(7, 8, "переживший текст")
        put_segments(7, 8, [[0.0, 1.5, "сегмент"]])

        # Симулируем рестарт процесса: память пуста, на диске — данные.
        cache_mod._cache.clear()
        cache_mod._seg_cache.clear()
        cache_mod.init_result_cache(db)

        assert get(7, 8) == "переживший текст"
        assert get_segments(7, 8) == [[0.0, 1.5, "сегмент"]]
    finally:
        cache_mod._DB_PATH = saved


def test_persistence_disabled_by_default_no_write(tmp_path):
    """Без init_result_cache put не пишет на диск (чистый in-memory)."""
    assert cache_mod._DB_PATH is None
    put(1, 1, "только в памяти")
    assert not (tmp_path / "results.db").exists()
