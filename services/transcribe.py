import asyncio
import threading
from io import BytesIO

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
    # faster-whisper feeds the input to av.open, which needs a path or a
    # file-like object with read(); raw bytes raise "File object has no
    # read() method". Wrap in BytesIO.
    segments, _ = model.transcribe(BytesIO(audio_bytes))
    return "".join(segment.text for segment in segments).strip()


async def transcribe(audio_bytes: bytes) -> str:
    return await asyncio.to_thread(_transcribe_sync, audio_bytes)
