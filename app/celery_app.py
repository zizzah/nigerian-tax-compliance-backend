"""
Celery Configuration for Background Tasks
Location: app/celery_app.py

WINDOWS COMPATIBILITY FIX:
- Uses 'solo' pool on Windows (prefork doesn't work well)
- Added better error handling and logging
"""
from celery import Celery # type: ignore
from app.core.config import settings
import sys

# Create Celery instance
celery_app = Celery(
    'nigerian_tax_compliance',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.tasks.document_processing']
)

# WINDOWS FIX: Detect platform and use appropriate pool
# prefork doesn't work well on Windows
import platform
if platform.system() == 'Windows':
    worker_pool = 'solo'  # Use solo pool on Windows
    worker_concurrency = 1
else:
    worker_pool = 'prefork'
    worker_concurrency = 2

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
    
    # Better logging
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    
    # Ensure tasks are imported
    imports=['app.tasks.document_processing'],
    
    # WINDOWS: Use solo pool
    worker_pool=worker_pool,
    worker_concurrency=worker_concurrency,
    
    # Better error handling
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
)

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery is working"""
    print(f'Request: {self.request!r}')
    return 'Celery is working!'


# Print configuration on import
if __name__ != '__main__':
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Celery configured for {platform.system()} with {worker_pool} pool")