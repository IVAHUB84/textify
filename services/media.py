import asyncio
import logging
from io import BytesIO

import av

from services import HEAVY_LOCAL_SEMAPHORE

logger = logging.getLogger(__name__)


def _extract_audio_sync(video_bytes: bytes) -> bytes | None:
    with av.open(BytesIO(video_bytes)) as container:
        audio_streams = [s for s in container.streams if s.type == "audio"]
        if not audio_streams:
            return None

        out_buf = BytesIO()
        with av.open(out_buf, mode="w", format="wav") as out_container:
            out_stream = out_container.add_stream("pcm_s16le", rate=16000, layout="mono")
            for frame in container.decode(audio=0):
                frame.pts = None
                for packet in out_stream.encode(frame):
                    out_container.mux(packet)
            for packet in out_stream.encode(None):
                out_container.mux(packet)

        return out_buf.getvalue()


async def extract_audio(video_bytes: bytes) -> bytes | None:
    async with HEAVY_LOCAL_SEMAPHORE:
        return await asyncio.to_thread(_extract_audio_sync, video_bytes)
