"""Общие фиксатуры для тестов Textify."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_pass_enforce_limit(request):
    """Автоматически мокает enforce_limit → True во всех тестах, кроме test_gate.py
    и test_limits.py (они проверяют поведение лимита явно)."""
    if "test_gate" in request.fspath.basename or "test_limits" in request.fspath.basename:
        yield
        return

    with (
        patch("handlers.gate.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.audio.enforce_limit", new=AsyncMock(return_value=True)),
        patch("handlers.image.enforce_limit", new=AsyncMock(return_value=True)),
    ):
        yield
