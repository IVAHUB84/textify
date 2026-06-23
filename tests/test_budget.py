"""Тесты services/budget.py: дневной бюджет CF."""
import asyncio
import sqlite3
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _init_budget_db(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS cf_usage (
                date  TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        con.commit()
    finally:
        con.close()


def _set_count(db_path: str, date_str: str, count: int) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO cf_usage (date, count) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET count = ?",
            (date_str, count, count),
        )
        con.commit()
    finally:
        con.close()


def _get_count(db_path: str, date_str: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT count FROM cf_usage WHERE date = ?", (date_str,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        con.close()


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "stats.db")
    _init_budget_db(path)
    return path


@pytest.fixture()
def budget_module(db_path, monkeypatch):
    import services.budget as m
    fake_config = {
        "BOT_TOKEN": "x",
        "ADMIN_USER_ID": None,
        "STATS_DB_PATH": db_path,
        "CF_DAILY_BUDGET": 5,
    }
    monkeypatch.setattr(m, "config", fake_config)
    yield m


# ---------------------------------------------------------------------------
# Базовая логика allow/consume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allow_when_count_below_budget(budget_module, db_path):
    """allow → True при count < budget."""
    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
        _set_count(db_path, "2026-01-01", 3)
        result = await budget_module.cf_budget_allow()
    assert result is True


@pytest.mark.asyncio
async def test_deny_when_count_equals_budget(budget_module, db_path):
    """allow → False при count == budget."""
    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
        _set_count(db_path, "2026-01-01", 5)
        result = await budget_module.cf_budget_allow()
    assert result is False


@pytest.mark.asyncio
async def test_deny_when_count_exceeds_budget(budget_module, db_path):
    """allow → False при count > budget."""
    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
        _set_count(db_path, "2026-01-01", 10)
        result = await budget_module.cf_budget_allow()
    assert result is False


@pytest.mark.asyncio
async def test_consume_increments_counter(budget_module, db_path):
    """consume увеличивает счётчик на 1."""
    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-02"
        await budget_module.cf_budget_consume()
        await budget_module.cf_budget_consume()
    assert _get_count(db_path, "2026-01-02") == 2


# ---------------------------------------------------------------------------
# Сброс при смене UTC-даты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_date_rollover_resets_counter(budget_module, db_path):
    """Счётчик дня D не влияет на счётчик дня D+1."""
    _set_count(db_path, "2026-01-10", 5)  # бюджет исчерпан для D

    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-11"
        result = await budget_module.cf_budget_allow()

    assert result is True


@pytest.mark.asyncio
async def test_consume_for_new_date_starts_from_zero(budget_module, db_path):
    """consume на новую дату создаёт запись с count=1, не затрагивая предыдущую."""
    _set_count(db_path, "2026-01-10", 5)

    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-11"
        await budget_module.cf_budget_consume()

    assert _get_count(db_path, "2026-01-11") == 1
    assert _get_count(db_path, "2026-01-10") == 5


# ---------------------------------------------------------------------------
# fail-open при ошибке БД
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allow_fail_open_on_db_error(budget_module):
    """При сбое чтения БД allow возвращает True (fail-open)."""
    with patch("services.budget.asyncio.to_thread", side_effect=RuntimeError("db error")):
        with patch("services.budget.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
            result = await budget_module.cf_budget_allow()
    assert result is True


@pytest.mark.asyncio
async def test_consume_no_raise_on_db_error(budget_module):
    """consume не бросает исключение при сбое БД."""
    with patch("services.budget.asyncio.to_thread", side_effect=RuntimeError("db error")):
        with patch("services.budget.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
            await budget_module.cf_budget_consume()  # не должно бросить


# ---------------------------------------------------------------------------
# Конкурентный инкремент
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_consume_no_crash_and_increments(budget_module, db_path):
    """Параллельные consume не роняют процесс; итоговый count >= числа вызовов."""
    n = 10
    with patch("services.budget.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-02-01"
        await asyncio.gather(*[budget_module.cf_budget_consume() for _ in range(n)])

    count = _get_count(db_path, "2026-02-01")
    assert count >= n


# ---------------------------------------------------------------------------
# init_cf_usage_db идемпотентна
# ---------------------------------------------------------------------------

def test_init_cf_usage_db_idempotent(budget_module):
    """Повторный вызов init_cf_usage_db не падает."""
    budget_module.init_cf_usage_db()
    budget_module.init_cf_usage_db()
