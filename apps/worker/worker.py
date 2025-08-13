import os
from celery import Celery

BROKER = os.getenv("REDIS_URL")
app = Celery("worker", broker=BROKER, backend=BROKER)
app.conf.update(task_track_started=True)

@app.task
def echo(msg: str):
    return {"echo": msg}
