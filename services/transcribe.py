import asyncio
import base64
import logging
import os
import threading
from io import BytesIO

import httpx
from faster_whisper import WhisperModel

from services import HEAVY_LOCAL_SEMAPHORE
from services.budget import cf_budget_allow, cf_budget_consume

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None
_model_lock = threading.Lock()

_CF_TIMEOUT = 60.0
_CF_MAX_AUDIO_BYTES = 8 * 1024 * 1024
_DEFAULT_ASR_PROVIDER = "cloudflare"
_DEFAULT_CF_WHISPER_MODEL = "@cf/openai/whisper-large-v3-turbo"

# Сегмент транскрипции: (начало_сек, конец_сек, текст).
Segment = tuple[float, float, str]

# Тайм-коды показываем только для записей длиннее порога — короткому
# голосовому они не нужны и лишь засоряют выдачу.
TIMESTAMP_MIN_SECONDS = 60.0


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def _seg_tuple(seg: object) -> Segment:
    # Моки в тестах дают SimpleNamespace(text=...) без start/end — отсюда getattr с дефолтом.
    start = float(getattr(seg, "start", 0.0) or 0.0)
    end = float(getattr(seg, "end", 0.0) or 0.0)
    return (start, end, getattr(seg, "text", ""))


def _transcribe_sync(audio_bytes: bytes) -> list[Segment]:
    model = _get_model()
    # faster-whisper feeds the input to av.open, which needs a path or a
    # file-like object with read(); raw bytes raise "File object has no
    # read() method". Wrap in BytesIO.
    segments, _ = model.transcribe(BytesIO(audio_bytes))
    return [_seg_tuple(seg) for seg in segments]


async def _transcribe_local(audio_bytes: bytes) -> list[Segment]:
    async with HEAVY_LOCAL_SEMAPHORE:
        return await asyncio.to_thread(_transcribe_sync, audio_bytes)


def _segments_text(segments: list[Segment]) -> str:
    return "".join(text for _start, _end, text in segments).strip()


def _parse_cf_segments(raw: object) -> list[Segment] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[Segment] = []
    for item in raw:
        try:
            out.append((float(item["start"]), float(item["end"]), str(item["text"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out or None


async def _transcribe_cloudflare(
    audio_bytes: bytes, account_id: str, api_token: str, model: str
) -> tuple[str, list[Segment] | None]:
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
    result = data["result"]
    return result["text"].strip(), _parse_cf_segments(result.get("segments"))


async def transcribe_with_timestamps(
    audio_bytes: bytes, force_local: bool = False
) -> tuple[str, list[Segment] | None]:
    if force_local:
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments

    asr_provider = os.environ.get("ASR_PROVIDER", _DEFAULT_ASR_PROVIDER).strip().lower()

    if asr_provider == "local":
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments

    if len(audio_bytes) > _CF_MAX_AUDIO_BYTES:
        logger.warning(
            "Audio exceeds CF size threshold (%d bytes > %d), using local transcription",
            len(audio_bytes),
            _CF_MAX_AUDIO_BYTES,
        )
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments

    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account_id or not api_token:
        logger.warning(
            "CF_ACCOUNT_ID or CF_API_TOKEN not configured, falling back to local transcription"
        )
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments

    model = os.environ.get("CF_WHISPER_MODEL", _DEFAULT_CF_WHISPER_MODEL).strip()

    if not await cf_budget_allow():
        logger.warning(
            "CF daily budget exhausted, degrading ASR to local transcription"
        )
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments

    await cf_budget_consume()

    try:
        return await _transcribe_cloudflare(audio_bytes, account_id, api_token, model)
    except Exception:
        logger.exception(
            "Cloudflare transcription failed, falling back to local transcription"
        )
        segments = await _transcribe_local(audio_bytes)
        return _segments_text(segments), segments


async def transcribe(audio_bytes: bytes, force_local: bool = False) -> str:
    text, _segments = await transcribe_with_timestamps(audio_bytes, force_local=force_local)
    return text


def _format_ts(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def segments_duration(segments: list[Segment]) -> float:
    return max((end for _start, end, _text in segments), default=0.0)


def format_timestamps(segments: list[Segment]) -> str:
    lines = []
    for start, _end, text in segments:
        clean = text.strip()
        if clean:
            lines.append(f"[{_format_ts(start)}] {clean}")
    return "\n".join(lines)
