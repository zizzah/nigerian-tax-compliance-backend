"""
Application Configuration - QStash Version WITH SECURITY FIXES
Location: app/core/config.py

Enhanced with proper CORS configuration and security settings
PRODUCTION OPTIMIZED: Added rate limiting, pagination, and Nigerian tax settings
"""
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore
from typing import List, Optional
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Nigerian Tax Compliance API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str
    TEST_DATABASE_URL: Optional[str] = None
    
    # Database Pool Settings (for enhanced database.py)
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "30"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password Requirements
    MIN_PASSWORD_LENGTH: int = 8
    REQUIRE_PASSWORD_UPPERCASE: bool = True
    REQUIRE_PASSWORD_LOWERCASE: bool = True
    REQUIRE_PASSWORD_DIGIT: bool = True
    REQUIRE_PASSWORD_SPECIAL: bool = False
    
    # ====================================================================
    # AI API KEYS
    # ====================================================================
    GROQ_API_KEY: str
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # ====================================================================
    # QSTASH (SERVERLESS BACKGROUND TASKS) - REPLACES REDIS/CELERY
    # ====================================================================
    QSTASH_TOKEN: str
    QSTASH_CURRENT_SIGNING_KEY: str
    QSTASH_NEXT_SIGNING_KEY: str
    
    # Render deployment URL (set this in Render dashboard)
    RENDER_EXTERNAL_URL: Optional[str] = None
    
    # ====================================================================
    # FILE UPLOAD SETTINGS
    # ====================================================================
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    
    # ====================================================================
    # OCR SETTINGS
    # ====================================================================
    TESSERACT_CMD: Optional[str] = None
    
    # ====================================================================
    # CORS SETTINGS - SECURITY ENHANCED
    # ====================================================================
    @property
    def BACKEND_CORS_ORIGINS(self) -> List[str]:
        """
        Get CORS origins based on environment.
        
        SECURITY: Strict origin control based on environment
        - Production: Only allow specific production domains
        - Staging: Only allow staging domain
        - Development: Only allow localhost
        """
        if self.ENVIRONMENT == "production":
            # IMPORTANT: Replace these with your actual production domains
            return [
                "https://yourdomain.com",
                "https://app.yourdomain.com",
                "https://www.yourdomain.com",
            ]
        elif self.ENVIRONMENT == "staging":
            # IMPORTANT: Replace with your staging domain
            return [
                "https://staging.yourdomain.com",
            ]
        else:
            # Development: localhost only
            return [
                "http://localhost:3000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
            ]
    
    # ====================================================================
    # RATE LIMITING - PRODUCTION OPTIMIZED
    # ====================================================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory://"  # Use "redis://localhost:6379" in production
    RATE_LIMIT_PER_MINUTE: int = 200  # Global rate limit
    
    # ====================================================================
    # PAGINATION SETTINGS - NEW
    # ====================================================================
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 1000
    
    # ====================================================================
    # NIGERIAN TAX SETTINGS - NEW
    # ====================================================================
    VAT_RATE: float = 0.075  # 7.5%
    WHT_RATE: float = 0.05   # 5%
    
    # ====================================================================
    # MONITORING (Optional)
    # ====================================================================
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


settings = Settings()  # type: ignore