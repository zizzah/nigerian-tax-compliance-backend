"""
Authentication Schemas
Pydantic models for request/response validation
"""

from pydantic import BaseModel, EmailStr, Field, validator,field_validator
from typing import Optional
from datetime import datetime
import re


# ============================================================================
# USER SCHEMAS
# ============================================================================

class UserBase(BaseModel):
    """Base user schema with common fields"""
    email: EmailStr
    phone: Optional[str] = None


class UserRegister(UserBase):
    """Schema for user registration"""
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        return v
    
    @field_validator('confirm_password')
    def passwords_match(cls, v, values):
        """Ensure passwords match"""
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('phone')
    def validate_phone(cls, v):
        """Validate Nigerian phone number format"""
        if v is None:
            return v
        
        # Remove spaces and special characters
        phone = re.sub(r'[^\d+]', '', v)
        
        # Nigerian phone numbers: +234, 0, or direct 10 digits
        if not re.match(r'^(\+234|0)?[789]\d{9}$', phone):
            raise ValueError('Invalid Nigerian phone number format. Use: +2348012345678 or 08012345678')
        
        return phone


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(UserBase):
    """Schema for user response (without sensitive data)"""
    id: str
    is_active: bool
    is_verified: bool
    email_verified_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    phone: Optional[str] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        """Validate Nigerian phone number format"""
        if v is None:
            return v
        
        phone = re.sub(r'[^\d+]', '', v)
        
        if not re.match(r'^(\+234|0)?[789]\d{9}$', phone):
            raise ValueError('Invalid Nigerian phone number format')
        
        return phone


class PasswordChange(BaseModel):
    """Schema for password change"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        return v
    
    @validator('confirm_new_password')
    def passwords_match(cls, v, values):
        """Ensure passwords match"""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class PasswordResetRequest(BaseModel):
    """Schema for requesting password reset"""
    email: EmailStr


class PasswordReset(BaseModel):
    """Schema for resetting password with token"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        return v
    
    @validator('confirm_new_password')
    def passwords_match(cls, v, values):
        """Ensure passwords match"""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class EmailVerification(BaseModel):
    """Schema for email verification"""
    token: str


# ============================================================================
# TOKEN SCHEMAS
# ============================================================================

class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema for JWT token payload"""
    sub: str  # User ID
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    type: str  # Token type: access or refresh


class RefreshToken(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class AuthResponse(BaseModel):
    """Complete authentication response"""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    detail: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: str
    data: Optional[dict] = None