"""
FastAPI Main Application — PRODUCTION READY (Render + Neon)
Location: app/main.py

CHANGES FROM PREVIOUS VERSION:
  1. Swagger/ReDoc docs disabled in production
  2. Sentry error tracking initialised before app startup
  3. redirect_slashes=False kept; duplicate-route shim retained
  4. DB pool tuned for Neon (SSL required, pool_recycle=300)
  5. JWT cookie helper updated with httponly / secure / samesite flags
  6. Duplicate-route normalisation still present for trailing-slash 404 fix
"""

# ── Sentry must be imported and initialised BEFORE FastAPI is instantiated ──
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

# ── Standard library ────────────────────────────────────────────────────────
import asyncio
import logging
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager



# ── FastAPI / Starlette ──────────────────────────────────────────────────────
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── App internals ────────────────────────────────────────────────────────────
from app.core.config import settings
from app.core.database import (
    close_db_connections,
    get_db,
)
from app.core.exceptions import (
    BaseAPIException,
    custom_exception_handler,
    database_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.security_middleware import (
    RequestIDMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

# ── Routers ──────────────────────────────────────────────────────────────────
from app.api.v1.endpoints import (
    analytics,
    auth,
    background,
    businesses,
    customers,
    documents,
    expenses,
    invoices,
    payments,
    paystack,
    products,
    reminders,
    targets,
    users,
    insights,
    nlp_invoice,
    reconciliation,
)
from app.api.v1.endpoints.stock_movements import router as stock_router
from app.api.v1.endpoints import tax_calendar


# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# Sentry — initialise BEFORE app is created so all errors are captured
# ============================================================================

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        # Capture 10 % of transactions for performance monitoring.
        # Set to 0.0 to disable performance tracing and reduce overhead.
        traces_sample_rate=0.1,
        # Do NOT send personally identifiable information (emails, IPs, etc.)
        send_default_pii=False,
    )
    logger.info("Sentry initialised (environment=%s)", settings.ENVIRONMENT)
else:
    logger.info("SENTRY_DSN not set — Sentry disabled")

# ============================================================================
# Custom Middleware
# ============================================================================



class RequestTimingMiddleware:
    """Pure ASGI middleware — no BaseHTTPMiddleware buffering overhead."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.time()

        async def send_with_timing(message) -> None:
            if message["type"] == "http.response.start":
                elapsed = time.time() - start
                headers = list(message.get("headers", []))
                headers.append(
                    (b"x-process-time", f"{elapsed:.4f}".encode())
                )
                message = {**message, "headers": headers}
                if elapsed > 1.0:
                    logger.warning(
                        "Slow request: %s took %.2fs",
                        scope.get("path", "unknown"),
                        elapsed,
                    )
            await send(message)

        await self.app(scope, receive, send_with_timing)

class TimeoutMiddleware(BaseHTTPMiddleware):
    """Return 504 if a handler takes longer than *timeout* seconds."""

    def __init__(self, app, timeout: int = 30):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.error("Request timeout: %s", request.url.path)
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "type": "timeout_error",
                        "code": 504,
                        "message": f"Request timed out after {self.timeout}s",
                        "path": str(request.url.path),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )


# ============================================================================
# FastAPI application
# ============================================================================

_is_production = settings.ENVIRONMENT == "production"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    yield
    logger.info("Shutting down — disposing DB engine...")
    await close_db_connections()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    # ── CHANGE 1: Hide API docs in production ──────────────────────────────
    # Exposing /docs in production leaks your entire API surface to attackers.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    # Keep trailing-slash normalisation; the shim below adds duplicate routes.
    redirect_slashes=False,
    description="""
    🇳🇬 Nigerian Tax Compliance Platform API

    ## Getting Started

    1. Register at `/api/v1/auth/register`
    2. Login at `/api/v1/auth/login` to obtain a JWT token
    3. Pass the token as `Authorization: Bearer <token>` on every request
    """,
)

# ============================================================================
# Rate-limiter state (must be set before SlowAPIMiddleware is added)
# ============================================================================

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore

# ============================================================================
# Middleware stack
# (FastAPI executes middleware in REVERSE registration order, so CORS —
#  registered last — runs first and handles OPTIONS pre-flights immediately.)
# ============================================================================

# Innermost: timeout guard
app.add_middleware(TimeoutMiddleware, timeout=30)

# GZip compression for responses > 1 kB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Rate limiting
app.add_middleware(SlowAPIMiddleware)

# Request timing header
app.add_middleware(RequestTimingMiddleware)

# Security response headers (HSTS, CSP, X-Frame-Options, …)
app.add_middleware(SecurityHeadersMiddleware, environment=settings.ENVIRONMENT)

# Unique request-ID header on every response
app.add_middleware(RequestIDMiddleware)

# Reject oversized request bodies
app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=settings.MAX_UPLOAD_SIZE_MB)

# Outermost: CORS — must handle OPTIONS before any auth middleware fires
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS_LIST,
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
    max_age=600,
    expose_headers=["Content-Length", "X-Request-ID", "X-Process-Time"],
)

# ============================================================================
# Routers
# ============================================================================

app.include_router(auth.router,       prefix=settings.API_V1_PREFIX)
app.include_router(users.router,      prefix=settings.API_V1_PREFIX)
app.include_router(businesses.router, prefix=settings.API_V1_PREFIX)
app.include_router(customers.router,  prefix=settings.API_V1_PREFIX)
app.include_router(invoices.router,   prefix=settings.API_V1_PREFIX)
app.include_router(products.router,   prefix=settings.API_V1_PREFIX)
app.include_router(payments.router,   prefix=settings.API_V1_PREFIX)
app.include_router(documents.router,  prefix=settings.API_V1_PREFIX)
app.include_router(background.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router,  prefix=settings.API_V1_PREFIX)
app.include_router(reminders.router,  prefix=settings.API_V1_PREFIX)
app.include_router(paystack.router,   prefix=settings.API_V1_PREFIX)
app.include_router(targets.router,    prefix=settings.API_V1_PREFIX)
app.include_router(expenses.router,   prefix=settings.API_V1_PREFIX)
app.include_router(stock_router,      prefix="/api/v1")
app.include_router(insights.router,        prefix=settings.API_V1_PREFIX)
app.include_router(nlp_invoice.router,     prefix=settings.API_V1_PREFIX)
app.include_router(reconciliation.router,  prefix=settings.API_V1_PREFIX)
app.include_router(tax_calendar.router,    prefix=settings.API_V1_PREFIX)


# ============================================================================
# Trailing-slash normalisation shim
# Adds a hidden duplicate route for every path that ends in "/" so that both
# /api/v1/invoices and /api/v1/invoices/ resolve to the same handler.
# ============================================================================

_routes_to_add = []
for _route in app.routes:
    if isinstance(_route, APIRoute):
        if _route.path.endswith("/") and _route.path != "/":
            _routes_to_add.append(
                APIRoute(
                    path=_route.path.rstrip("/"),
                    endpoint=_route.endpoint,
                    methods=_route.methods,
                    name=_route.name + "_no_slash",
                    response_model=_route.response_model,
                    status_code=_route.status_code,
                    tags=_route.tags,
                    dependencies=_route.dependencies,
                    summary=_route.summary,
                    description=_route.description,
                    response_description=_route.response_description,
                    responses=_route.responses,
                    deprecated=_route.deprecated,
                    operation_id=_route.operation_id,
                    include_in_schema=False,  # keep duplicates out of any docs
                )
            )
for _route in _routes_to_add:
    app.routes.append(_route)

# ============================================================================
# Exception handlers
# ============================================================================

app.add_exception_handler(StarletteHTTPException, http_exception_handler)      # type: ignore
app.add_exception_handler(RequestValidationError, validation_exception_handler) # type: ignore
app.add_exception_handler(BaseAPIException, custom_exception_handler)           # type: ignore
app.add_exception_handler(DBAPIError, database_exception_handler)               # type: ignore
app.add_exception_handler(Exception, general_exception_handler)

# ============================================================================
# Health / readiness endpoints
# ============================================================================


@app.get("/", tags=["System"])
def root():
    """Ultra-fast root endpoint — no dependency checks."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documentation": "/docs" if not _is_production else "disabled in production",
        "endpoints": {
            "health": "/health",
            "alive": "/alive",
            "ready": "/ready",
            "api_base": settings.API_V1_PREFIX,
        },
    }


@app.get("/alive", tags=["System"])
def alive():
    """Kubernetes liveness probe — confirms the process is running."""
    return {"alive": True, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health", tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    health: dict = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }
    try:
        await db.execute(text("SELECT 1"))
        health["checks"]["database"] = {"status": "healthy"}
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
        health["status"] = "unhealthy"
        health["checks"]["database"] = {
            "status": "unhealthy",
            "message": "Database connection failed",
        }
        return JSONResponse(status_code=503, content=health)
    return health

@app.get("/ready", tags=["System"])
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes readiness probe.

    Returns 503 immediately if the database is unavailable so the load
    balancer stops sending traffic to this instance.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"ready": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "error": "Database unavailable",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@app.get("/pool-status", tags=["System"])
async def pool_status():
    """Real-time DB connection-pool statistics (for ops monitoring)."""
    from app.core.database import get_pool_status
    if _is_production:
        return JSONResponse(status_code=404, content={})
        
        

    try:
        return {
            "status": "healthy",
            "pool": await get_pool_status(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Pool status check failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": "Could not retrieve pool status",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


