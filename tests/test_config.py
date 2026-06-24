import importlib
import sys

import pytest


def reload_config(monkeypatch, token_value):
    monkeypatch.setenv("BOT_TOKEN", token_value)
    if "config" in sys.modules:
        del sys.modules["config"]
    return importlib.import_module("config")


def test_valid_token_returns_nonempty(monkeypatch):
    """Т-1: при заданном BOT_TOKEN конфиг отдаёт непустой токен."""
    module = reload_config(monkeypatch, "test_token_12345")
    assert module.config["BOT_TOKEN"] == "test_token_12345"


def test_empty_token_raises(monkeypatch):
    """Т-2: при пустом BOT_TOKEN загрузка конфига падает ошибкой."""
    monkeypatch.setenv("BOT_TOKEN", "")
    if "config" in sys.modules:
        del sys.modules["config"]
    with pytest.raises(RuntimeError):
        importlib.import_module("config")


def test_missing_token_raises(monkeypatch):
    """Т-2: при незаданном BOT_TOKEN загрузка конфига падает ошибкой."""
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    if "config" in sys.modules:
        del sys.modules["config"]
    with pytest.raises(RuntimeError):
        importlib.import_module("config")


def _reload(monkeypatch, extra_env: dict):
    monkeypatch.setenv("BOT_TOKEN", "tok")
    for k, v in extra_env.items():
        monkeypatch.setenv(k, v)
    if "config" in sys.modules:
        del sys.modules["config"]
    return importlib.import_module("config")


def test_daily_limit_free_default(monkeypatch):
    mod = _reload(monkeypatch, {})
    assert mod.config["DAILY_LIMIT_FREE"] == 3


def test_daily_limit_subscribed_default(monkeypatch):
    mod = _reload(monkeypatch, {})
    assert mod.config["DAILY_LIMIT_SUBSCRIBED"] == 30


def test_daily_limit_free_custom(monkeypatch):
    mod = _reload(monkeypatch, {"DAILY_LIMIT_FREE": "10"})
    assert mod.config["DAILY_LIMIT_FREE"] == 10


def test_daily_limit_subscribed_custom(monkeypatch):
    mod = _reload(monkeypatch, {"DAILY_LIMIT_SUBSCRIBED": "50"})
    assert mod.config["DAILY_LIMIT_SUBSCRIBED"] == 50


def test_daily_limit_free_invalid_string_uses_default(monkeypatch):
    mod = _reload(monkeypatch, {"DAILY_LIMIT_FREE": "abc"})
    assert mod.config["DAILY_LIMIT_FREE"] == 3


def test_daily_limit_free_nonpositive_uses_default(monkeypatch):
    mod = _reload(monkeypatch, {"DAILY_LIMIT_FREE": "0"})
    assert mod.config["DAILY_LIMIT_FREE"] == 3


def test_daily_limit_subscribed_invalid_uses_default(monkeypatch):
    mod = _reload(monkeypatch, {"DAILY_LIMIT_SUBSCRIBED": "-5"})
    assert mod.config["DAILY_LIMIT_SUBSCRIBED"] == 30


def test_required_channel_empty_by_default(monkeypatch):
    mod = _reload(monkeypatch, {})
    assert mod.config["REQUIRED_CHANNEL"] == ""


def test_required_channel_set(monkeypatch):
    mod = _reload(monkeypatch, {"REQUIRED_CHANNEL": "@mychan"})
    assert mod.config["REQUIRED_CHANNEL"] == "@mychan"


def test_required_channel_whitespace_stripped(monkeypatch):
    mod = _reload(monkeypatch, {"REQUIRED_CHANNEL": "  @mychan  "})
    assert mod.config["REQUIRED_CHANNEL"] == "@mychan"
