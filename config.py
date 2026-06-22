import os

from dotenv import load_dotenv

load_dotenv()


def load_config() -> dict:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан или пуст. "
            "Укажите его в переменных окружения или в файле .env."
        )
    return {"BOT_TOKEN": token}


config = load_config()
