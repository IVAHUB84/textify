import asyncio
from io import BytesIO

import pytesseract
from PIL import Image


async def recognize_text(image_bytes: bytes) -> str:
    image = Image.open(BytesIO(image_bytes))
    result: str = await asyncio.to_thread(
        pytesseract.image_to_string, image, lang="rus+eng"
    )
    return result
