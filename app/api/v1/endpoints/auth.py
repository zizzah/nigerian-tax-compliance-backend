"""
Authentication API Endpoints
Location: app/api/v1/endpoints/auth.py

PRODUCTION VERSION - Fixed validation errors and improved security
WITH SECURITY FIXES: Rate limiting on authentication endpoints

PRODUCTION OPTIMIZED: Enhanced rate limiting and monitoring
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request # type: ignore
from sqlalchemy.orm import Session # type: ignore
from datetime import datetime, timedelta, timezone
import secrets
import time
import logging

from app.core.database import get_db
from app.core.rate_limit import limiter
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
logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_by_email(db: Session, email: str) -> User:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def check_account_locked(user: User):
    """
    Check if user account is locked
    
    Args:
        user: User object
        
    Raises:
        HTTPException: If account is locked
    """
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until:
        remaining_minutes = (user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_locked",
                "message": "Account is temporarily locked.",
                "locked_until": user.locked_until.isoformat(),
                "retry_after_minutes": int(remaining_minutes) + 1
            }
        )


def increment_failed_login(db: Session, user: User):
    """
    Increment failed login attempts and lock if needed
    
    Args:
        db: Database session
        user: User object
        
    Raises:
        HTTPException: If account is locked after incrementing
    """
    user.failed_login_attempts += 1
    
    # Lock account after 5 failed attempts for 30 minutes
    if user.failed_login_attempts >= 5:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.commit()
        
        # Log security event
        logger.warning(
            f"Account locked due to failed login attempts: {user.email}",
            extra={
                "user_id": str(user.id),
                "email": user.email,
                "event": "account_locked",
                "reason": "too_many_failed_attempts"
            }
        )
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_locked",
                "message": "Account locked due to too many failed login attempts.",
                "locked_until": user.locked_until.isoformat(),
                "retry_after_minutes": 30
            }
        )
    
    db.commit()
    
    # Log failed attempt
    logger.warning(
        f"Failed login attempt {user.failed_login_attempts}/5: {user.email}",
        extra={
            "user_id": str(user.id),
            "email": user.email,
            "event": "login_failed",
            "attempts": user.failed_login_attempts
        }
    )


def reset_failed_login(db: Session, user: User):
    """Reset failed login attempts on successful login"""
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    db.commit()


# ============================================================================
# Authentication Endpoints - PRODUCTION OPTIMIZED
# ============================================================================

# PRODUCTION OPTIMIZED: Conservative rate limiting to prevent abuse
@limiter.limit("5/minute")  # SECURITY: Max 5 registration attempts per minute per IP
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,  # REQUIRED: For rate limiting
    user_data: UserRegister, 
    db: Session = Depends(get_db)
):
    """
    Register a new user
    
    **Required:**
    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    
    **Optional:**
    - **phone**: Phone number
    
    **Rate Limiting:** 5 requests per minute per IP
    
    **Security Features:**
    - Password hashing with bcrypt
    - Email verification token generation
    - Duplicate email prevention
    """
    try:
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
        
        logger.info(f"New user registered: {new_user.email}")
        
        return new_user
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user account"
        )


@limiter.limit("10/minute")  # PRODUCTION OPTIMIZED: 10 login attempts per minute per IP
@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,  # REQUIRED: For rate limiting
    credentials: UserLogin, 
    db: Session = Depends(get_db)
):
    """
    Login with email and password - PRODUCTION OPTIMIZED
    
    Returns JWT access token on successful authentication
    
    **Args:**
    - **email**: User email address
    - **password**: User password
    
    **Returns:**
    - **access_token**: JWT access token
    - **token_type**: "bearer"
    - **user**: User object with profile information
    
    **Rate Limiting:** 10 requests per minute per IP
    
    **Security Features:**
    - Account lockout after 5 failed attempts (30 min)
    - No user enumeration (same error for invalid email/password)
    - Password timing attack prevention
    - Failed login attempt tracking
    - Comprehensive audit logging
    
    **Status Codes:**
    - 200: Success - returns token
    - 401: Incorrect email or password
    - 403: Account locked or deactivated
    - 422: Validation error (missing/invalid fields)
    - 429: Too many requests (rate limited)
    - 500: Internal server error
    """
    try:
        # Normalize email
        email = credentials.email.strip().lower()
        password = credentials.password
        
        # Get user
        user = get_user_by_email(db, email)
        
        # SECURITY: Don't reveal whether email exists
        if not user:
            # Add small delay to prevent timing attacks
            time.sleep(0.1)
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Check if account is locked
        check_account_locked(user)
        
        # Check if account is deactivated
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Please contact support."
            )
        
        # Verify password
        if not verify_password(password, user.password_hash):
            # Increment failed attempts
            increment_failed_login(db, user)
            
            # Add delay to prevent brute force
            time.sleep(0.1)
            
            # Return generic error (don't reveal which field is wrong)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # SUCCESS - Reset counters & create token
        reset_failed_login(db, user)
        
        # Create access token with claims
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "type": "access"
            }
        )
        
        # Log successful login (for security audit)
        logger.info(
            f"Successful login: {user.email}",
            extra={
                "user_id": str(user.id),
                "email": user.email,
                "event": "login_success"
            }
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login. Please try again."
        )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verify email address with token sent via email
    
    **Args:**
    - **token**: Verification token from email
    
    **Returns:**
    - Success message
    """
    user = db.query(User).filter(User.verification_token == token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Mark as verified
    user.is_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    user.verification_token = None
    db.commit()
    
    logger.info(f"Email verified: {user.email}")
    
    return {
        "message": "Email verified successfully",
        "success": True
    }


@limiter.limit("3/hour")  # SECURITY: Prevent password reset spam
@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request,  # REQUIRED: For rate limiting
    reset_request: PasswordResetRequest, 
    db: Session = Depends(get_db)
):
    """
    Request password reset - sends reset token to email
    
    **Rate Limiting:** 3 requests per hour per IP
    
    **Security:** Always returns success (doesn't reveal if email exists)
    """
    user = get_user_by_email(db, reset_request.email)
    
    if not user:
        # Don't reveal if email exists - security best practice
        return {
            "message": "If the email exists, a password reset link has been sent",
            "success": True
        }
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token
    user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()
    
    # TODO: Send password reset email
    # send_password_reset_email(user.email, reset_token)
    
    logger.info(f"Password reset requested: {user.email}")
    
    return {
        "message": "If the email exists, a password reset link has been sent",
        "success": True
    }


