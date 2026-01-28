from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Nigerian Tax Compliance API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite:///./test.db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600
    TEST_DATABASE_URL: str = ""
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password Requirements
    MIN_PASSWORD_LENGTH: int = 8
    REQUIRE_PASSWORD_UPPERCASE: bool = True
    REQUIRE_PASSWORD_LOWERCASE: bool = True
    REQUIRE_PASSWORD_DIGIT: bool = True
    REQUIRE_PASSWORD_SPECIAL: bool = False
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    # AI Services - Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_FAST: str = "claude-haiku-3-5-20250217"
    ANTHROPIC_MODEL_STANDARD: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_ADVANCED: str = "claude-opus-4-5-20251101"
    
    # AI Services - OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_VISION_MODEL: str = "gpt-4-vision-preview"
    
    # AI Configuration
    AI_MAX_TOKENS: int = 4096
    AI_TEMPERATURE: float = 0.1
    AI_PROCESSING_TIMEOUT: int = 60
    ENABLE_AI_FALLBACK: bool = True
    
    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "tax-compliance-documents"
    AWS_REGION: str = "us-east-1"
    
    # Email Configuration
    EMAIL_PROVIDER: str = "smtp"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    FROM_EMAIL: str = "noreply@taxcompliance.ng"
    FROM_NAME: str = "Nigerian Tax Compliance"
    SUPPORT_EMAIL: str = "support@taxcompliance.ng"
    SENDGRID_API_KEY: str = ""
    
    # Redis & Caching
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 10
    CACHE_ENABLED: bool = False
    CACHE_DEFAULT_TTL: int = 3600
    CACHE_PREFIX: str = "tax_compliance:"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 300
    
    # Monitoring
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: str = "./logs/app.log"
    LOG_MAX_SIZE: int = 10485760
    LOG_BACKUP_COUNT: int = 5
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    
    # Business Logic
    INVOICE_COUNTER_START: int = 1000
    DEFAULT_PAYMENT_TERMS_DAYS: int = 30
    
    # Feature Flags
    ENABLE_OCR: bool = True
    ENABLE_AI_EXTRACTION: bool = True
    ENABLE_FRAUD_DETECTION: bool = True
    OCR_CONFIDENCE_THRESHOLD: float = 0.7
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    STORAGE_TYPE: str = "local"
    
    # Nigerian Tax
    NIGERIAN_VAT_RATE: float = 7.5
    VAT_REGISTRATION_THRESHOLD: float = 25000000
    
    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Testing
    TESTING: bool = False
    BYPASS_AUTH: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()