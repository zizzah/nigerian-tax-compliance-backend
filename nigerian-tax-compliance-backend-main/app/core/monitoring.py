
"""
File: app/core/monitoring.py (CREATE NEW)
"""

import logging
import time
from functools import wraps
from typing import Callable
import sentry_sdk # type: ignore
from sentry_sdk.integrations.fastapi import FastApiIntegration # type: ignore
from app.core.config import settings

# Initialize Sentry for error tracking
if settings.ENVIRONMENT in ["production", "staging"]:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,  # Add to config
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,  # 10% of transactions
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION
    )

# Structured logging
logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def log_performance(func: Callable) -> Callable:
    """Decorator to log function performance"""
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            logging.info(f"{func.__name__} completed in {duration:.3f}s")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logging.error(f"{func.__name__} failed after {duration:.3f}s: {e}")
            raise
    
    return wrapper



