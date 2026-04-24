"""
Invoice Model - FIXED VERSION with UUID columns
Location: app/models/invoice.py
"""
from sqlalchemy import Column, String, Date, DateTime, Numeric, Boolean, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date, timezone
from decimal import Decimal
import uuid
import enum

from app.core.base import Base


class InvoiceStatus(enum.Enum):
    """Invoice status enumeration"""
    DRAFT = "DRAFT"
    SENT = "SENT"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class Invoice(Base):
    """Invoice model"""
    __tablename__ = "invoices"
    
    # Primary Key - FIXED: Use UUID type
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys - FIXED: Use UUID type
    business_id = Column(UUID(as_uuid=True), ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    # Invoice Details
    invoice_number = Column(String(50), nullable=False, unique=True, index=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT, index=True)
    
    # Financial Details
    subtotal = Column(Numeric(15, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(15, 2), nullable=False, default=0)
    total_amount = Column(Numeric(15, 2), nullable=False, default=0)
    paid_amount = Column(Numeric(15, 2), nullable=False, default=0)
    outstanding_amount = Column(Numeric(15, 2), nullable=False, default=0)
    
    # Additional Info
    payment_terms = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    
    # Email Tracking
    email_sent = Column(Boolean, nullable=False, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_opened_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps - FIXED: Use timezone-aware datetime
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    customer = relationship("Customer", foreign_keys=[customer_id], lazy="selectin")
    business = relationship("Business", foreign_keys=[business_id], lazy="selectin")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    payment_link = relationship("PaymentLink", back_populates="invoice", uselist=False)
    
    # Properties
    @property
    def is_overdue(self) -> bool:
        """Check if invoice is overdue"""
        if self.status in [InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]:
            return self.due_date < date.today() # type: ignore
        return False
    
    @property
    def days_until_due(self) -> int:
        """Days until invoice is due (negative if overdue)"""
        return (self.due_date - date.today()).days
    
    # Methods
    def calculate_totals(self):
        """Calculate invoice totals from line items"""
        if not hasattr(self, 'items') or self.items is None:
            return
        
        self.subtotal = sum(
            (item.quantity * item.unit_price) - item.discount_amount
            for item in self.items
        )
        
        self.tax_amount = sum(item.tax_amount for item in self.items)
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        self.outstanding_amount = self.total_amount - self.paid_amount
        
        if self.outstanding_amount < 0: # type: ignore
            self.outstanding_amount = Decimal('0')
    
    def update_status(self):
        """Update invoice status based on payment"""
        if self.status == InvoiceStatus.CANCELLED: # type: ignore
            return
        
        if self.paid_amount == 0: # type: ignore
            if self.status == InvoiceStatus.DRAFT: # type: ignore
                pass
            elif self.is_overdue:
                self.status = InvoiceStatus.OVERDUE
            else:
                self.status = InvoiceStatus.SENT
        elif self.paid_amount >= self.total_amount: # type: ignore
            self.status = InvoiceStatus.PAID
            if not self.paid_at: # type: ignore
                self.paid_at = datetime.now(timezone.utc)
        else:
            self.status = InvoiceStatus.PARTIALLY_PAID
    
    def mark_as_sent(self):
        """Mark invoice as sent"""
        self.status = InvoiceStatus.SENT
        self.sent_at = datetime.now(timezone.utc)
    
    def mark_as_paid(self):
        """Mark invoice as fully paid"""
        self.status = InvoiceStatus.PAID
        self.paid_at = datetime.now(timezone.utc)
        self.paid_amount = self.total_amount
        self.outstanding_amount = Decimal('0')
    
    def mark_as_cancelled(self):
        """Cancel invoice"""
        self.status = InvoiceStatus.CANCELLED
        self.cancelled_at = datetime.now(timezone.utc)
    
    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.status.value}>"
