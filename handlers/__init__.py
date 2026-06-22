from handlers.audio import router as audio_router
from handlers.commands import router as commands_router
from handlers.image import router as image_router
from handlers.text import router as text_router

__all__ = ["audio_router", "commands_router", "image_router", "text_router"]
