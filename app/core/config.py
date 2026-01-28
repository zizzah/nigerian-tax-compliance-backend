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
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    # AI Services
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    STORAGE_TYPE: str = "local"
    
    # Nigerian Tax
    NIGERIAN_VAT_RATE: float = 7.5
    VAT_REGISTRATION_THRESHOLD: float = 25000000
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()