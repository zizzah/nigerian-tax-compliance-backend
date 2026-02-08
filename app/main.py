"""
FastAPI Main Application with Authentication
Location: app/main.py

FIXED VERSION - Removed async from health endpoints to prevent timeouts
"""
from fastapi import FastAPI, Depends # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
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

from app.core.database import get_db
from app.core.config import settings
from app.api.v1.endpoints import (
    auth, 
    users, 
    businesses, 
    customers, 
    invoices, 
    products, 
    payments,
    documents
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
    """
)

# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ============================================================================
# Exception Handlers
# ============================================================================

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(BaseAPIException, custom_exception_handler)
app.add_exception_handler(DBAPIError, database_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ============================================================================
# Health Check Endpoints - FIXED VERSION (NO ASYNC)
# ============================================================================

@app.get("/", tags=["System"])
def root():
    """
    Ultra-fast root endpoint - no dependency checks
    
    Provides API metadata and service discovery.
    Used for basic connectivity testing.
    
    FIXED: Removed async to prevent timeout issues
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
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
    Fast health check - simplified without asyncio
    
    Checks:
    - Database connectivity (synchronous)
    - Redis connectivity (synchronous)
    
    Returns:
    - 200: Healthy (all critical systems operational)
    - 200: Degraded (Redis down, API still functional)
    - 503: Unhealthy (database down, API cannot function)
    
    Use this for:
    - Load balancer health checks
    - Monitoring systems
    - General health monitoring
    
    FIXED: Removed async/await and asyncio.to_thread to prevent timeouts
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {}
    }
    
    # Database check (CRITICAL) - SYNCHRONOUS
    try:
        # Direct synchronous call - no async wrapper needed
        db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": str(e)[:100]
        }
        # Return 503 if database is down
        return JSONResponse(status_code=503, content=health_status)
    
    # Redis check (NON-CRITICAL) - SYNCHRONOUS
    try:
        import redis # type: ignore
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        client.close()
        health_status["checks"]["redis"] = {"status": "healthy"}
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
        health_status["checks"]["redis"] = {
            "status": "degraded",
            "message": "Redis unavailable"
        }
    
    return health_status


@app.get("/ready", tags=["System"])
def readiness_check(db: Session = Depends(get_db)):
    """
    Kubernetes readiness probe endpoint
    
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