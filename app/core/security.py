"""
Enhanced Security Utilities
JWT token generation, password hashing, and authentication helpers
"""

from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import secrets
import uuid

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security
security = HTTPBearer()


# ============================================================================
# PASSWORD FUNCTIONS
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database
        
    Returns:
        bool: True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt
    
    Args:
        password: Plain text password
        
    Returns:
        str: Hashed password
    """
    return pwd_context.hash(password)


# ============================================================================
# TOKEN FUNCTIONS
# ============================================================================

def create_access_token(
    data: Dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Data to encode in token (typically {"sub": user_id})
        expires_delta: Custom expiration time
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(data: Dict) -> str:
    """
    Create a JWT refresh token (longer expiration)
    
    Args:
        data: Data to encode in token (typically {"sub": user_id})
        
    Returns:
        str: Encoded JWT refresh token
    """
    to_encode = data.copy()
    
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict]:
    """
    Decode and validate a JWT token
    
    Args:
        token: JWT token to decode
        
    Returns:
        dict: Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def verify_token(token: str, token_type: str = "access") -> str:
    """
    Verify token and return user ID
    
    Args:
        token: JWT token
        token_type: Expected token type (access or refresh)
        
    Returns:
        str: User ID from token
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify token type
    if payload.get("type") != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected {token_type}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: str = payload.get("sub") # type: ignore
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id


# ============================================================================
# TOKEN GENERATION HELPERS
# ============================================================================

def generate_verification_token() -> str:
    """Generate a secure random verification token"""
    return secrets.token_urlsafe(32)


def generate_reset_token() -> str:
    """Generate a secure random password reset token"""
    return secrets.token_urlsafe(32)


# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    
    This is a FastAPI dependency that extracts and validates the JWT token,
    then retrieves the user from the database.
    
    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session
        
    Returns:
        User: Authenticated user object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    # Verify and decode token
    user_id = verify_token(token, token_type="access")
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user (alias for get_current_user)
    
    Args:
        current_user: Current user from get_current_user dependency
        
    Returns:
        User: Active user object
    """
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current verified user (email verified)
    
    Args:
        current_user: Current user from get_current_user dependency
        
    Returns:
        User: Verified user object
        
    Raises:
        HTTPException: If user email is not verified
    """
    if not current_user.is_verified: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email first."
        )
    
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current superuser (admin)
    
    Args:
        current_user: Current user from get_current_user dependency
        
    Returns:
        User: Superuser object
        
    Raises:
        HTTPException: If user is not a superuser
    """
    if not current_user.is_superuser: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required."
        )
    
    return current_user


# ============================================================================
# USER AUTHENTICATION
# ============================================================================

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate user by email and password
    
    Args:
        db: Database session
        email: User email
        password: Plain text password
        
    Returns:
        User: User object if authentication successful, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        return None
    
    if not verify_password(password, user.password_hash): # type: ignore
        return None
    
    return user


def check_user_locked(user: User) -> bool:
    """
    Check if user account is locked due to failed login attempts
    
    Args:
        user: User object
        
    Returns:
        bool: True if account is locked, False otherwise
    """
    if user.locked_until is None:
        return False
    
    if datetime.utcnow() < user.locked_until:
        return True
    
    # Lock period expired, reset
    return False


def record_failed_login(db: Session, user: User) -> None:
    """
    Record a failed login attempt and lock account if necessary
    
    Args:
        db: Database session
        user: User object
    """
    user.failed_login_attempts += 1
    
    # Lock account after 5 failed attempts for 30 minutes
    if user.failed_login_attempts >= 5:
        user.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    db.commit()


def reset_failed_logins(db: Session, user: User) -> None:
    """
    Reset failed login attempts on successful login
    
    Args:
        db: Database session
        user: User object
    """
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow() # type: ignore
    db.commit()


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

def verify_user_email(db: Session, user: User) -> None:
    """
    Mark user email as verified
    
    Args:
        db: Database session
        user: User object
    """
    user.is_verified = True # type: ignore
    user.email_verified_at = datetime.utcnow() # pyright: ignore[reportAttributeAccessIssue]
    user.verification_token = None
    db.commit()


# ============================================================================
# PASSWORD RESET
# ============================================================================

def create_password_reset_token(db: Session, user: User) -> str:
    """
    Create password reset token for user
    
    Args:
        db: Database session
        user: User object
        
    Returns:
        str: Reset token
    """
    reset_token = generate_reset_token()
    user.reset_token = reset_token
    user.reset_token_expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()
    
    return reset_token


def verify_reset_token(db: Session, token: str) -> Optional[User]:
    """
    Verify password reset token and return user
    
    Args:
        db: Database session
        token: Reset token
        
    Returns:
        User: User object if token is valid, None otherwise
    """
    user = db.query(User).filter(User.reset_token == token).first()
    
    if not user:
        return None
    
    # Check if token expired
    if user.reset_token_expires_at < datetime.utcnow():
        return None
    
    return user


def reset_user_password(db: Session, user: User, new_password: str) -> None:
    """
    Reset user password
    
    Args:
        db: Database session
        user: User object
        new_password: New plain text password
    """
    user.password_hash = get_password_hash(new_password) # type: ignore
    user.reset_token = None
    user.reset_token_expires_at = None
    db.commit()