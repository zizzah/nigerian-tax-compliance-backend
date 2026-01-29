"""
Authentication API Endpoints
Complete authentication system with registration, login, password reset, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Any

from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_token,
    authenticate_user,
    check_user_locked,
    record_failed_login,
    reset_failed_logins,
    generate_verification_token,
    verify_user_email,
    create_password_reset_token,
    verify_reset_token,
    reset_user_password,
    get_current_user,
    get_current_active_user,
    get_current_verified_user,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    UserUpdate,
    PasswordChange,
    PasswordResetRequest,
    PasswordReset,
    EmailVerification,
    AuthResponse,
    Token,
    RefreshToken,
    MessageResponse,
    SuccessResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# REGISTRATION
# ============================================================================

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Register a new user
    
    - **email**: Valid email address (must be unique)
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    - **confirm_password**: Must match password
    - **phone**: Optional Nigerian phone number
    
    Returns user details and authentication tokens.
    A verification email will be sent in the background.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    verification_token = generate_verification_token()
    
    new_user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        phone=user_data.phone,
        verification_token=verification_token,
        is_active=True,
        is_verified=False,  # Require email verification
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(new_user.id)})
    refresh_token = create_refresh_token(data={"sub": str(new_user.id)})
    
    # TODO: Send verification email in background
    # background_tasks.add_task(send_verification_email, new_user.email, verification_token)
    
    # Convert to response model
    user_response = UserResponse.from_orm(new_user)
    
    return AuthResponse(
        user=user_response,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


# ============================================================================
# LOGIN
# ============================================================================

@router.post("/login", response_model=AuthResponse)
async def login(
    credentials: UserLogin,
    db: Session = Depends(get_db)
) -> Any:
    """
    Login with email and password
    
    - **email**: Registered email address
    - **password**: User password
    
    Returns user details and authentication tokens.
    """
    # Authenticate user
    user = authenticate_user(db, credentials.email, credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is locked
    if check_user_locked(user):
        minutes_remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked due to multiple failed login attempts. Try again in {minutes_remaining} minutes."
        )
    
    # Check if user is active
    if not user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact support."
        )
    
    # Reset failed login attempts
    reset_failed_logins(db, user)
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    # Convert to response model
    user_response = UserResponse.from_orm(user)
    
    return AuthResponse(
        user=user_response,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


# ============================================================================
# REFRESH TOKEN
# ============================================================================

@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_data: RefreshToken,
    db: Session = Depends(get_db)
) -> Any:
    """
    Get a new access token using refresh token
    
    - **refresh_token**: Valid refresh token
    
    Returns new access and refresh tokens.
    """
    # Verify refresh token
    user_id = verify_token(refresh_data.refresh_token, token_type="refresh")
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.is_active: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Generate new tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )


# ============================================================================
# GET CURRENT USER
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current authenticated user information
    
    Requires: Valid access token in Authorization header
    
    Returns current user details.
    """
    return UserResponse.from_orm(current_user)


# ============================================================================
# UPDATE USER PROFILE
# ============================================================================

