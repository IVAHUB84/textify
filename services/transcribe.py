import asyncio
import base64
import logging
import os
import threading
from io import BytesIO

import httpx
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None
_model_lock = threading.Lock()

_CF_TIMEOUT = 60.0
_CF_MAX_AUDIO_BYTES = 8 * 1024 * 1024
_DEFAULT_ASR_PROVIDER = "cloudflare"
_DEFAULT_CF_WHISPER_MODEL = "@cf/openai/whisper-large-v3-turbo"


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def _transcribe_sync(audio_bytes: bytes) -> str:
    model = _get_model()
    # faster-whisper feeds the input to av.open, which needs a path or a
    # file-like object with read(); raw bytes raise "File object has no
    # read() method". Wrap in BytesIO.
    segments, _ = model.transcribe(BytesIO(audio_bytes))
    return "".join(segment.text for segment in segments).strip()


async def _transcribe_local(audio_bytes: bytes) -> str:
    return await asyncio.to_thread(_transcribe_sync, audio_bytes)


async def _transcribe_cloudflare(
    audio_bytes: bytes, account_id: str, api_token: str, model: str
) -> str:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    payload = {"audio": base64.b64encode(audio_bytes).decode()}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=_CF_TIMEOUT,
        )
        response.raise_for_status()
    data = response.json()
    return data["result"]["text"].strip()


async def transcribe(audio_bytes: bytes) -> str:
    asr_provider = os.environ.get("ASR_PROVIDER", _DEFAULT_ASR_PROVIDER).strip().lower()

    if asr_provider == "local":
        return await _transcribe_local(audio_bytes)

    if len(audio_bytes) > _CF_MAX_AUDIO_BYTES:
        logger.warning(
            "Audio exceeds CF size threshold (%d bytes > %d), using local transcription",
            len(audio_bytes),
            _CF_MAX_AUDIO_BYTES,
        )
        return await _transcribe_local(audio_bytes)

    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account_id or not api_token:
        logger.warning(
            "CF_ACCOUNT_ID or CF_API_TOKEN not configured, falling back to local transcription"
        )
        return await _transcribe_local(audio_bytes)

    model = os.environ.get("CF_WHISPER_MODEL", _DEFAULT_CF_WHISPER_MODEL).strip()

    try:
        return await _transcribe_cloudflare(audio_bytes, account_id, api_token, model)
    except Exception:
        logger.exception(
            "Cloudflare transcription failed, falling back to local transcription"
        )
        return await _transcribe_local(audio_bytes)
