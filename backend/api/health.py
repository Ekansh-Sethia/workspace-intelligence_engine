from fastapi import APIRouter
from utils.config import settings
from utils.logger import logger

import os

router = APIRouter()

def _get_proc_memory() -> dict:
    mem = {}
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith(("VmRSS:", "VmHWM:", "VmPeak:", "VmSize:")):
                        parts = line.split()
                        mem[parts[0].rstrip(":")] = f"{int(parts[1]) / 1024:.1f} MB"
    except Exception:
        pass
    return mem

@router.get("/health", status_code=200)
async def health_check():
    logger.info("Health check endpoint called")
    return {
        "status": "ok",
        "message": "ContextIQ is running",
        "has_gemini_key": bool(settings.GEMINI_API_KEY),
        "has_groq_key": bool(settings.GROQ_API_KEY),
        "primary_model": settings.LLM_PRIMARY_MODEL,
        "memory": _get_proc_memory(),
    }
