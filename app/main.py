"""
FastAPI Main Application with Authentication
Location: app/main.py

FIXED VERSION - Removed async from health endpoints to prevent timeouts
WITH SECURITY FIXES: Rate limiting, security headers, HTTPS enforcement
PRODUCTION OPTIMIZED: Enhanced with request timing and monitoring

FIX APPLIED: Added SlowAPIMiddleware to enable rate limiting
"""
from fastapi import FastAPI, Depends # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.middleware.gzip import GZipMiddleware # type: ignore
from starlette.middleware.base import BaseHTTPMiddleware # type: ignore
from starlette.requests import Request # type: ignore
from starlette.exceptions import HTTPException as StarletteHTTPException # type: ignore
from fastapi.exceptions import RequestValidationError # type: ignore

from datetime import datetime, timezone
from sqlalchemy import text # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy.exc import DBAPIError # type: ignore

import asyncio
import logging
import time

from app.core.database import get_db, check_database_connection, close_db_connections
from app.core.config import settings

# SECURITY: Import security middleware and rate limiting
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware, # type: ignore
    RequestIDMiddleware
)
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded # type: ignore
from slowapi.middleware import SlowAPIMiddleware # type: ignore

from app.api.v1.endpoints import (
    auth, 
    users, 
    businesses, 
    customers, 
    invoices, 
    products, 
    payments,
    documents,
    background  # QStash callback endpoint
)
from app.core.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    custom_exception_handler,
    general_exception_handler,
    database_exception_handler,
    BaseAPIException
)

# ============================================================================
# Logging Configuration
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# Request Timing Middleware - PRODUCTION OPTIMIZED
# ============================================================================

class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Track request processing time and log slow requests
    
    PRODUCTION OPTIMIZED: Adds X-Process-Time header to all responses
    and logs warnings for requests taking > 1 second
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add processing time to response headers
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        
        # Log slow requests (> 1 second)
        if process_time > 1.0:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {process_time:.2f}s",
                extra={
                    "path": str(request.url.path),
                    "method": request.method,
                    "process_time": process_time
                }
            )
        
        return response


# ============================================================================
# Timeout Middleware - Prevents Hanging Requests
# ============================================================================

class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Prevent requests from hanging forever
    
    Times out requests after 30 seconds (configurable)
    """
    
    def __init__(self, app, timeout: int = 30):
        super().__init__(app)
        self.timeout = timeout
    
    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Request timeout: {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "type": "timeout_error",
                        "code": 504,
                        "message": f"Request timed out after {self.timeout}s",
                        "path": str(request.url.path),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            )


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
    description="""
    🇳🇬 Nigerian Tax Compliance Platform API
    
    ## Features
    
    * **Authentication** - JWT-based user authentication
    * **Invoicing** - Create and manage invoices
    * **Documents** - Upload receipts with AI-powered OCR
    * **VAT Tracking** - Automated VAT calculations and compliance
    * **AI Insights** - Financial intelligence and recommendations
    
    ## Getting Started
    
    1. Register a new account at `/api/v1/auth/register`
    2. Login at `/api/v1/auth/login` to get your JWT token
    3. Use the token in the 'Authorize' button above (top right)
    4. Start using protected endpoints!
    
    ## Performance
    
    - Optimized database connection pooling
    - Request timing headers (X-Process-Time)
    - Automatic slow request logging
    - Production-grade rate limiting
    """
)

# ============================================================================
# Middleware Configuration - PRODUCTION OPTIMIZED
# ============================================================================

# SECURITY: Add rate limiter state (REQUIRED for rate limiting to work)
app.state.limiter = limiter

# SECURITY: Add rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler) # type: ignore

# ============================================================================
# FIX: Add SlowAPI Middleware (CRITICAL for rate limiting)
# ============================================================================
app.add_middleware(SlowAPIMiddleware)

# PRODUCTION: Request timing middleware (track performance)
app.add_middleware(RequestTimingMiddleware)

# SECURITY 1: Security Headers (all environments)
app.add_middleware(
    SecurityHeadersMiddleware,
    environment=settings.ENVIRONMENT
)

# SECURITY 2: Request ID (for tracing and debugging)
app.add_middleware(RequestIDMiddleware)

# SECURITY 3: Request Size Limit (prevent DoS attacks)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_size_mb=settings.MAX_UPLOAD_SIZE_MB
)

# SECURITY 4: CORS Middleware - STRICT CONFIGURATION
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS_LIST,  # Strict origins from config
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Requested-With",
    ],
    max_age=600,  # Cache preflight for 10 minutes
    expose_headers=["Content-Length", "X-Request-ID", "X-Process-Time"]  # Expose timing
)

# PRODUCTION: GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Timeout Middleware - Must be added AFTER CORS
app.add_middleware(TimeoutMiddleware, timeout=30)

# ============================================================================
# Router Registration
# ============================================================================

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(businesses.router, prefix=settings.API_V1_PREFIX)
app.include_router(customers.router, prefix=settings.API_V1_PREFIX)
app.include_router(invoices.router, prefix=settings.API_V1_PREFIX)
app.include_router(products.router, prefix=settings.API_V1_PREFIX)
app.include_router(payments.router, prefix=settings.API_V1_PREFIX)
app.include_router(documents.router, prefix=settings.API_V1_PREFIX)
app.include_router(background.router, prefix=settings.API_V1_PREFIX)

# ============================================================================
# Exception Handlers
# ============================================================================

app.add_exception_handler(StarletteHTTPException, http_exception_handler) # type: ignore
app.add_exception_handler(RequestValidationError, validation_exception_handler) # type: ignore
app.add_exception_handler(BaseAPIException, custom_exception_handler)  # type: ignore
app.add_exception_handler(DBAPIError, database_exception_handler) # type: ignore
app.add_exception_handler(Exception, general_exception_handler)

# ============================================================================
# Health Check Endpoints - PRODUCTION OPTIMIZED
# ============================================================================

@app.get("/", tags=["System"])
def root():
    """
    Ultra-fast root endpoint - no dependency checks
    
    Provides API metadata and service discovery.
    Used for basic connectivity testing.
    
    FIXED: Removed async to prevent timeout issues
    PRODUCTION OPTIMIZED: Added version and environment info
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documentation": "/docs",
        "endpoints": {
            "health": "/health",
            "alive": "/alive",
            "ready": "/ready",
            "api_base": settings.API_V1_PREFIX
        }
    }


