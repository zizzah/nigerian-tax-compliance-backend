"""
User Pydantic Schemas for Request/Response Validation
Location: app/schemas/user.py

PRODUCTION VERSION - Fixed validation errors per deployment guide
"""
from pydantic import BaseModel, EmailStr, Field, field_validator # type: ignore
from datetime import datetime
from typing import Optional
import uuid


# ============================================================================
# Base Schemas
# ============================================================================

class UserBase(BaseModel):
    """Base user schema with common fields"""
    email: EmailStr
    phone: Optional[str] = None


# ============================================================================
# Request Schemas (Input)
# ============================================================================

class UserRegister(UserBase):
    """Schema for user registration"""
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('password')
    @classmethod
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserLogin(BaseModel):
    """
    Schema for user login with explicit validation
    
    FIXED: Per deployment guide to prevent timeouts and return proper 422 errors
    
    This ensures:
    - Missing email returns 422 with clear error message
    - Missing password returns 422 with clear error message
    - Empty fields are caught and validated
    - Email is normalized (stripped and lowercased)
    """
    email: EmailStr = Field(
        ..., 
        description="User email address",
        examples=["user@example.com"]
    )
    password: str = Field(
        ..., 
        min_length=1, 
        description="User password"
    )
    
    @field_validator('email')
    @classmethod
    def validate_email_not_empty(cls, v):
        """
        Ensure email is not empty or whitespace
        
        This prevents validation errors from causing timeouts
        """
        if not v or not v.strip():
            raise ValueError('Email cannot be empty')
        return v.strip().lower()
    
    @field_validator('password')
    @classmethod
    def validate_password_not_empty(cls, v):
        """
        Ensure password is not empty or whitespace
        
        This prevents validation errors from causing timeouts
        """
        if not v or not v.strip():
            raise ValueError('Password cannot be empty')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePassword123!"
            }
        }


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    phone: Optional[str] = None
    
    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    """Schema for changing password"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v):
        """Validate new password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class PasswordResetRequest(BaseModel):
    """Schema for requesting password reset"""
    email: EmailStr
    
    @field_validator('email')
    @classmethod
    def validate_email_not_empty(cls, v):
        """Ensure email is not empty"""
        if not v or not v.strip():
            raise ValueError('Email cannot be empty')
        return v.strip().lower()


class PasswordReset(BaseModel):
    """Schema for resetting password with token"""
    token: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v):
        """Validate new password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


# ============================================================================
# Response Schemas (Output)
# ============================================================================

class UserResponse(UserBase):
    """Schema for user response"""
    id: uuid.UUID
    is_active: bool
    is_verified: bool
    is_superuser: bool
    email_verified_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "phone": "+2348012345678",
                "is_active": True,
                "is_verified": True,
                "is_superuser": False,
                "email_verified_at": "2024-01-15T10:30:00Z",
                "last_login": "2024-02-07T14:20:00Z",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-02-07T14:20:00Z"
            }
        }


class TokenResponse(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "user@example.com",
                    "is_active": True,
                    "is_verified": True
                }
            }
        }


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation completed successfully",
                "success": True
            }
        }


# ============================================================================
# Token Schemas
# ============================================================================

class TokenData(BaseModel):
    """Schema for token payload data"""
    user_id: Optional[str] = None
    email: Optional[str] = None