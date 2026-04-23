# app/core/encryption.py
from cryptography.fernet import Fernet
from app.core.config import settings

_fernet = Fernet(settings.ENCRYPTION_KEY.encode()) # type: ignore

def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()