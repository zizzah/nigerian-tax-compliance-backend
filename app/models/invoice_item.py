"""
InvoiceItem Model - FIXED VERSION with UUID columns
Location: app/models/invoice_item.py
"""
from sqlalchemy import Column, String, Numeric, Integer, DateTime, ForeignKey # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.core.base import Base


class InvoiceItem(Base):
    """Invoice line item model"""
    __tablename__ = "invoice_items"
    
    # Primary Key - FIXED: Use UUID type
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys - FIXED: Use UUID type
    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey('products.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Item Details
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    
    # Discounts and Tax
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0)
    tax_rate = Column(Numeric(5, 2), nullable=False, default=7.5)
    tax_amount = Column(Numeric(15, 2), nullable=False, default=0)
    
    # Calculated Total
    line_total = Column(Numeric(15, 2), nullable=False, default=0)
    
    # Ordering
    sort_order = Column(Integer, nullable=False, default=0)
    
    # Timestamps - FIXED: Use timezone-aware datetime
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", foreign_keys=[product_id])
    
    # Methods
    def calculate_totals(self):
        """Calculate line item totals"""
        base_amount = self.quantity * self.unit_price
        
        if self.discount_percent > 0: # type: ignore
            self.discount_amount = base_amount * (self.discount_percent / Decimal('100'))
        else:
            self.discount_amount = Decimal('0')
        
        amount_after_discount = base_amount - self.discount_amount
        self.tax_amount = amount_after_discount * (self.tax_rate / Decimal('100'))
        self.line_total = amount_after_discount + self.tax_amount
    
    def __repr__(self):
        return f"<InvoiceItem {self.description[:30]} - ₦{float(self.line_total):,.2f}>" # type: ignore
