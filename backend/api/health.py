from fastapi import APIRouter
from utils.config import settings
from utils.logger import logger

router = APIRouter()

@router.get("/health", status_code=200)
async def health_check():
    logger.info("Health check endpoint called")
    return {
        "status": "ok",
        "message": "ContextIQ is running",
        "has_gemini_key": bool(settings.GEMINI_API_KEY),
        "has_groq_key": bool(settings.GROQ_API_KEY),
        "primary_model": settings.LLM_PRIMARY_MODEL,
    }
