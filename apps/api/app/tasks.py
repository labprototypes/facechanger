from .celery_app import celery_app
import time

@celery_app.task
def task_mask(frame_id: int):
    time.sleep(1)
    return {"frame_id": frame_id, "mask_url": "s3://.../mask.png"}

@celery_app.task
def task_replicate(version_id: int):
    time.sleep(2)
    return {"version_id": version_id, "outputs": ["s3://.../res1.jpg", "s3://.../res2.jpg", "s3://.../res3.jpg"]}
