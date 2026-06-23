"""Тесты services/result_cache.py."""
import time
import pytest

import services.result_cache as cache_mod
from services.result_cache import get, put


def _clear_cache():
    cache_mod._cache.clear()


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
