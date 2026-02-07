"""
Payment Pydantic Schemas
Location: app/schemas/payment.py
"""
from pydantic import BaseModel, Field, field_validator # type: ignore
from typing import Optional
from decimal import Decimal
from datetime import datetime, date
import uuid


# ============================================================================
# Payment Schemas
# ============================================================================

class PaymentBase(BaseModel):
    """Base payment schema"""
    amount: Decimal = Field(..., gt=0, description="Payment amount must be greater than 0")
    payment_date: date = Field(default_factory=date.today)
    payment_method: str = Field(..., description="Payment method")
    
    reference_number: Optional[str] = Field(None, max_length=100, description="Reference number")
    transaction_id: Optional[str] = Field(None, max_length=100, description="Transaction ID")
    
    bank_name: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=20)
    
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    """Schema for creating payment"""
    invoice_id: uuid.UUID
    
    @field_validator('payment_date')
    @classmethod
    def validate_payment_date(cls, v):
        """Validate payment date is not in future"""
        if v > date.today():
            raise ValueError('Payment date cannot be in the future')
        return v


class PaymentUpdate(BaseModel):
    """Schema for updating payment"""
    amount: Optional[Decimal] = Field(None, gt=0)
    payment_date: Optional[date] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    transaction_id: Optional[str] = Field(None, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaymentResponse(PaymentBase):
    """Schema for payment response"""
    id: uuid.UUID
    invoice_id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    
    receipt_number: Optional[str]
    receipt_sent: Optional[datetime]
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Schema for paginated payment list"""
    payments: list[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaymentSummary(BaseModel):
    """Lightweight payment summary"""
    id: uuid.UUID
    amount: Decimal
    payment_date: date
    payment_method: str
    
    class Config:
        from_attributes = True