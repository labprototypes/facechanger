import os
from celery import Celery
from .config import settings

celery = Celery("fc_publisher", broker=settings.redis_url, backend=settings.redis_url)

def enqueue_process_sku(sku_id: int):
    celery.send_task("worker.process_sku", args=[sku_id])
