"""
Rate Limiting Module
Location: app/core/rate_limit.py

CRITICAL SECURITY: Prevents brute force attacks and API abuse
"""

from slowapi import Limiter # type: ignore
from slowapi.util import get_remote_address # type: ignore
from slowapi.errors import RateLimitExceeded # type: ignore
from fastapi import Request, Response # type: ignore
from fastapi.responses import JSONResponse # type: ignore
import logging

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # Global default
    storage_uri="memory://",  # Use Redis in production: "redis://localhost:6379"
)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom handler for rate limit exceeded"""
    logger.warning(f"Rate limit exceeded: {get_remote_address(request)}")
    
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "type": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after_seconds": 60
            }
        }
    )