"""
Application Configuration - QStash Version WITH SECURITY FIXES
Location: app/core/config.py

Enhanced with proper CORS configuration and security settings
PRODUCTION OPTIMIZED: Added rate limiting, pagination, and Nigerian tax settings
"""
from pydantic_settings import BaseSettings # type: ignore
from typing import List, Optional


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
    DB_POOL_SIZE: int = 20  # pydantic reads DB_POOL_SIZE from env automatically
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
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
    # Allow overriding CORS origins via environment variable (comma-separated)
    BACKEND_CORS_ORIGINS: Optional[str] = None
    
    @property
    def BACKEND_CORS_ORIGINS_LIST(self) -> List[str]:
        """
        Get CORS origins based on environment or BACKEND_CORS_ORIGINS env var.
        
        SECURITY: Strict origin control based on environment
        - Production: Only allow specific production domains
        - Staging: Only allow staging domain
        - Development: Only allow localhost
        
        Override with BACKEND_CORS_ORIGINS environment variable (comma-separated).
        """
        # First check if explicitly set via environment variable
        if self.BACKEND_CORS_ORIGINS:
            origins = [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")]
            return origins
        
        # Otherwise, use environment-based defaults
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
    ENCRYPTION_KEY: str

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""


    SMTP_HOST:     str  = "smtp.gmail.com"
    SMTP_PORT:     int  = 587
    SMTP_USER:     str  = ""
    SMTP_PASSWORD: str  = ""
    SMTP_TLS:      bool = True
    SMTP_SSL:      bool = False

    # Email display
    FROM_EMAIL:     str = "noreply@taxcompliance.ng"
    FROM_NAME:      str = "Nigerian Tax Compliance"
    SUPPORT_EMAIL:  str = "support@taxcompliance.ng"
    # paystack keys for payment processing
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    
    # ====================================================================
    # MONITORING (Optional)
    # ====================================================================
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


settings = Settings()  # type: ignore