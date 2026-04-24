"""
Product Database Model
Location: app/models/product.py
"""
from sqlalchemy import Column, String, Text, Numeric, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.core.base import Base


class Product(Base):
    """Product/Service model"""
    __tablename__ = "products"
    
    # Primary Key - FIXED: Use UUID type
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key - FIXED: Use UUID type
    business_id = Column(UUID(as_uuid=True), ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Basic Info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sku = Column(String(100), nullable=True)  # Stock Keeping Unit
    
    # Pricing
    unit_price = Column(Numeric(15, 2), nullable=False)  # Selling price
    cost_price = Column(Numeric(15, 2), nullable=True)   # Cost for profit calculation
    
    # Tax
    tax_rate = Column(Numeric(5, 2), nullable=False, default=7.5)  # Default 7.5% VAT
    is_taxable = Column(Boolean, nullable=False, default=True)
    
    # Inventory
    track_inventory = Column(Boolean, nullable=False, default=False)
    quantity_in_stock = Column(Numeric(10, 2), nullable=True)
    low_stock_threshold = Column(Numeric(10, 2), nullable=True)
    
    # Organization
    category = Column(String(100), nullable=True, index=True)
    
    # Usage Tracking
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Timestamps - FIXED: Use timezone-aware datetime
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    business = relationship("Business", foreign_keys=[business_id])
    
    # Properties
    @property
    def is_low_stock(self) -> bool:
        """Check if product is low in stock"""
        if not self.track_inventory: # type: ignore
            return False
        if self.quantity_in_stock is None or self.low_stock_threshold is None:
            return False
        return self.quantity_in_stock <= self.low_stock_threshold # type: ignore
    
    @property
    def profit_margin(self) -> Decimal:
        """Calculate profit margin percentage"""
        if not self.cost_price or self.cost_price == 0: # type: ignore
            return Decimal('0')
        return ((self.unit_price - self.cost_price) / self.cost_price) * Decimal('100') # type: ignore
    
    # Methods
    def increment_usage(self):
        """Increment usage count when used in invoice"""
        self.usage_count += 1
        self.last_used_at = datetime.now(timezone.utc)
    
    def decrease_stock(self, quantity: Decimal):
        """Decrease stock quantity"""
        if self.track_inventory and self.quantity_in_stock is not None: # type: ignore
            self.quantity_in_stock -= quantity
    
    def increase_stock(self, quantity: Decimal):
        """Increase stock quantity"""
        if self.track_inventory: # type: ignore
            if self.quantity_in_stock is None:
                self.quantity_in_stock = quantity
            else:
                self.quantity_in_stock += quantity
    
    def __repr__(self):
        return f"<Product {self.name} - ₦{float(self.unit_price):,.2f}>" # type: ignore
