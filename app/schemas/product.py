"""
Product Pydantic Schemas - FIXED VERSION
Location: app/schemas/product.py

CHANGES:
- Replaced @field_validator with @model_validator for inventory tracking validation
- This fixes the timeout issue in test 1.2 "Create Product with Inventory Tracking"
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from decimal import Decimal
from datetime import datetime
import uuid


# ============================================================================
# Product Schemas
# ============================================================================

class ProductBase(BaseModel):
    """Base product schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100, description="Stock Keeping Unit")
    
    unit_price: Decimal = Field(..., ge=0, description="Unit price")
    cost_price: Optional[Decimal] = Field(None, ge=0, description="Cost price for profit calculation")
    
    tax_rate: Decimal = Field(7.5, ge=0, le=100, description="Tax rate (default 7.5% VAT)") # type: ignore
    is_taxable: bool = Field(True, description="Is product taxable")
    
    category: Optional[str] = Field(None, max_length=100)
    
    # Inventory
    track_inventory: bool = Field(False, description="Track inventory for this product")
    quantity_in_stock: Optional[Decimal] = Field(None, ge=0)
    low_stock_threshold: Optional[Decimal] = Field(None, ge=0)


class ProductCreate(ProductBase):
    """Schema for creating product"""
    
    @model_validator(mode='after')
    def validate_inventory_tracking(self):
        """Validate quantity is provided if tracking inventory"""
        if self.track_inventory and self.quantity_in_stock is None:
            raise ValueError('Quantity in stock is required when inventory tracking is enabled')
        return self


class ProductUpdate(BaseModel):
    """Schema for updating product"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100)
    
    unit_price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    is_taxable: Optional[bool] = None
    
    category: Optional[str] = Field(None, max_length=100)
    
    track_inventory: Optional[bool] = None
    quantity_in_stock: Optional[Decimal] = Field(None, ge=0)
    low_stock_threshold: Optional[Decimal] = Field(None, ge=0)
    
    is_active: Optional[bool] = None
    
    class Config:
        from_attributes = True


class ProductResponse(ProductBase):
    """Schema for product response"""
    id: uuid.UUID
    business_id: uuid.UUID
    
    usage_count: int
    last_used_at: Optional[datetime]
    is_active: bool
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Schema for paginated product list"""
    products: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSummary(BaseModel):
    """Lightweight product summary"""
    id: uuid.UUID
    name: str
    unit_price: Decimal
    is_active: bool
    
    class Config:
        from_attributes = True