@router.patch("/me", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Update current user profile
    
    Requires: Valid access token
    
    - **phone**: Optional phone number
    
    Returns updated user details.
    """
    # Update fields
    if user_update.phone is not None:
        current_user.phone = user_update.phone # type: ignore
    
    current_user.updated_at = datetime.utcnow() # type: ignore
    
    db.commit()
    db.refresh(current_user)
    
    return UserResponse.from_orm(current_user)


# ============================================================================
# CHANGE PASSWORD
# ============================================================================

@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Change user password
    
    Requires: Valid access token
    
    - **current_password**: Current password
    - **new_password**: New password (min 8 chars, uppercase, lowercase, digit)
    - **confirm_new_password**: Must match new password
    
    Returns success message.
    """
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash): # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.password_hash = get_password_hash(password_data.new_password) # type: ignore
    current_user.updated_at = datetime.utcnow() # type: ignore
    
    db.commit()
    
    return MessageResponse(
        message="Password changed successfully",
        detail="Please login with your new password"
    )


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    verification: EmailVerification,
    db: Session = Depends(get_db)
) -> Any:
    """
    Verify user email with token
    
    - **token**: Email verification token (sent via email)
    
    Returns success message.
    """
    # Find user with this verification token
    user = db.query(User).filter(User.verification_token == verification.token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token"
        )
    
    if user.is_verified: # type: ignore
        return MessageResponse(
            message="Email already verified",
            detail="Your email has already been verified"
        )
    
    # Verify email
    verify_user_email(db, user)
    
    return MessageResponse(
        message="Email verified successfully",
        detail="You can now access all features"
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification_email(
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks = None, # type: ignore
    db: Session = Depends(get_db)
) -> Any:
    """
    Resend email verification link
    
    Requires: Valid access token
    
    Returns success message.
    """
    if current_user.is_verified: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Generate new verification token
    verification_token = generate_verification_token()
    current_user.verification_token = verification_token
    current_user.updated_at = datetime.utcnow() # type: ignore
    
    db.commit()
    
    # TODO: Send verification email in background
    # background_tasks.add_task(send_verification_email, current_user.email, verification_token)
    
    return MessageResponse(
        message="Verification email sent",
        detail=f"Please check your email at {current_user.email}"
    )


# ============================================================================
# PASSWORD RESET
# ============================================================================

@router.post("/forgot-password", response_model=MessageResponse)
async def request_password_reset(
    reset_request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Request password reset link
    
    - **email**: Registered email address
    
    Returns success message (even if email doesn't exist for security).
    A password reset email will be sent if the email is registered.
    """
    # Find user
    user = db.query(User).filter(User.email == reset_request.email).first()
    
    if user and user.is_active: # type: ignore
        # Create reset token
        reset_token = create_password_reset_token(db, user)
        
        # TODO: Send reset email in background
        # background_tasks.add_task(send_password_reset_email, user.email, reset_token)
    
    # Always return success for security (don't reveal if email exists)
    return MessageResponse(
        message="Password reset link sent",
        detail=f"If an account exists with {reset_request.email}, you will receive a password reset link"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
) -> Any:
    """
    Reset password with token
    
    - **token**: Password reset token (sent via email)
    - **new_password**: New password (min 8 chars, uppercase, lowercase, digit)
    - **confirm_new_password**: Must match new password
    
    Returns success message.
    """
    # Verify reset token
    user = verify_reset_token(db, reset_data.token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Reset password
    reset_user_password(db, user, reset_data.new_password)
    
    return MessageResponse(
        message="Password reset successful",
        detail="You can now login with your new password"
    )


# ============================================================================
# LOGOUT (Optional - for token blacklisting)
# ============================================================================

@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Logout user
    
    Requires: Valid access token
    
    Note: JWTs are stateless, so this is mainly for client-side cleanup.
    For true logout, implement token blacklisting with Redis.
    
    Returns success message.
    """
    # TODO: Add token to blacklist in Redis if implementing token blacklisting
    
    return MessageResponse(
        message="Logged out successfully",
        detail="Please remove the access token from your client"
    )


# ============================================================================
# ACCOUNT DELETION
# ============================================================================

@router.delete("/me", response_model=MessageResponse)
async def delete_account(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Delete user account
    
    Requires: Valid access token
    
    WARNING: This will permanently delete your account and all associated data.
    
    Returns success message.
    """
    # Soft delete - just deactivate
    current_user.is_active = False # type: ignore
    current_user.updated_at = datetime.utcnow() # type: ignore
    
    db.commit()
    
    # For hard delete:
    # db.delete(current_user)
    # db.commit()
    
    return MessageResponse(
        message="Account deactivated successfully",
        detail="Your account has been deactivated. Contact support to reactivate."
    )