"""
Celery Configuration for Background Tasks
Location: app/celery_app.py
"""
from celery import Celery
from app.core.config import settings

# Create Celery instance
celery_app = Celery(
    'nigerian_tax_compliance',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Africa/Lagos',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    result_expires=3600,  # Results expire after 1 hour
    task_acks_late=True,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['app.tasks'])

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery is working"""
    print(f'Request: {self.request!r}')
    return 'Celery is working!'