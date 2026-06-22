import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def load_config() -> dict:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан или пуст. "
            "Укажите его в переменных окружения или в файле .env."
        )

    admin_user_id: int | None = None
    raw_admin = os.environ.get("ADMIN_USER_ID", "").strip()
    if raw_admin:
        try:
            admin_user_id = int(raw_admin)
        except ValueError:
            logger.warning(
                "ADMIN_USER_ID содержит нечисловое значение %r — игнорируется.", raw_admin
            )

    stats_db_path = os.environ.get("STATS_DB_PATH", "/app/data/stats.db").strip()

    return {
        "BOT_TOKEN": token,
        "ADMIN_USER_ID": admin_user_id,
        "STATS_DB_PATH": stats_db_path,
    }


config = load_config()