@app.get("/alive", tags=["System"])
def alive():
    """
    Kubernetes liveness probe - no dependency checks
    
    Simple check that the application process is running.
    Does not check database, Redis, or other dependencies.
    
    Use this for:
    - Kubernetes liveness probes
    - Container health checks
    - Uptime monitoring
    
    FIXED: Removed async to prevent timeout issues
    """
    return {
        "alive": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """
    Fast health check - PRODUCTION OPTIMIZED
    
    Checks:
    - Database connectivity (using optimized check_database_connection)
    
    Returns:
    - 200: Healthy (all critical systems operational)
    - 503: Unhealthy (database down, API cannot function)
    
    Use this for:
    - Load balancer health checks
    - Monitoring systems
    - General health monitoring
    
    PRODUCTION OPTIMIZED: Uses enhanced database connection check
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }
    
    # Database check (CRITICAL) - Using enhanced function
    if check_database_connection():
        health_status["checks"]["database"] = {"status": "healthy"}
    else:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": "Database connection failed"
        }
        # Return 503 if database is down
        return JSONResponse(status_code=503, content=health_status)
    
    return health_status


@app.get("/ready", tags=["System"])
def readiness_check(db: Session = Depends(get_db)):
    """
    Kubernetes readiness probe endpoint - PRODUCTION OPTIMIZED
    
    Returns 200 only if critical services (database) are available.
    Unlike /health, this returns 503 immediately if database is down.
    
    Use this for:
    - Kubernetes readiness probes
    - Load balancer backend pool checks
    - Determining if instance can receive traffic
    
    FIXED: Removed async/await to prevent timeouts
    """
    try:
        # Quick database check - synchronous
        db.execute(text("SELECT 1"))
        
        return {
            "ready": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "error": str(e)[:200],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# ============================================================================
# Connection Pool Status Endpoint - NEW (for monitoring)
# ============================================================================

@app.get("/pool-status", tags=["System"])
def pool_status():
    """
    Get database connection pool statistics
    
    PRODUCTION OPTIMIZED: Real-time pool monitoring
    
    Use this for:
    - Monitoring connection pool health
    - Debugging connection issues
    - Performance tuning
    """
    from app.core.database import get_pool_status
    
    try:
        pool_stats = get_pool_status()
        return {
            "status": "healthy",
            "pool": pool_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Pool status check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# ============================================================================
# Shutdown Event - Close database connections gracefully
# ============================================================================

@app.on_event("shutdown")
def shutdown_event():
    """
    Gracefully close database connections on shutdown
    
    PRODUCTION OPTIMIZED: Ensures clean shutdown
    """
    logger.info("Shutting down application...")
    close_db_connections()
    logger.info("Application shutdown complete")


# ============================================================================
# Prometheus Metrics (Optional - uncomment if using Prometheus)
# ============================================================================

# from prometheus_client import Counter, Histogram, generate_latest
# from prometheus_fastapi_instrumentator import Instrumentator

# # Request metrics
# request_count = Counter(
#     'http_requests_total', 
#     'Total HTTP requests', 
#     ['method', 'endpoint', 'status']
# )
# request_duration = Histogram(
#     'http_request_duration_seconds', 
#     'HTTP request duration'
# )

# # Document processing metrics
# doc_processed = Counter(
#     'documents_processed_total', 
#     'Total documents processed', 
#     ['status']
# )
# doc_processing_time = Histogram(
#     'document_processing_seconds', 
#     'Document processing time'
# )

# # Initialize instrumentator
# Instrumentator().instrument(app).expose(app)


# ============================================================================
# Sentry Error Tracking (Optional - uncomment if using Sentry)
# ============================================================================

# import sentry_sdk
# from sentry_sdk.integrations.fastapi import FastApiIntegration
# from sentry_sdk.integrations.celery import CeleryIntegration

# if hasattr(settings, 'SENTRY_DSN') and settings.SENTRY_DSN:
#     sentry_sdk.init(
#         dsn=settings.SENTRY_DSN,
#         integrations=[
#             FastApiIntegration(),
#             CeleryIntegration()
#         ],
#         traces_sample_rate=0.1,  # 10% of transactions
#         environment=settings.ENVIRONMENT
#     )