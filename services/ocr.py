import asyncio
import logging
from io import BytesIO

import pytesseract
from PIL import Image

from services.preprocess import preprocess_image

logger = logging.getLogger(__name__)


_LANG = "rus+eng"
_CONFIG = "--oem 1 --psm 3"


def _alnum_score(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def _run_ocr(image_bytes: bytes) -> str:
    # Run OCR on two candidates and keep the stronger one. Preprocessing
    # (deskew/binarize) helps skewed scans but can hurt noisy photos — on such
    # inputs the binarized image may yield empty/garbled text. Recognizing the
    # plain grayscale original as well guarantees we are never worse than the
    # v0.2.0 baseline; we pick the candidate with more alphanumeric characters.
    candidates: list[str] = []

    try:
        preprocessed = preprocess_image(image_bytes)
        candidates.append(
            pytesseract.image_to_string(preprocessed, lang=_LANG, config=_CONFIG)
        )
    except Exception:
        logger.exception("Preprocessing/OCR failed; relying on original image")

    try:
        original = Image.open(BytesIO(image_bytes)).convert("L")
        candidates.append(
            pytesseract.image_to_string(original, lang=_LANG, config=_CONFIG)
        )
    except Exception:
        logger.exception("OCR on original image failed")

    if not candidates:
        return ""
    return max(candidates, key=_alnum_score)


async def recognize_text(image_bytes: bytes) -> str:
    result: str = await asyncio.to_thread(_run_ocr, image_bytes)
    return result
