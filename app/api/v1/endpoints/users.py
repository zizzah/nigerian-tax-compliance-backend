"""
User Management Endpoints
Location: app/api/v1/endpoints/users.py
"""
from fastapi import APIRouter, Depends, HTTPException, status # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_verified_user # type: ignore
from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    PasswordChange,
    MessageResponse
)
import logging
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# ============================================================================
# User Profile Endpoints
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's profile
    
    Requires: Valid JWT token
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile
    
    Requires: Valid JWT token
    """
    # Update allowed fields
    
    try :
        update_data = user_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(current_user, field, value)
    
        await db.commit()
        await db.refresh(current_user)
        return current_user

        
    except HTTPException:
        raise
    
    except Exception as e:
        await db.rollback()
        logger.error("Error updating user profile: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating profile"
            
        )  


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change current user's password
    
    Requires: Valid JWT token and current password
    """
    # Verify current password
    try :
        if not verify_password(password_data.current_password, current_user.password_hash): # type: ignore
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"  
            )
        current_user.password_hash = get_password_hash(password_data.new_password) # type: ignore
        await db.commit()
    
        return {
        "message": "Password changed successfully",
        "success": True
        }
    

            
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error updating user profile: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating profile"
            
        )  



@router.delete("/me", response_model=MessageResponse)
async def delete_current_user_account(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete current user's account (soft delete - deactivate)
    
    Requires: Valid JWT token and verified email
    """
    
    try:
        current_user.is_active = False # type: ignore
        await db.commit()
        return {
        "message": "Account deactivated successfully",
        "success": True
        }
    
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error deleting user profile: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deactivating account"
            
        )  

    
    


# ============================================================================
# Example Protected Routes
# ============================================================================

@router.get("/dashboard")
async def user_dashboard(
    current_user: User = Depends(get_current_verified_user)
):
    """
    Example protected route - User dashboard
    
    Requires: Valid JWT token and verified email
    """
    return {
        "message": f"Welcome to your dashboard, {current_user.email}",
        "user_id": str(current_user.id),
        "is_verified": current_user.is_verified,
        "account_age_days": (datetime.now(timezone.utc) - current_user.created_at).days
    }