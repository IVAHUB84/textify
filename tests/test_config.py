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
