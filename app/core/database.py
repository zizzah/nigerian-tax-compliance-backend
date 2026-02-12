"""
Database Configuration - WITH SECURITY FIXES
Location: app/core/database.py

Enhanced with production-grade connection pooling
"""
from sqlalchemy import create_engine, event # type: ignore
from sqlalchemy.ext.declarative import declarative_base # type: ignore
from sqlalchemy.orm import sessionmaker, Session # type: ignore
from sqlalchemy.pool import QueuePool # type: ignore
from app.core.config import settings
from typing import Generator
import logging
import os

logger = logging.getLogger(__name__)

# Get environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = settings.DEBUG

# Production-grade connection pool settings
if ENVIRONMENT == "production":
    # Production: Handle high load
    POOL_SIZE = 20          # Max persistent connections
    MAX_OVERFLOW = 30       # Max temporary connections
    POOL_TIMEOUT = 30       # Seconds to wait for connection
    POOL_RECYCLE = 3600     # Recycle connections after 1 hour
    POOL_PRE_PING = True    # Verify connections before use
    ECHO_SQL = False        # Don't log SQL queries
    
elif ENVIRONMENT == "staging":
    # Staging: Moderate load
    POOL_SIZE = 10
    MAX_OVERFLOW = 20
    POOL_TIMEOUT = 30
    POOL_RECYCLE = 3600
    POOL_PRE_PING = True
    ECHO_SQL = False
    
else:
    # Development: Conservative settings
    POOL_SIZE = 5
    MAX_OVERFLOW = 10
    POOL_TIMEOUT = 30
    POOL_RECYCLE = 3600
    POOL_PRE_PING = True
    ECHO_SQL = DEBUG

# Create engine with robust connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    # Connection pool settings
    poolclass=QueuePool,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=POOL_PRE_PING,
    
    # SQL query logging
    echo=ECHO_SQL,
    
    # Transaction isolation level
    isolation_level="READ COMMITTED",
)

logger.info(
    f"Database engine created: "
    f"pool_size={POOL_SIZE}, "
    f"max_overflow={MAX_OVERFLOW}, "
    f"environment={ENVIRONMENT}"
)

# Event listeners for monitoring
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log when a new database connection is established"""
    logger.debug("Database connection opened")

@event.listens_for(engine, "close")
def receive_close(dbapi_conn, connection_record):
    """Log when a connection is closed"""
    logger.debug("Database connection closed")

# Create SessionLocal class
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Create Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session with proper error handling.
    
    Usage:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
        
    except Exception as e:
        # Log the error
        logger.error(f"Database error in request: {e}", exc_info=True)
        
        # Rollback any pending transactions
        db.rollback()
        
        # Re-raise the exception
        raise
        
    finally:
        # Always close the session
        db.close()


def check_database_connection() -> bool:
    """
    Check if database connection is working.
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        db = SessionLocal()
        from sqlalchemy import text # type: ignore
        db.execute(text("SELECT 1"))
        db.close()
        
        logger.info("Database connection check: SUCCESS")
        return True
        
    except Exception as e:
        logger.error(f"Database connection check FAILED: {e}")
        return False


def get_pool_status() -> dict:
    """
    Get current connection pool status for monitoring.
    
    Returns:
        Dictionary with pool statistics
    """
    pool_status = {
        "size": engine.pool.size(),
        "checked_in": engine.pool.checkedin(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow(),
        "max_overflow": MAX_OVERFLOW,
        "pool_size": POOL_SIZE,
    }
    
    logger.debug(f"Connection pool status: {pool_status}")
    
    return pool_status


def close_db_connections():
    """
    Close all database connections gracefully.
    Call this during application shutdown.
    """
    try:
        engine.dispose()
        logger.info("Database connections closed")
        
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")