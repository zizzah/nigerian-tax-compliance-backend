from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import field_validator


class Settings(BaseSettings):
    # ============================================================================
    # APPLICATION SETTINGS
    # ============================================================================
    APP_NAME: str = "Nigerian Tax Compliance API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # ============================================================================
    # DATABASE CONFIGURATION
    # ============================================================================
    DATABASE_URL: str
    TEST_DATABASE_URL: str = ""
    
    # ============================================================================
    # AUTHENTICATION & SECURITY
    # ============================================================================
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
    
    # ============================================================================
    # AI SERVICES
    # ============================================================================
    # Anthropic Claude
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_FAST: str = "claude-haiku-3-5-20250217"
    ANTHROPIC_MODEL_STANDARD: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_ADVANCED: str = "claude-opus-4-5-20251101"
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_VISION_MODEL: str = "gpt-4-vision-preview"
    
    # AI Processing Settings
    AI_MAX_TOKENS: int = 4096
    AI_TEMPERATURE: float = 0.1
    AI_PROCESSING_TIMEOUT: int = 60
    ENABLE_AI_FALLBACK: bool = True
    
    # ============================================================================
    # FILE STORAGE
    # ============================================================================
    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    
    # AWS S3 (optional)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_ENDPOINT_URL: str = ""
    
    # ============================================================================
    # EMAIL CONFIGURATION
    # ============================================================================
    EMAIL_PROVIDER: str = "smtp"
    
    # SMTP Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    
    # Email Display Settings
    FROM_EMAIL: str = "noreply@taxcompliance.ng"
    FROM_NAME: str = "Nigerian Tax Compliance"
    SUPPORT_EMAIL: str = "support@taxcompliance.ng"
    
    # SendGrid (alternative)
    SENDGRID_API_KEY: str = ""
    
    # ============================================================================
    # REDIS CONFIGURATION
    # ============================================================================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""
    REDIS_MAX_CONNECTIONS: int = 10
    
    # Cache Settings
    CACHE_ENABLED: bool = False
    CACHE_DEFAULT_TTL: int = 3600
    CACHE_PREFIX: str = "tax_compliance:"
    
    # ============================================================================
    # CELERY BACKGROUND TASKS
    # ============================================================================
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 300
    
    # ============================================================================
    # MONITORING & LOGGING
    # ============================================================================
    # Sentry Error Tracking
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: str = "./logs/app.log"
    LOG_MAX_SIZE: int = 10485760
    LOG_BACKUP_COUNT: int = 5
    
    # ============================================================================
    # CORS
    # ============================================================================
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # Remove brackets and quotes, then split
            v = v.strip('[]"').replace('"', '').replace("'", "")
            return [origin.strip() for origin in v.split(',')]
        return v
    
    # ============================================================================
    # APPLICATION FEATURES
    # ============================================================================
    # Nigerian Tax Settings
    NIGERIAN_VAT_RATE: float = 7.5
    VAT_REGISTRATION_THRESHOLD: float = 25000000
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    
    # Invoice Settings
    INVOICE_COUNTER_START: int = 1000
    DEFAULT_PAYMENT_TERMS_DAYS: int = 30
    
    # Document Processing
    ENABLE_OCR: bool = True
    ENABLE_AI_EXTRACTION: bool = True
    ENABLE_FRAUD_DETECTION: bool = True
    OCR_CONFIDENCE_THRESHOLD: float = 0.7
    
    # ============================================================================
    # FRONTEND URL
    # ============================================================================
    FRONTEND_URL: str = "http://localhost:3000"
    
    # ============================================================================
    # TESTING
    # ============================================================================
    TESTING: bool = False
    BYPASS_AUTH: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow extra fields from .env that aren't defined here
        extra = "ignore"


settings = Settings() # type: ignore