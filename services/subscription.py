import logging
import time

from config import config

logger = logging.getLogger(__name__)

SUBSCRIPTION_TTL_SECONDS = 600

_subscriber_cache: dict[int, float] = {}

_SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}


def is_gate_enabled() -> bool:
    return bool(config["REQUIRED_CHANNEL"])


def is_subscriber_cached(user_id: int) -> bool:
    expiry = _subscriber_cache.get(user_id)
    if expiry is None:
        return False
    now = time.monotonic()
    if now >= expiry:
        del _subscriber_cache[user_id]
        return False
    return True


async def check_subscription(bot, user_id: int) -> bool:
    if not is_gate_enabled():
        return False
    channel = config["REQUIRED_CHANNEL"]
    try:
        member = await bot.get_chat_member(channel, user_id)
        if member.status in _SUBSCRIBED_STATUSES:
            _subscriber_cache[user_id] = time.monotonic() + SUBSCRIPTION_TTL_SECONDS
            return True
        return False
    except Exception:
        logger.warning(
            "check_subscription: get_chat_member failed for user=%d channel=%s",
            user_id,
            channel,
            exc_info=True,
        )
        return False


def channel_url() -> str | None:
    channel = config["REQUIRED_CHANNEL"]
    if not channel:
        return None
    if channel.startswith("@"):
        return f"https://t.me/{channel.lstrip('@')}"
    return None


def cached_subscriber_count() -> int:
    now = time.monotonic()
    return sum(1 for expiry in _subscriber_cache.values() if now < expiry)
