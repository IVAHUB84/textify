# Username хранится без "@" и в оригинальном регистре (как вернул get_me()),
# потому что используется в реф-ссылках вида t.me/<Username>?start=...
# Сравнение @-упоминаний в group.py само приводит к lower() перед сравнением.
_username: str = ""


def set_bot_username(username: str) -> None:
    global _username
    _username = username.lstrip("@")


def get_bot_username() -> str:
    return _username
