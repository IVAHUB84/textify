"""Тесты gate-логики: enforce_limit и callback «Проверить»."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_subscription_cache():
    import services.subscription as sub
    sub._subscriber_cache.clear()
    yield
    sub._subscriber_cache.clear()


@pytest.fixture(autouse=True)
def reset_referral_cache():
    import services.referrals as ref
    ref._referral_count_cache.clear()
    yield
    ref._referral_count_cache.clear()


def _gate_cfg():
    import handlers.gate as gate
    return gate.config


def _sub_cfg():
    import services.subscription as sub
    return sub.config


@pytest.fixture(autouse=True)
def default_limits(monkeypatch):
    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)
    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_SUBSCRIBED", 30)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_CAP", 30)
    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "")


def _make_message(chat_type="private"):
    msg = MagicMock()
    msg.chat.type = chat_type
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_enforce_limit_within_limit_returns_true(monkeypatch):
    from handlers.gate import enforce_limit

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=0)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=1, is_private=True)

    assert result is True
    rec.assert_awaited_once_with(1)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_enforce_limit_exhausted_private_gate_enabled_shows_gate(monkeypatch):
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=3)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=True),
        patch("handlers.gate.subscription.channel_url", return_value="https://t.me/chan"),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=2, is_private=True)

    assert result is False
    rec.assert_not_awaited()
    msg.answer.assert_awaited_once()
    call_kwargs = msg.answer.call_args
    markup = call_kwargs.kwargs.get("reply_markup") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    cb_buttons = [b for b in buttons if hasattr(b, "callback_data") and b.callback_data == "gate:chk"]
    assert cb_buttons, "Кнопка «Проверить» не найдена"


@pytest.mark.asyncio
async def test_enforce_limit_exhausted_group_shows_neutral(monkeypatch):
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=5)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=True),
    ):
        msg = _make_message("group")
        result = await enforce_limit(msg, user_id=3, is_private=False)

    assert result is False
    rec.assert_not_awaited()
    msg.answer.assert_awaited_once()
    answered_text = msg.answer.call_args.args[0]
    assert "завтра" in answered_text.lower() or "лимит" in answered_text.lower()
    call_kwargs = msg.answer.call_args.kwargs
    assert "reply_markup" not in call_kwargs or call_kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_enforce_limit_exhausted_gate_disabled_shows_neutral(monkeypatch):
    from handlers.gate import enforce_limit

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=3)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()),
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=False),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=4, is_private=True)

    assert result is False
    msg.answer.assert_awaited_once()
    call_kwargs = msg.answer.call_args.kwargs
    assert "reply_markup" not in call_kwargs or call_kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_enforce_limit_subscriber_uses_subscribed_limit(monkeypatch):
    from handlers.gate import enforce_limit

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=5)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=True),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=5, is_private=True)

    assert result is True
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_gate_check_subscribed():
    from handlers.gate import handle_gate_check

    bot = AsyncMock()
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 10
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    with patch("handlers.gate.subscription.check_subscription", new=AsyncMock(return_value=True)):
        await handle_gate_check(callback, bot)

    callback.answer.assert_awaited()
    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.call_args.args[0]
    assert "подтверждена" in text.lower() or "пришлите" in text.lower()


@pytest.mark.asyncio
async def test_callback_gate_check_not_subscribed():
    from handlers.gate import handle_gate_check

    bot = AsyncMock()
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 11
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    with patch("handlers.gate.subscription.check_subscription", new=AsyncMock(return_value=False)):
        await handle_gate_check(callback, bot)

    callback.answer.assert_awaited()
    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.call_args.args[0]
    assert "не вижу" in text.lower() or "подписк" in text.lower()


@pytest.mark.asyncio
async def test_enforce_limit_record_failure_does_not_block():
    from handlers.gate import enforce_limit

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=1)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock(side_effect=Exception("db err"))),
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=99, is_private=True)

    assert result is True


@pytest.mark.asyncio
async def test_callback_gate_check_inaccessible_message_answers_alert():
    """handle_gate_check при InaccessibleMessage не падает, отвечает show_alert."""
    from aiogram.types import InaccessibleMessage
    from handlers.gate import handle_gate_check

    bot = AsyncMock()
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 20
    inaccessible = MagicMock(spec=InaccessibleMessage)
    callback.message = inaccessible
    callback.answer = AsyncMock()

    with patch("handlers.gate.subscription.check_subscription", new=AsyncMock(return_value=True)):
        await handle_gate_check(callback, bot)

    callback.answer.assert_awaited_once()
    call_kwargs = callback.answer.call_args
    assert call_kwargs.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_callback_gate_check_none_message_answers_alert():
    """handle_gate_check при callback.message=None не падает, отвечает show_alert."""
    from handlers.gate import handle_gate_check

    bot = AsyncMock()
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 21
    callback.message = None
    callback.answer = AsyncMock()

    with patch("handlers.gate.subscription.check_subscription", new=AsyncMock(return_value=False)):
        await handle_gate_check(callback, bot)

    callback.answer.assert_awaited_once()
    call_kwargs = callback.answer.call_args
    assert call_kwargs.kwargs.get("show_alert") is True


# ---------------------------------------------------------------------------
# v1.8.0: реферальный бонус в enforce_limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_limit_free_user_with_referrals_gets_bonus(monkeypatch):
    """Неподписчик с 2 рефералами: effective = 3 + 6 = 9; used=9 → заблокирован."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_CAP", 30)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=9)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=2)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=50, is_private=True)

    assert result is False
    rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_enforce_limit_free_user_with_referrals_within_effective_limit(monkeypatch):
    """Неподписчик с 2 рефералами: used=8 < effective=9, должен пройти."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_CAP", 30)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=7)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=2)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=51, is_private=True)

    assert result is True
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_limit_subscribed_user_with_referrals_gets_bonus(monkeypatch):
    """Подписчик с 3 рефералами: effective = 30 + 9 = 39; used=35 < 39 → проходит."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_SUBSCRIBED", 30)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_CAP", 30)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=35)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=True),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=3)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=52, is_private=True)

    assert result is True
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_limit_gate_message_has_invite_button(monkeypatch):
    """При исчерпании лимита в личке неподписчику — кнопка «Пригласить друзей»."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=3)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()),
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=True),
        patch("handlers.gate.subscription.channel_url", return_value="https://t.me/chan"),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
        patch("handlers.gate.build_share_url", return_value="https://t.me/share/url?url=x"),
    ):
        msg = _make_message("private")
        await enforce_limit(msg, user_id=53, is_private=True)

    msg.answer.assert_awaited_once()
    call_kwargs = msg.answer.call_args
    markup = call_kwargs.kwargs.get("reply_markup") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    invite_buttons = [b for b in buttons if "Пригласить" in b.text]
    assert invite_buttons, "Кнопка «Пригласить друзей» не найдена"
    check_buttons = [b for b in buttons if b.callback_data == "gate:chk"]
    assert check_buttons, "Кнопка «Проверить» не найдена"


@pytest.mark.asyncio
async def test_enforce_limit_gate_message_has_two_paths_text(monkeypatch):
    """Текст gate-сообщения в личке содержит оба пути (канал + друзья)."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=3)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()),
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=True),
        patch("handlers.gate.subscription.channel_url", return_value="https://t.me/chan"),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
        patch("handlers.gate.build_share_url", return_value="https://t.me/share/url?url=x"),
    ):
        msg = _make_message("private")
        await enforce_limit(msg, user_id=54, is_private=True)

    text = msg.answer.call_args.args[0]
    assert "подпишитесь" in text.lower() or "канал" in text.lower()
    assert "пригласите" in text.lower() or "друзей" in text.lower()
    assert "+3" in text


