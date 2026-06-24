"""Тесты обёртки подписки и кэша (services/subscription.py)."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def reset_subscription_cache():
    import services.subscription as sub
    sub._subscriber_cache.clear()
    yield
    sub._subscriber_cache.clear()


def _sub_cfg():
    import services.subscription as sub
    return sub.config


def test_is_gate_enabled_empty(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "")
    assert sub.is_gate_enabled() is False


def test_is_gate_enabled_nonempty(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    assert sub.is_gate_enabled() is True


def test_is_subscriber_cached_no_entry():
    import services.subscription as sub
    assert sub.is_subscriber_cached(123) is False


def test_is_subscriber_cached_live_entry():
    import services.subscription as sub
    sub._subscriber_cache[123] = time.monotonic() + 600
    assert sub.is_subscriber_cached(123) is True


def test_is_subscriber_cached_expired_entry():
    import services.subscription as sub
    sub._subscriber_cache[123] = time.monotonic() - 1
    assert sub.is_subscriber_cached(123) is False
    assert 123 not in sub._subscriber_cache


@pytest.mark.asyncio
async def test_check_subscription_gate_disabled_returns_false_no_api(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "")
    bot = AsyncMock()
    result = await sub.check_subscription(bot, 1)
    assert result is False
    bot.get_chat_member.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["member", "administrator", "creator"])
async def test_check_subscription_subscribed_statuses(status, monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    member = MagicMock()
    member.status = status
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=member)

    result = await sub.check_subscription(bot, 42)
    assert result is True
    assert sub.is_subscriber_cached(42) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["left", "kicked", "restricted"])
async def test_check_subscription_non_subscribed_statuses(status, monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    member = MagicMock()
    member.status = status
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=member)

    result = await sub.check_subscription(bot, 99)
    assert result is False
    assert sub.is_subscriber_cached(99) is False


@pytest.mark.asyncio
async def test_check_subscription_api_exception_returns_false(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(side_effect=Exception("API error"))

    result = await sub.check_subscription(bot, 10)
    assert result is False
    assert sub.is_subscriber_cached(10) is False


@pytest.mark.asyncio
async def test_check_subscription_caches_on_second_call_no_extra_api(monkeypatch):
    """После подтверждения повторный check_subscription в окне TTL не зовёт getChatMember."""
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    member = MagicMock()
    member.status = "member"
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=member)

    await sub.check_subscription(bot, 5)
    assert bot.get_chat_member.call_count == 1

    assert sub.is_subscriber_cached(5) is True


def test_channel_url_at_username(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@mychan")
    assert sub.channel_url() == "https://t.me/mychan"


def test_channel_url_numeric_returns_none(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "-1001234567890")
    assert sub.channel_url() is None


def test_channel_url_empty_returns_none(monkeypatch):
    import services.subscription as sub
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "")
    assert sub.channel_url() is None


def test_ttl_expiry_makes_user_unconfirmed():
    import services.subscription as sub
    sub._subscriber_cache[77] = time.monotonic() + 600
    assert sub.is_subscriber_cached(77) is True
    sub._subscriber_cache[77] = time.monotonic() - 1
    assert sub.is_subscriber_cached(77) is False
