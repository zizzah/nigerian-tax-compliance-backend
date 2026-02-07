"""
FastAPI Main Application with Authentication
Location: app/main.py
"""
from fastapi import FastAPI # type: ignore

from datetime import datetime, timezone
from fastapi.responses import JSONResponse # type: ignore
from sqlalchemy import text # type: ignore
from app.core.database import get_db
from sqlalchemy.orm import Session # type: ignore
from fastapi import Depends # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from app.core.config import settings
from app.api.v1.endpoints import (
    auth, 
    users, 
    businesses, 
    customers, 
    invoices, 
    products, 
    payments
)
from app.api.v1.endpoints import documents
from app.core.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    custom_exception_handler,
    general_exception_handler,
    database_exception_handler,
    BaseAPIException
)
from starlette.exceptions import HTTPException as StarletteHTTPException # type: ignore
from fastapi.exceptions import RequestValidationError # type: ignore
from sqlalchemy.exc import DBAPIError # type: ignore




# Import routers (we'll create these files)
# Note: You'll need to create these files in app/api/v1/endpoints/
# from app.api.v1.endpoints import auth, users

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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)


# Add to routers
app.include_router(businesses.router, prefix=settings.API_V1_PREFIX)
app.include_router(customers.router, prefix=settings.API_V1_PREFIX)

app.include_router(invoices.router, prefix=settings.API_V1_PREFIX)
app.include_router(products.router, prefix=settings.API_V1_PREFIX)
app.include_router(payments.router, prefix=settings.API_V1_PREFIX)


# Add with other router registrations:
app.include_router(documents.router, prefix=settings.API_V1_PREFIX)


app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(BaseAPIException, custom_exception_handler)
app.add_exception_handler(DBAPIError, database_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ============================================================================
# Include Routers (Add these as you create the endpoint files)
# ============================================================================

# Example of how to include routers:
# app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
# app.include_router(users.router, prefix=settings.API_V1_PREFIX)

# TODO: Uncomment above lines after creating the endpoint files


# ============================================================================
# Root Endpoints
# ============================================================================


@app.get("/", tags=["System"], response_model=dict)
async def root():
    """
    Root endpoint - API information and service discovery
    
    Provides:
    - API metadata
    - Environment information
    - Available endpoints
    - Documentation links
    
    Used for API discovery and basic connectivity testing.
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json"
        },
        "endpoints": {
            "health": "/health",
            "api_base": settings.API_V1_PREFIX,
            "authentication": f"{settings.API_V1_PREFIX}/auth",
            "businesses": f"{settings.API_V1_PREFIX}/businesses",
            "customers": f"{settings.API_V1_PREFIX}/customers",
            "products": f"{settings.API_V1_PREFIX}/products",
            "invoices": f"{settings.API_V1_PREFIX}/invoices",
            "payments": f"{settings.API_V1_PREFIX}/payments",
            "documents": f"{settings.API_V1_PREFIX}/documents"
        },
        "support": {
            "email": "support@yourdomain.com",
            "documentation": "https://docs.yourdomain.com"
        }
    }


@app.get("/health", tags=["System"])
async def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check endpoint
    
    Checks:
    - API responsiveness ✓
    - Database connectivity ✓
    - Redis connectivity (Celery broker) ✓
    - Celery workers status ✓
    
    Returns:
    - 200: Healthy (all systems operational)
    - 200: Degraded (some non-critical systems down)
    - 503: Unhealthy (critical systems down)
    
    This endpoint is used by:
    - Load balancers for health checks
    - Kubernetes liveness/readiness probes
    - Monitoring systems (Datadog, New Relic)
    - Uptime monitors (UptimeRobot, Pingdom)
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {}
    }
    
    # 1. Database check (CRITICAL)
    try:
        result = db.execute(text("SELECT 1"))
        db.commit()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "type": "postgresql",
            "message": "Database connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "type": "postgresql",
            "message": f"Database connection failed: {str(e)[:100]}"
        }
    
    # 2. Redis check (NON-CRITICAL - for Celery)
    try:
        import redis # type: ignore
        redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        redis_client.ping()
        redis_client.close()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful"
        }
    except Exception as e:
        # Redis is not critical - API can function without Celery
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
        health_status["checks"]["redis"] = {
            "status": "degraded",
            "message": f"Redis unavailable: {str(e)[:100]}"
        }
    
    # 3. Celery workers check (NON-CRITICAL)
    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        workers = inspect.active()
        
        if workers and len(workers) > 0:
            health_status["checks"]["celery"] = {
                "status": "healthy",
                "workers_count": len(workers),
                "message": f"{len(workers)} Celery worker(s) active"
            }
        else:
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
            health_status["checks"]["celery"] = {
                "status": "degraded",
                "workers_count": 0,
                "message": "No active Celery workers detected"
            }
    except Exception as e:
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
        health_status["checks"]["celery"] = {
            "status": "degraded",
            "message": f"Celery check failed: {str(e)[:100]}"
        }
    
    # 4. Disk space check (NON-CRITICAL)
    try:
        import shutil
        disk_usage = shutil.disk_usage("/")
        free_gb = disk_usage.free / (1024 ** 3)
        total_gb = disk_usage.total / (1024 ** 3)
        percent_free = (disk_usage.free / disk_usage.total) * 100
        
        if percent_free < 10:
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
            disk_status = "warning"
        else:
            disk_status = "healthy"
        
        health_status["checks"]["disk_space"] = {
            "status": disk_status,
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "percent_free": round(percent_free, 1),
            "message": f"{round(free_gb, 1)}GB free of {round(total_gb, 1)}GB"
        }
    except Exception as e:
        health_status["checks"]["disk_space"] = {
            "status": "unknown",
            "message": f"Could not check disk space: {str(e)[:100]}"
        }
    
    # 5. Memory check (INFORMATIONAL)
    try:
        import psutil
        memory = psutil.virtual_memory()
        health_status["checks"]["memory"] = {
            "status": "healthy",
            "percent_used": memory.percent,
            "available_gb": round(memory.available / (1024 ** 3), 2),
            "total_gb": round(memory.total / (1024 ** 3), 2)
        }
    except ImportError:
        # psutil not installed - skip
        pass
    except Exception as e:
        health_status["checks"]["memory"] = {
            "status": "unknown",
            "message": f"Could not check memory: {str(e)[:100]}"
        }
    
    # Determine HTTP status code
    if health_status["status"] == "unhealthy":
        return JSONResponse(
            status_code=503,
            content=health_status
        )
    elif health_status["status"] == "degraded":
        # Return 200 but with degraded status
        # This allows load balancers to keep the instance alive
        # while alerting that something is wrong
        return JSONResponse(
            status_code=200,
            content=health_status
        )
    
    return health_status


# Additional utility endpoint for readiness check
@app.get("/ready", tags=["System"])
async def readiness_check(db: Session = Depends(get_db)):
    """
    Kubernetes readiness probe endpoint
    
    Returns 200 only if critical services are available.
    Unlike /health, this returns 503 if anything is wrong.
    
    Use this for:
    - Kubernetes readiness probes
    - Load balancer backend pool checks
    """
    try:
        # Check database
        db.execute(text("SELECT 1"))
        db.commit()
        
        return {
            "ready": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "error": str(e)[:200],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# Additional utility endpoint for liveness check
@app.get("/alive", tags=["System"])
async def liveness_check():
    """
    Kubernetes liveness probe endpoint
    
    Simple check that the application is running.
    Does not check dependencies.
    
    Use this for:
    - Kubernetes liveness probes
    - Simple uptime monitoring
    """
    return {
        "alive": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION
    }
