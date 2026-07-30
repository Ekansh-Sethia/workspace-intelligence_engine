from celery import Celery
from utils.config import settings
from utils.logger import logger

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workspaces.tasks"]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # 1 hour max
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

logger.info("Celery worker initialized")
