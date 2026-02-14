"""
Security utilities
Location: app/core/security.py

PRODUCTION OPTIMIZED: Enhanced with input validation and sanitization
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError # type: ignore
from passlib.context import CryptContext # type: ignore
from fastapi import Depends, HTTPException, status # type: ignore
from fastapi.security import OAuth2PasswordBearer # type: ignore
from sqlalchemy.orm import Session # type: ignore
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User # type: ignore

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    PRODUCTION OPTIMIZED: Enhanced with active user check
    
    Args:
        token: JWT token from request header
        db: Database session
    
    Returns:
        Current user object
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub") # type: ignore
        
        if user_id is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise credentials_exception
    
    # Check if user is active
    if not user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user.
    Additional check to ensure user is active.
    """
    if not current_user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


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
    import re
    
    if not email or len(email) > 255:
        return False
    
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    return bool(re.match(pattern, email))