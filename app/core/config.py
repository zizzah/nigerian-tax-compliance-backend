"""
Application Configuration - QStash Version
Location: app/core/config.py
"""
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore
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
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


settings = Settings()  # type: ignore