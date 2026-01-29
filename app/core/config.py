from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Nigerian Tax Compliance API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # AI Services (optional - can be empty for now)
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


settings = Settings() # type: ignore