"""
Payment Database Model
Location: app/models/payment.py
"""
from sqlalchemy import Column, String, Date, DateTime, Numeric, Text, Enum, ForeignKey # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from datetime import datetime, date, timezone
from decimal import Decimal
import uuid
import enum

from app.core.database import Base


class PaymentMethod(enum.Enum):
    """Payment method enumeration"""
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    CARD = "CARD"
    MOBILE_MONEY = "MOBILE_MONEY"
    POS = "POS"
    OTHER = "OTHER"


class Payment(Base):
    """Payment model"""
    __tablename__ = "payments"
    
    # Primary Key - FIXED: Use UUID type
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys - FIXED: Use UUID type
    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    # Payment Details
    amount = Column(Numeric(15, 2), nullable=False)
    payment_date = Column(Date, nullable=False, default=date.today)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    
    # Reference Info
    reference_number = Column(String(100), nullable=True)  # Bank reference, etc.
    transaction_id = Column(String(100), nullable=True)    # Transaction ID
    
    # Bank Details (for bank transfers)
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(20), nullable=True)
    
    # Additional Info
    notes = Column(Text, nullable=True)
    
    # Receipt
    receipt_number = Column(String(50), nullable=True)
    receipt_sent = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps - FIXED: Use timezone-aware datetime
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    business = relationship("Business", foreign_keys=[business_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    
    # Methods
    def generate_receipt_number(self, prefix: str = "RCP"):
        """Generate receipt number"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        self.receipt_number = f"{prefix}-{timestamp}"
    
    def __repr__(self):
        return f"<Payment {self.receipt_number} - ₦{float(self.amount):,.2f}>" # type: ignore