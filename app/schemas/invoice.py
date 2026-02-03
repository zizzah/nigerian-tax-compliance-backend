"""
Invoice Pydantic Schemas
Location: app/schemas/invoice.py
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime, date, timedelta
import uuid


# ============================================================================
# Invoice Item Schemas
# ============================================================================

class InvoiceItemBase(BaseModel):
    """Base invoice item schema"""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(..., gt=0, description="Quantity must be greater than 0")
    unit_price: Decimal = Field(..., ge=0, description="Unit price")
    discount_percent: Decimal = Field(0, ge=0, le=100, description="Discount percentage (0-100)") # type: ignore
    tax_rate: Decimal = Field(7.5, ge=0, le=100, description="Tax rate percentage (default 7.5% VAT)") # type: ignore
    product_id: Optional[uuid.UUID] = None


class InvoiceItemCreate(InvoiceItemBase):
    """Schema for creating invoice item"""
    sort_order: int = Field(0, ge=0, description="Sort order for items")


class InvoiceItemUpdate(BaseModel):
    """Schema for updating invoice item"""
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    sort_order: Optional[int] = Field(None, ge=0)


class InvoiceItemResponse(InvoiceItemBase):
    """Schema for invoice item response"""
    id: uuid.UUID
    invoice_id: uuid.UUID
    product_id: Optional[uuid.UUID] # type: ignore
    
    # Calculated fields
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    sort_order: int
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# Invoice Schemas
# ============================================================================

class InvoiceBase(BaseModel):
    """Base invoice schema"""
    customer_id: uuid.UUID
    issue_date: date = Field(default_factory=date.today)
    payment_terms: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=5000)
    internal_notes: Optional[str] = Field(None, max_length=5000)


class InvoiceCreate(InvoiceBase):
    """Schema for creating invoice"""
    due_date: Optional[date] = None
    discount_amount: Decimal = Field(0, ge=0, description="Overall invoice discount") # type: ignore
    items: List[InvoiceItemCreate] = Field(..., min_length=1, description="Invoice must have at least 1 item")
    
    @field_validator('issue_date')
    @classmethod
    def validate_issue_date(cls, v):
        """Validate issue date is not in future"""
        if v > date.today():
            raise ValueError('Issue date cannot be in the future')
        return v
    
    @model_validator(mode='after')
    def validate_dates(self):
        """Validate due date is after issue date"""
        if self.due_date and self.due_date < self.issue_date:
            raise ValueError('Due date must be on or after issue date')
        
        # Set default due date to 30 days from issue date if not provided
        if not self.due_date:
            self.due_date = self.issue_date + timedelta(days=30)
        
        return self


class InvoiceUpdate(BaseModel):
    """Schema for updating invoice"""
    customer_id: Optional[uuid.UUID] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    payment_terms: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=5000)
    internal_notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[InvoiceItemCreate]] = None
    
    class Config:
        from_attributes = True


class InvoiceResponse(InvoiceBase):
    """Schema for invoice response"""
    id: uuid.UUID
    business_id: uuid.UUID
    invoice_number: str
    status: str
    
    # Financial details
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    
    # Email tracking
    email_sent: bool
    email_sent_at: Optional[datetime]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime]
    paid_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    
    # Related data
    items: List[InvoiceItemResponse] = []
    
    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Schema for paginated invoice list"""
    invoices: List[InvoiceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class InvoiceSummary(BaseModel):
    """Lightweight invoice summary"""
    id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    issue_date: date
    due_date: date
    status: str
    total_amount: Decimal
    outstanding_amount: Decimal
    
    class Config:
        from_attributes = True


# ============================================================================
# Invoice Action Schemas
# ============================================================================

class InvoiceSendRequest(BaseModel):
    """Schema for sending invoice via email"""
    email: Optional[str] = Field(None, description="Override customer email")
    cc_emails: List[str] = Field(default_factory=list, description="CC emails")
    subject: Optional[str] = None
    message: Optional[str] = None


class InvoiceCancelRequest(BaseModel):
    """Schema for cancelling invoice"""
    reason: Optional[str] = Field(None, max_length=500, description="Cancellation reason")


# ============================================================================
# Invoice Statistics
# ============================================================================

class InvoiceStatistics(BaseModel):
    """Invoice statistics"""
    total_invoices: int
    draft_invoices: int
    sent_invoices: int
    paid_invoices: int
    overdue_invoices: int
    cancelled_invoices: int
    
    total_invoiced: Decimal
    total_paid: Decimal
    total_outstanding: Decimal
    
    average_invoice_value: Decimal
    average_days_to_payment: Optional[float]


# ============================================================================
# Natural Language Invoice Creation
# ============================================================================

class NaturalLanguageInvoiceRequest(BaseModel):
    """Schema for creating invoice from natural language"""
    text: str = Field(..., min_length=10, max_length=1000, 
                     description="Natural language description of invoice")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Invoice ABC Corp for 5 laptops at ₦200,000 each and 10 mice at ₦5,000 each"
            }
        }