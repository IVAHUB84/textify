import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_CF_DAILY_BUDGET = 300


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

    cf_daily_budget = _DEFAULT_CF_DAILY_BUDGET
    raw_budget = os.environ.get("CF_DAILY_BUDGET", "").strip()
    if raw_budget:
        try:
            parsed = int(raw_budget)
            if parsed <= 0:
                logger.warning(
                    "CF_DAILY_BUDGET содержит неположительное значение %r — используется дефолт %d.",
                    raw_budget,
                    _DEFAULT_CF_DAILY_BUDGET,
                )
            else:
                cf_daily_budget = parsed
        except ValueError:
            logger.warning(
                "CF_DAILY_BUDGET содержит нечисловое значение %r — используется дефолт %d.",
                raw_budget,
                _DEFAULT_CF_DAILY_BUDGET,
            )

    group_asr_local = True
    raw_group_asr = os.environ.get("GROUP_ASR_LOCAL", "").strip().lower()
    if raw_group_asr in ("true", "1", "yes"):
        group_asr_local = True
    elif raw_group_asr in ("false", "0", "no"):
        group_asr_local = False
    elif raw_group_asr:
        logger.warning(
            "GROUP_ASR_LOCAL содержит некорректное значение %r — используется дефолт True.",
            raw_group_asr,
        )

    attribution_footer = True
    raw_attribution = os.environ.get("ATTRIBUTION_FOOTER", "").strip().lower()
    if raw_attribution in ("true", "1", "yes"):
        attribution_footer = True
    elif raw_attribution in ("false", "0", "no"):
        attribution_footer = False
    elif raw_attribution:
        logger.warning(
            "ATTRIBUTION_FOOTER содержит некорректное значение %r — используется дефолт True.",
            raw_attribution,
        )

    return {
        "BOT_TOKEN": token,
        "ADMIN_USER_ID": admin_user_id,
        "STATS_DB_PATH": stats_db_path,
        "CF_DAILY_BUDGET": cf_daily_budget,
        "GROUP_ASR_LOCAL": group_asr_local,
        "ATTRIBUTION_FOOTER": attribution_footer,
    }


config = load_config()
