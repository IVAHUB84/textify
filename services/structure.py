import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 8000
_TIMEOUT = 30.0
_DEFAULT_CF_MODEL = "@cf/meta/llama-3.1-8b-instruct"

_SYSTEM_PROMPT = (
    "Твоя задача — привести распознанный текст к читаемой структуре Markdown: "
    "заголовки, списки, ключевые пункты. "
    "Сохраняй смысл дословно — не выдумывай факты и не добавляй содержание, "
    "отсутствующее в исходнике. "
    "Не переводи и не меняй язык контента. "
    "Верни только оформленный текст без преамбул и пояснений."
)


class LLMProvider(Protocol):
    async def complete(self, client: httpx.AsyncClient, system: str, user: str) -> str:
        ...


class _CloudflareProvider:
    def __init__(self, account_id: str, api_token: str, model: str) -> None:
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        )
        self._token = api_token

    async def complete(self, client: httpx.AsyncClient, system: str, user: str) -> str:
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        }
        response = await client.post(
            self._url,
            json=payload,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["result"]["response"]


class _GroqProvider:
    _URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str) -> None:
        self._key = api_key
        self._model = model

    async def complete(self, client: httpx.AsyncClient, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = await client.post(
            self._URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _build_provider() -> LLMProvider | None:
    llm_provider = os.environ.get("LLM_PROVIDER", "cloudflare").strip().lower()

    if llm_provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.environ.get("GROQ_MODEL", "llama3-8b-8192").strip()
        return _GroqProvider(api_key=api_key, model=model)

    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return None
    model = os.environ.get("CF_MODEL", _DEFAULT_CF_MODEL).strip()
    return _CloudflareProvider(account_id=account_id, api_token=api_token, model=model)


async def structure_text(raw_text: str) -> str:
    provider = _build_provider()
    if provider is None:
        logger.warning("LLM provider credentials not configured, falling back to raw text")
        return raw_text

    truncated = raw_text[:_MAX_INPUT_CHARS]

    try:
        async with httpx.AsyncClient() as client:
            result = await provider.complete(client, _SYSTEM_PROMPT, truncated)
        if result and result.strip():
            return result
        logger.warning("LLM returned empty response, falling back to raw text")
    except Exception:
        logger.exception("LLM structuring failed, falling back to raw text")

    return raw_text
