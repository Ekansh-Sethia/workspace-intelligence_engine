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

@router.get("/health/llm-test", status_code=200)
async def health_llm_test():
    import urllib.request
    import urllib.error
    import json
    results = {
        "gemini_prefix": (settings.GEMINI_API_KEY or "")[:6],
        "groq_prefix": (settings.GROQ_API_KEY or "")[:6],
    }
    gkey = (settings.GROQ_API_KEY or "").strip("\"' \r\n\t")
    if gkey:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={
                "Authorization": f"Bearer {gkey}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
                models = [m["id"] for m in data.get("data", [])]
                results["groq"] = f"HTTP 200 OK, models={models[:5]}"
        except urllib.error.HTTPError as e:
            results["groq"] = f"HTTP {e.code}: {e.read().decode()[:150]}"
        except Exception as exc:
            results["groq"] = f"Error: {exc}"
    else:
        results["groq"] = "No key"
    return results
