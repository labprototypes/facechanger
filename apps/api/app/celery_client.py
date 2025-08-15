import os
from celery import Celery

# API тоже должно знать адрес брокера, чтобы публиковать задачи
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(broker=REDIS_URL, backend=REDIS_URL)

def queue_process_sku(sku_id: int):
    # имя задачи = то, что объявлено в воркере @celery.task(name="worker.process_sku")
    return celery.send_task("worker.process_sku", args=[sku_id])

def queue_process_frame(frame_id: int):
    return celery.send_task("worker.process_frame", args=[frame_id])
