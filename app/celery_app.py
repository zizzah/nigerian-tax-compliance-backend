"""
Celery Configuration for Background Tasks
Location: app/celery_app.py

PRODUCTION VERSION - Includes:
- Windows compatibility
- Celery Beat schedule for stuck document recovery
- Task timeout configuration
- Better error handling
"""
from celery import Celery # type: ignore
from celery.schedules import crontab # type: ignore
from app.core.config import settings
import sys
import platform
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CELERY INSTANCE
# ============================================================================

# Create Celery instance
celery_app = Celery(
    'nigerian_tax_compliance',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.tasks.document_processing']
)

# ============================================================================
# WINDOWS COMPATIBILITY FIX
# ============================================================================

# WINDOWS FIX: Detect platform and use appropriate pool
# prefork doesn't work well on Windows
if platform.system() == 'Windows':
    worker_pool = 'solo'  # Use solo pool on Windows
    worker_concurrency = 1
    logger.info("Running on Windows - using 'solo' worker pool")
else:
    worker_pool = 'prefork'
    worker_concurrency = 2
    logger.info(f"Running on {platform.system()} - using 'prefork' worker pool")

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='Africa/Lagos',
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit per task
    task_soft_time_limit=270,  # 4.5 minutes soft limit (warning)
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Reject task if worker dies
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Only fetch 1 task at a time
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
    worker_pool=worker_pool,
    worker_concurrency=worker_concurrency,
    
    # Results
    result_expires=3600,  # Results expire after 1 hour
    task_ignore_result=False,
    
    # Logging
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    
    # Task imports
    imports=['app.tasks.document_processing'],
)

# ============================================================================
# CELERY BEAT SCHEDULE - AUTOMATIC STUCK DOCUMENT RECOVERY
# ============================================================================

celery_app.conf.beat_schedule = {
    # Recover stuck documents every 10 minutes
    'recover-stuck-documents': {
        'task': 'app.tasks.document_processing.recover_stuck_documents',
        'schedule': 600.0,  # Every 10 minutes (in seconds)
        'options': {
            'expires': 300,  # Task expires after 5 minutes if not executed
        }
    },
    
    # Optional: Clean up old task results every hour
    'cleanup-old-results': {
        'task': 'app.tasks.document_processing.cleanup_old_results',
        'schedule': crontab(minute=0),  # Every hour at minute 0
        'options': {
            'expires': 1800,
        }
    },
    
    # Optional: Generate daily statistics at midnight
    # 'generate-daily-stats': {
    #     'task': 'app.tasks.document_processing.generate_daily_statistics',
    #     'schedule': crontab(hour=0, minute=0),  # Every day at midnight
    #     'options': {
    #         'expires': 3600,
    #     }
    # },
}

# ============================================================================
# TASK ROUTES (Optional - for task prioritization)
# ============================================================================

celery_app.conf.task_routes = {
    'app.tasks.document_processing.process_document': {
        'queue': 'documents',
        'routing_key': 'document.process',
    },
    'app.tasks.document_processing.recover_stuck_documents': {
        'queue': 'maintenance',
        'routing_key': 'maintenance.recover',
    },
    'app.tasks.document_processing.cleanup_old_results': {
        'queue': 'maintenance',
        'routing_key': 'maintenance.cleanup',
    },
}

# ============================================================================
# TASK PRIORITIES (Optional)
# ============================================================================

celery_app.conf.task_default_priority = 5  # Default priority (0-10)
celery_app.conf.task_inherit_parent_priority = True

# ============================================================================
# ERROR HANDLING
# ============================================================================

# Retry settings for failed tasks
celery_app.conf.task_default_retry_delay = 60  # Wait 60 seconds before retry
celery_app.conf.task_max_retries = 3  # Maximum 3 retries

# ============================================================================
# MONITORING & EVENTS
# ============================================================================

# Send task events for monitoring
celery_app.conf.worker_send_task_events = True
celery_app.conf.task_send_sent_event = True

# ============================================================================
# DEBUG TASK
# ============================================================================

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery is working"""
    print(f'Request: {self.request!r}')
    return {
        'status': 'success',
        'message': 'Celery is working!',
        'worker': self.request.hostname,
        'platform': platform.system()
    }

# ============================================================================
# STARTUP LOGGING
# ============================================================================

if __name__ != '__main__':
    logger.info("=" * 70)
    logger.info("CELERY CONFIGURATION")
    logger.info("=" * 70)
    logger.info(f"Platform: {platform.system()}")
    logger.info(f"Worker Pool: {worker_pool}")
    logger.info(f"Concurrency: {worker_concurrency}")
    logger.info(f"Task Time Limit: {celery_app.conf.task_time_limit}s")
    logger.info(f"Soft Time Limit: {celery_app.conf.task_soft_time_limit}s")
    logger.info(f"Beat Schedule: {len(celery_app.conf.beat_schedule)} scheduled tasks")
    logger.info("=" * 70)


# ============================================================================
# CELERY BEAT COMMAND
# ============================================================================
"""
To run Celery Beat (scheduler) for automatic stuck document recovery:

Development:
    celery -A app.celery_app beat --loglevel=info

Production (with worker):
    # Terminal 1 - Worker
    celery -A app.celery_app worker --loglevel=info --concurrency=2
    
    # Terminal 2 - Beat (scheduler)
    celery -A app.celery_app beat --loglevel=info

Docker Compose:
    Add this service to docker-compose.yml:
    
    celery_beat:
        build: .
        command: celery -A app.celery_app beat --loglevel=info
        environment:
            - DATABASE_URL=postgresql://...
            - REDIS_URL=redis://redis:6379/0
        depends_on:
            - db
            - redis
        restart: unless-stopped

Windows:
    # Use eventlet or gevent pool instead of solo for better performance
    pip install eventlet
    celery -A app.celery_app worker --pool=eventlet --loglevel=info
    
    # In separate terminal for beat
    celery -A app.celery_app beat --loglevel=info
"""

# ============================================================================
# HEALTH CHECK FOR CELERY
# ============================================================================

@celery_app.task(bind=True)
def health_check(self):
    """
    Health check task for Celery workers
    
    Returns worker status and configuration info
    """
    return {
        'status': 'healthy',
        'worker': self.request.hostname,
        'platform': platform.system(),
        'pool': worker_pool,
        'concurrency': worker_concurrency,
        'task_time_limit': celery_app.conf.task_time_limit,
        'beat_schedule_count': len(celery_app.conf.beat_schedule),
    }