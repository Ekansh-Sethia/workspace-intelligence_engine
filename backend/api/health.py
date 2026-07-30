from fastapi import APIRouter
from utils.logger import logger

router = APIRouter()

@router.get("/health", status_code=200)
async def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok", "message": "Workspace Intelligence Engine is running"}
