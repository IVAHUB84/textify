import asyncio
import logging
from io import BytesIO

import pytesseract
from PIL import Image

from services.preprocess import preprocess_image

logger = logging.getLogger(__name__)


def _run_ocr(image_bytes: bytes) -> str:
    try:
        preprocessed = preprocess_image(image_bytes)
        return pytesseract.image_to_string(
            preprocessed, lang="rus+eng", config="--oem 1 --psm 3"
        )
    except Exception:
        logger.exception("Preprocessing failed, falling back to original image")
        try:
            fallback = Image.open(BytesIO(image_bytes)).convert("L")
            return pytesseract.image_to_string(
                fallback, lang="rus+eng", config="--oem 1 --psm 3"
            )
        except Exception:
            logger.exception("Fallback OCR failed, returning empty string")
            return ""


async def recognize_text(image_bytes: bytes) -> str:
    result: str = await asyncio.to_thread(_run_ocr, image_bytes)
    return result
