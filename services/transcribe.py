import asyncio
import threading

from faster_whisper import WhisperModel

_model: WhisperModel | None = None
_model_lock = threading.Lock()


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def _transcribe_sync(audio_bytes: bytes) -> str:
    model = _get_model()
    segments, _ = model.transcribe(audio_bytes)
    return "".join(segment.text for segment in segments).strip()


async def transcribe(audio_bytes: bytes) -> str:
    return await asyncio.to_thread(_transcribe_sync, audio_bytes)
