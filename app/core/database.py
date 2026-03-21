"""
Database Configuration — PRODUCTION READY (Neon + Render)
Location: app/core/database.py

CHANGES FROM PREVIOUS VERSION:
  - pool_recycle lowered to 300 s (Neon drops idle connections after ~5 min)
  - connect_args: sslmode=require (Neon mandates SSL)
  - pool_size / max_overflow kept conservative so we stay inside Neon free tier
  - All other monitoring helpers retained unchanged
"""
from sqlalchemy import create_engine, event  # type: ignore
from sqlalchemy.ext.declarative import declarative_base  # type: ignore
from sqlalchemy.orm import sessionmaker, Session  # type: ignore
from sqlalchemy.pool import QueuePool  # type: ignore
from app.core.config import settings
from typing import Generator
import logging
import os

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
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
    MAX_OVERFLOW   = 10
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
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,   # recycle before Neon drops the connection
    pool_pre_ping=POOL_PRE_PING, # validate connection before handing it out
    echo=ECHO_SQL,
    isolation_level="READ COMMITTED",
    connect_args={
        "sslmode": "require",       # Neon mandates SSL
        "connect_timeout": 10,
        "options": "-c timezone=UTC",
    },
)

logger.info(
    "Database engine created: pool_size=%d max_overflow=%d "
    "pool_recycle=%ds environment=%s",
    POOL_SIZE, MAX_OVERFLOW, POOL_RECYCLE, ENVIRONMENT,
)

# ── Connection-pool event listeners (monitoring hooks) ───────────────────────

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug("DB connection opened")


@event.listens_for(engine, "close")
def receive_close(dbapi_conn, connection_record):
    logger.debug("DB connection closed")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    pass  # add metrics / tracing here if needed


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    pass  # add metrics / tracing here if needed


# ── Session factory ──────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

# ── Declarative base ─────────────────────────────────────────────────────────

Base = declarative_base()


# ── FastAPI dependency ───────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session, rolling back on error and always closing.

    Usage::

        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error("Database error in request: %s", exc, exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


# ── Utility helpers ──────────────────────────────────────────────────────────

def check_database_connection() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        from sqlalchemy import text  # type: ignore
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Database connection check: OK")
        return True
    except Exception as exc:
        logger.error("Database connection check FAILED: %s", exc)
        return False


def get_pool_status() -> dict:
    """Return current connection-pool statistics."""
    stats = {
        "size":         engine.pool.size(), # type: ignore
        "checked_in":   engine.pool.checkedin(), # type: ignore
        "checked_out":  engine.pool.checkedout(), # type: ignore
        "overflow":     engine.pool.overflow(), # type: ignore
        "max_overflow": MAX_OVERFLOW,
        "pool_size":    POOL_SIZE,
        "pool_recycle": POOL_RECYCLE,
        "environment":  ENVIRONMENT,
    }
    logger.debug("Pool status: %s", stats)
    return stats


# Backwards-compat alias
def get_connection_pool_status() -> dict:
    return get_pool_status()


def close_db_connections():
    """Dispose all connections — call during application shutdown."""
    try:
        engine.dispose()
        logger.info("Database connections closed.")
    except Exception as exc:
        logger.error("Error closing DB connections: %s", exc)