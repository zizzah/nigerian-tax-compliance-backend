"""
Business Pydantic Schemas
Location: app/schemas/business.py
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
import uuid
from datetime import datetime


# ============================================================================
# Request Schemas (Input)
# ============================================================================

class BusinessCreate(BaseModel):
    """Schema for creating a business profile"""
    model_config = ConfigDict(extra="ignore")

    business_name: str = Field(..., min_length=2, max_length=255, description="Business name")
    business_type: Optional[str] = Field(None, max_length=100, description="e.g., Limited Liability Company")
    industry: Optional[str] = Field(None, max_length=100, description="e.g., Technology, Retail")
    
    # Tax Info
    tin: Optional[str] = Field(None, max_length=20, description="Tax Identification Number")
    vat_registered: bool = Field(False, description="Is business VAT registered?")
    vat_number: Optional[str] = Field(None, max_length=20)
    rc_number: Optional[str] = Field(None, max_length=20, description="Registration/Company Number")
    
    # Contact
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field("Nigeria", max_length=50)
    website: Optional[str] = Field(None, max_length=255)

    @field_validator(
        'business_name',
        'business_type',
        'industry',
        'tin',
        'vat_number',
        'rc_number',
        'phone',
        'address',
        'city',
        'state',
        'country',
        'website',
        mode='before',
    )
    @classmethod
    def normalize_strings(cls, v):
        """Trim strings and convert blank optional values to None."""
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip()
            return value or None
        return v

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip().lower()
            return value or None
        return v
    

class BusinessUpdate(BaseModel):
    """Schema for updating business profile"""
    model_config = ConfigDict(extra="ignore")

    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    business_type: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    
    # Tax Info
    tin: Optional[str] = Field(None, max_length=20)
    vat_registered: Optional[bool] = None
    vat_number: Optional[str] = Field(None, max_length=20)
    rc_number: Optional[str] = Field(None, max_length=20)
    
    # Contact
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    
    # Branding
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    secondary_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    
    # Invoice Settings
    invoice_prefix: Optional[str] = Field(None, min_length=1, max_length=10)

    @field_validator(
        'business_name',
        'business_type',
        'industry',
        'tin',
        'vat_number',
        'rc_number',
        'phone',
        'website',
        'address',
        'city',
        'state',
        'logo_url',
        'primary_color',
        'secondary_color',
        'invoice_prefix',
        mode='before',
    )
    @classmethod
    def normalize_optional_strings(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip()
            return value or None
        return v

    @field_validator('email', mode='before')
    @classmethod
    def normalize_update_email(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip().lower()
            return value or None
        return v
    
    class Config:
        from_attributes = True


# ============================================================================
# Response Schemas (Output)
# ============================================================================

class BusinessResponse(BaseModel):
    """Schema for business response"""
    id: uuid.UUID
    user_id: uuid.UUID
    
    # Business Info
    business_name: str
    business_type: Optional[str]
    industry: Optional[str]
    
    # Tax Info
    tin: Optional[str]
    vat_registered: bool
    vat_number: Optional[str]
    rc_number: Optional[str]
    
    # Contact
    phone: Optional[str]
    email: Optional[str]
    website: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: str
    
    # Branding
    logo_url: Optional[str]
    primary_color: str
    secondary_color: str
    
    # Invoice Settings
    invoice_prefix: str
    invoice_counter: int
    
    # Subscription
    subscription_tier: str
    monthly_invoice_quota: int
    monthly_document_quota: int
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BusinessSummary(BaseModel):
    """Lightweight business summary"""
    id: uuid.UUID
    business_name: str
    industry: Optional[str]
    subscription_tier: str
    
    class Config:
        from_attributes = True
