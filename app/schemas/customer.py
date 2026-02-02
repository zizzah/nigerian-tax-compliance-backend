"""
Customer Pydantic Schemas
Location: app/schemas/customer.py
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from decimal import Decimal
from datetime import datetime, date
import uuid


# ============================================================================
# Request Schemas (Input)
# ============================================================================

class CustomerCreate(BaseModel):
    """Schema for creating a customer"""
    name: str = Field(..., min_length=2, max_length=255, description="Customer name")
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    
    # Address
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    
    # Tax Info
    tin: Optional[str] = Field(None, max_length=20, description="Customer's TIN")
    
    # Settings
    customer_type: str = Field("Individual", description="Individual or Business")
    credit_limit: Optional[Decimal] = Field(None, ge=0, description="Credit limit")
    payment_terms_days: int = Field(30, ge=0, le=365, description="Payment terms in days")
    
    # Notes
    notes: Optional[str] = None
    
    @validator('customer_type')
    def validate_customer_type(cls, v):
        """Validate customer type"""
        allowed_types = ['Individual', 'Business']
        if v not in allowed_types:
            raise ValueError(f'Customer type must be one of: {", ".join(allowed_types)}')
        return v


class CustomerUpdate(BaseModel):
    """Schema for updating a customer"""
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    
    # Address
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    
    # Tax Info
    tin: Optional[str] = Field(None, max_length=20)
    
    # Settings
    customer_type: Optional[str] = None
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    is_active: Optional[bool] = None
    
    # Notes
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# Response Schemas (Output)
# ============================================================================

class CustomerResponse(BaseModel):
    """Schema for customer response"""
    id: uuid.UUID
    business_id: uuid.UUID
    
    # Basic Info
    name: str
    email: Optional[str]
    phone: Optional[str]
    
    # Address
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: str
    
    # Tax Info
    tin: Optional[str]
    
    # Analytics
    total_invoices_count: int
    total_invoiced_amount: Decimal
    total_paid_amount: Decimal
    average_payment_days: Optional[int]
    last_invoice_date: Optional[date]
    
    # Settings
    customer_type: str
    credit_limit: Optional[Decimal]
    payment_terms_days: int
    is_active: bool
    
    # Notes
    notes: Optional[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Schema for paginated customer list"""
    customers: list[CustomerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CustomerSummary(BaseModel):
    """Lightweight customer summary"""
    id: uuid.UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    total_invoices_count: int
    outstanding_amount: Decimal
    is_active: bool
    
    class Config:
        from_attributes = True