@pytest.mark.asyncio
async def test_enforce_limit_zero_referrals_same_as_v170(monkeypatch):
    """При нуле рефералов поведение идентично v1.7.0 (base = DAILY_LIMIT_FREE)."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=3)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=0)),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=55, is_private=True)

    assert result is False
    rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_enforce_limit_referral_count_failure_falls_back_to_base(monkeypatch):
    """Сбой cached_referral_count → бонус 0, enforce_limit не падает."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=1)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()) as rec,
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch(
            "handlers.gate.referrals.cached_referral_count",
            new=AsyncMock(side_effect=Exception("cache down")),
        ),
    ):
        msg = _make_message("private")
        result = await enforce_limit(msg, user_id=56, is_private=True)

    assert result is True
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_limit_group_exhausted_shows_neutral_with_refs(monkeypatch):
    """В группе при исчерпании лимита (даже с рефералами) — нейтральное сообщение."""
    from handlers.gate import enforce_limit

    monkeypatch.setitem(_gate_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_sub_cfg(), "REQUIRED_CHANNEL", "@chan")
    monkeypatch.setitem(_gate_cfg(), "DAILY_LIMIT_FREE", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_PER", 3)
    monkeypatch.setitem(_gate_cfg(), "REFERRAL_BONUS_CAP", 30)

    with (
        patch("handlers.gate.limits.usage_today", new=AsyncMock(return_value=10)),
        patch("handlers.gate.limits.record_recognition", new=AsyncMock()),
        patch("handlers.gate.subscription.is_subscriber_cached", return_value=False),
        patch("handlers.gate.subscription.is_gate_enabled", return_value=True),
        patch("handlers.gate.referrals.cached_referral_count", new=AsyncMock(return_value=2)),
    ):
        msg = _make_message("group")
        result = await enforce_limit(msg, user_id=57, is_private=False)

    assert result is False
    call_kwargs = msg.answer.call_args.kwargs
    assert "reply_markup" not in call_kwargs or call_kwargs.get("reply_markup") is None