@limiter.limit("5/hour")  # SECURITY: Limit password reset attempts
@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,  # REQUIRED: For rate limiting
    reset_data: PasswordReset, 
    db: Session = Depends(get_db)
):
    """
    Reset password using token from email
    
    **Rate Limiting:** 5 requests per hour per IP
    """
    user = db.query(User).filter(User.reset_token == reset_data.token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token expired
    if user.reset_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    # Update password
    user.password_hash = get_password_hash(reset_data.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    
    logger.info(f"Password reset completed: {user.email}")
    
    return {
        "message": "Password reset successfully",
        "success": True
    }


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout user
    
    **Note:** Since we're using JWT, actual logout happens on client side
    by removing the token. This endpoint is provided for consistency.
    """
    return {
        "message": "Logged out successfully",
        "success": True
    }


@router.get("/login-status")
async def check_login_status(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Check if email is locked (useful for frontend)
    
    **Args:**
    - **email**: Email to check
    
    **Returns:**
    - Status information (without revealing if email exists)
    """
    user = get_user_by_email(db, email)
    
    # Don't reveal if email exists
    if not user:
        return {
            "can_login": True,
            "message": "Ready to login"
        }
    
    # Check if locked
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until:
        remaining_minutes = (user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60
        
        return {
            "can_login": False,
            "locked": True,
            "retry_after_minutes": int(remaining_minutes) + 1,
            "message": f"Account locked. Try again in {int(remaining_minutes) + 1} minutes."
        }
    
    return {
        "can_login": True,
        "message": "Ready to login"
    }


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def auth_health():
    """Health check for auth endpoints"""
    return {
        "status": "healthy", 
        "service": "authentication",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }