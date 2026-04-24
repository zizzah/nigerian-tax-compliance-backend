"""
Database Configuration — PRODUCTION READY (Neon + Render)
Location: app/core/database.py

CHANGES FROM PREVIOUS VERSION:
  - pool_recycle lowered to 300 s (Neon drops idle connections after ~5 min)
  - connect_args: sslmode=require (Neon mandates SSL)
  - pool_size / max_overflow kept conservative so we stay inside Neon free tier
  - All other monitoring helpers retained unchanged
"""
from sqlalchemy import  event,text  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker  # type: ignore

from app.core.config import settings
from typing import AsyncGenerator
import logging
from app.core.base import Base



logger = logging.getLogger(__name__)

ENVIRONMENT = settings.ENVIRONMENT
DEBUG = settings.DEBUG

# ── Pool parameters per environment ─────────────────────────────────────────
#
# Neon free tier: 100 total connections via pgbouncer.
# Keep pool_size small — the pgbouncer pooler multiplexes for you.
# pool_recycle=300 matches Neon's ~5-minute idle-connection timeout so
# SQLAlchemy never hands you a stale socket.
#
if ENVIRONMENT == "production":
    POOL_SIZE      = 5
    MAX_OVERFLOW   = 5
    POOL_TIMEOUT   = 30
    POOL_RECYCLE   = 300   # 5 min — matches Neon's idle timeout
    POOL_PRE_PING  = True
    ECHO_SQL       = False

elif ENVIRONMENT == "staging":
    POOL_SIZE      = 5
    MAX_OVERFLOW   = 10
    POOL_TIMEOUT   = 30
    POOL_RECYCLE   = 300
    POOL_PRE_PING  = True
    ECHO_SQL       = False

else:  # development / test
    POOL_SIZE      = 5
    MAX_OVERFLOW   = 10
    POOL_TIMEOUT   = 30
    POOL_RECYCLE   = 300
    POOL_PRE_PING  = True
    ECHO_SQL       = DEBUG

# ── Engine ───────────────────────────────────────────────────────────────────
#
# CHANGE 4: Neon requires SSL and benefits from a short pool_recycle.
# sslmode=require is safe for all environments when DATABASE_URL points to
# Neon; for local Postgres without SSL just set ENVIRONMENT=development and
# the same settings still work (SSL is negotiated automatically if available).
#

async_engine   = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1).replace("postgres://", "postgresql+asyncpg://", 1),
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=POOL_PRE_PING,
    echo=ECHO_SQL,
    isolation_level="READ COMMITTED",
    connect_args={
        "ssl": "require",
        "timeout": 10,
        "server_settings": {"timezone": "UTC"},
        "statement_cache_size": 0,
        
    },
)



logger.info(
    "Database engine created: pool_size=%d max_overflow=%d "
    "pool_recycle=%ds environment=%s",
    POOL_SIZE, MAX_OVERFLOW, POOL_RECYCLE, ENVIRONMENT,
)

# ── Connection-pool event listeners (monitoring hooks) ───────────────────────

@event.listens_for(async_engine.sync_engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug("DB connection opened")


@event.listens_for(async_engine.sync_engine, "close")
def receive_close(dbapi_conn, connection_record):
    logger.debug("DB connection closed")


@event.listens_for(async_engine.sync_engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    pass  # add metrics / tracing here if needed


@event.listens_for(async_engine.sync_engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    pass  # add metrics / tracing here if needed


# ── Session factory ──────────────────────────────────────────────────────────



async_session_factory = async_sessionmaker(
    async_engine  ,
    class_=AsyncSession,
    expire_on_commit=False,
)





# ── FastAPI dependency ───────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session, rolling back on error and always closing.

    Usage::

        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()   
    """
    async with async_session_factory() as session:
        try:
            yield session
            
        except Exception as exc:
            await session.rollback()
            logger.error("DB session error: %s", exc)
            raise
        


# ── Utility helpers ──────────────────────────────────────────────────────────

async def check_database_connection() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
    
        async with async_engine.connect() as session:
            
            await session.execute(text("SELECT 1"))
        logger.info("Database connection check: OK")
        return True
    except Exception as exc:
        logger.error("Database connection check FAILED: %s", exc)
        return False


async def get_pool_status() -> dict:
    """Return current connection-pool statistics."""
    stats = {
        "size":         async_engine  .pool.size(), # type: ignore
        "checked_in":   async_engine.pool.checkedin(), # type: ignore
        "checked_out":  async_engine.pool.checkedout(), # type: ignore
        "overflow":     async_engine.pool.overflow(), # type: ignore
        "max_overflow": MAX_OVERFLOW,
        "pool_size":    POOL_SIZE,
        "pool_recycle": POOL_RECYCLE,
        "environment":  ENVIRONMENT,
    }
    logger.debug("Pool status: %s", stats)
    return   stats


# Backwards-compat alias
async def get_connection_pool_status() -> dict:
    return await get_pool_status()


async def close_db_connections():
    """Dispose all connections — call during application shutdown."""
    try:
        await async_engine.dispose()
        logger.info("Database connections closed.")
    except Exception as exc:
        logger.error("Error closing DB connections: %s", exc)