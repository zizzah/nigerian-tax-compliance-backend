"""
Authentication API Endpoints
Location: app/api/v1/endpoints/auth.py
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets

from app.core.database import get_db
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token
)
from app.models.user import User
from app.schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    MessageResponse,
    PasswordChange,
    PasswordResetRequest,
    PasswordReset
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_by_email(db: Session, email: str) -> User:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def check_account_locked(user: User):
    """Check if user account is locked"""
    if user.locked_until and datetime.utcnow() < user.locked_until: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is locked. Try again after {user.locked_until}"
        )


def increment_failed_login(db: Session, user: User):
    """Increment failed login attempts and lock if needed"""
    user.failed_login_attempts += 1 # type: ignore
    
    # Lock account after 5 failed attempts for 30 minutes
    if user.failed_login_attempts >= 5: # type: ignore
        user.locked_until = datetime.utcnow() + timedelta(minutes=30) # type: ignore
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account locked due to too many failed login attempts. Try again in 30 minutes."
        )
    
    db.commit()


def reset_failed_login(db: Session, user: User):
    """Reset failed login attempts on successful login"""
    user.failed_login_attempts = 0 # type: ignore
    user.locked_until = None # type: ignore
    user.last_login = datetime.utcnow() # type: ignore
    db.commit()


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user
    
    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    - **phone**: Optional phone number
    """
    # Check if user already exists
    existing_user = get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        phone=user_data.phone,
        is_active=True,
        is_verified=False,  # Email verification required
        verification_token=secrets.token_urlsafe(32)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # TODO: Send verification email
    # send_verification_email(new_user.email, new_user.verification_token)
    
    return new_user


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login with email and password
    
    Returns JWT access token on successful authentication
    """
    # Get user
    user = get_user_by_email(db, credentials.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if account is locked
    check_account_locked(user)
    
    # Check if account is active
    if not user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash): # type: ignore
        increment_failed_login(db, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Reset failed login attempts
    reset_failed_login(db, user)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verify email address with token sent via email
    """
    user = db.query(User).filter(User.verification_token == token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token"
        )
    
    if user.is_verified: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Mark as verified
    user.is_verified = True # type: ignore
    user.email_verified_at = datetime.utcnow() # type: ignore
    user.verification_token = None # type: ignore
    db.commit()
    
    return {
        "message": "Email verified successfully",
        "success": True
    }


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Request password reset - sends reset token to email
    """
    user = get_user_by_email(db, request.email)
    
    if not user:
        # Don't reveal if email exists - security best practice
        return {
            "message": "If the email exists, a password reset link has been sent",
            "success": True
        }
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token # type: ignore
    user.reset_token_expires_at = datetime.utcnow() + timedelta(hours=1) # type: ignore
    db.commit()
    
    # TODO: Send password reset email
    # send_password_reset_email(user.email, reset_token)
    
    return {
        "message": "If the email exists, a password reset link has been sent",
        "success": True
    }


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(reset_data: PasswordReset, db: Session = Depends(get_db)):
    """
    Reset password using token from email
    """
    user = db.query(User).filter(User.reset_token == reset_data.token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token expired
    if user.reset_token_expires_at < datetime.utcnow(): # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    # Update password
    user.password_hash = get_password_hash(reset_data.new_password) # type: ignore
    user.reset_token = None # type: ignore
    user.reset_token_expires_at = None # type: ignore
    user.failed_login_attempts = 0 # type: ignore
    user.locked_until = None # type: ignore
    db.commit()
    
    return {
        "message": "Password reset successfully",
        "success": True
    }


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout user
    
    Note: Since we're using JWT, actual logout happens on client side
    by removing the token. This endpoint is provided for consistency.
    """
    return {
        "message": "Logged out successfully",
        "success": True
    }


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def auth_health():
    """Health check for auth endpoints"""
    return {"status": "healthy", "service": "authentication"}