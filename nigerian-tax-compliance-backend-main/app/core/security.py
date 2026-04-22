"""
Security utilities
Location: app/core/security.py

PRODUCTION OPTIMIZED: Enhanced with input validation and sanitization
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError # type: ignore
from passlib.context import CryptContext # type: ignore
from app.core.config import settings
import re


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    PRODUCTION OPTIMIZED: Configurable expiration time
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode a JWT token.
    
    PRODUCTION OPTIMIZED: Enhanced error handling
    
    Args:
        token: JWT token to decode
    
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None






def sanitize_input(value: str, max_length: int = 255) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.
    
    PRODUCTION OPTIMIZED: Enhanced sanitization
    
    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    if not value:
        return ""
    
    # Remove null bytes
    value = value.replace('\x00', '')
    
    # Remove or escape potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&']
    for char in dangerous_chars:
        value = value.replace(char, '')
    
    # Trim to max length
    value = value[:max_length]
    
    # Strip whitespace
    value = value.strip()
    
    return value


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    PRODUCTION OPTIMIZED: Enhanced email validation
    
    Args:
        email: Email address to validate
    
    Returns:
        True if valid, False otherwise
    """
    
    if not email or len(email) > 255:
        return False
    
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    return bool(re.match(pattern, email))