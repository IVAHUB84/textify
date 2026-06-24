"""Тесты v1.8.0: effective_daily_limit и cached_referral_count с TTL-кэшем."""
import sqlite3
import pytest


# ---------------------------------------------------------------------------
# Фикстуры: изоляция кэша рефералов и БД
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_referral_cache():
    import services.referrals as ref
    ref._referral_count_cache.clear()
    yield
    ref._referral_count_cache.clear()


def _init_referrals_schema(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id  INTEGER PRIMARY KEY,
                referrer_id  INTEGER NOT NULL,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
            """
        )
        con.commit()
    finally:
        con.close()


@pytest.fixture()
def ref_db_path(tmp_path):
    path = str(tmp_path / "stats.db")
    _init_referrals_schema(path)
    return path


@pytest.fixture()
def ref_module(ref_db_path, monkeypatch):
    import services.referrals as m
    monkeypatch.setattr(m, "config", {"STATS_DB_PATH": ref_db_path})
    return m


# ---------------------------------------------------------------------------
# effective_daily_limit: формула
# ---------------------------------------------------------------------------


def _limits_module_with_config(monkeypatch, per: int = 3, cap: int = 30):
    import services.limits as lm
    monkeypatch.setitem(lm.config, "REFERRAL_BONUS_PER", per)
    monkeypatch.setitem(lm.config, "REFERRAL_BONUS_CAP", cap)
    return lm


def test_effective_limit_zero_referrals_returns_base(monkeypatch):
    lm = _limits_module_with_config(monkeypatch)
    assert lm.effective_daily_limit(3, 0) == 3
    assert lm.effective_daily_limit(30, 0) == 30


def test_effective_limit_linear_growth(monkeypatch):
    lm = _limits_module_with_config(monkeypatch, per=3, cap=30)
    assert lm.effective_daily_limit(3, 1) == 6
    assert lm.effective_daily_limit(3, 2) == 9
    assert lm.effective_daily_limit(3, 5) == 18


def test_effective_limit_cap_applied(monkeypatch):
    lm = _limits_module_with_config(monkeypatch, per=3, cap=30)
    assert lm.effective_daily_limit(3, 10) == 33
    assert lm.effective_daily_limit(3, 11) == 33
    assert lm.effective_daily_limit(3, 100) == 33


def test_effective_limit_subscribed_base_plus_bonus(monkeypatch):
    lm = _limits_module_with_config(monkeypatch, per=3, cap=30)
    assert lm.effective_daily_limit(30, 2) == 36
    assert lm.effective_daily_limit(30, 10) == 60
    assert lm.effective_daily_limit(30, 11) == 60


def test_effective_limit_free_base_zero_refs(monkeypatch):
    lm = _limits_module_with_config(monkeypatch, per=3, cap=30)
    assert lm.effective_daily_limit(3, 0) == 3


def test_effective_limit_negative_referrals_returns_base(monkeypatch):
    lm = _limits_module_with_config(monkeypatch)
    assert lm.effective_daily_limit(3, -1) == 3


# ---------------------------------------------------------------------------
# cached_referral_count: TTL-кэш и инвалидация
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_referral_count_first_call_queries_db(ref_module):
    await ref_module.record_referral(referrer_id=1, referred_id=101)
    await ref_module.record_referral(referrer_id=1, referred_id=102)

    count = await ref_module.cached_referral_count(1)
    assert count == 2


@pytest.mark.asyncio
async def test_cached_referral_count_second_call_uses_cache(ref_module, monkeypatch):
    await ref_module.record_referral(referrer_id=2, referred_id=201)

    call_count = 0
    original_count = ref_module.count_referrals

    async def tracked_count(referrer_id):
        nonlocal call_count
        call_count += 1
        return await original_count(referrer_id)

    monkeypatch.setattr(ref_module, "count_referrals", tracked_count)

    await ref_module.cached_referral_count(2)
    await ref_module.cached_referral_count(2)

    assert call_count == 1, "count_referrals должен быть вызван один раз (кэш)"


@pytest.mark.asyncio
async def test_cached_referral_count_expired_ttl_requeries(ref_module, monkeypatch):
    import time

    await ref_module.record_referral(referrer_id=3, referred_id=301)
    ref_module._referral_count_cache[3] = (1, time.monotonic() - 1)

    call_count = 0
    original_count = ref_module.count_referrals

    async def tracked_count(referrer_id):
        nonlocal call_count
        call_count += 1
        return await original_count(referrer_id)

    monkeypatch.setattr(ref_module, "count_referrals", tracked_count)

    result = await ref_module.cached_referral_count(3)
    assert result == 1
    assert call_count == 1, "По истечении TTL должен выполняться COUNT"


@pytest.mark.asyncio
async def test_record_referral_invalidates_cache(ref_module):
    await ref_module.record_referral(referrer_id=4, referred_id=401)
    await ref_module.cached_referral_count(4)

    assert 4 in ref_module._referral_count_cache

    await ref_module.record_referral(referrer_id=4, referred_id=402)

    assert 4 not in ref_module._referral_count_cache

    count = await ref_module.cached_referral_count(4)
    assert count == 2


@pytest.mark.asyncio
async def test_cached_referral_count_db_failure_returns_zero(ref_module, monkeypatch):
    async def broken_count(referrer_id):
        raise RuntimeError("db is down")

    monkeypatch.setattr(ref_module, "count_referrals", broken_count)

    result = await ref_module.cached_referral_count(999)
    assert result == 0


@pytest.mark.asyncio
async def test_cached_referral_count_no_refs_returns_zero(ref_module):
    result = await ref_module.cached_referral_count(9999)
    assert result == 0
