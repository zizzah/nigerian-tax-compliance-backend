"""
Product API Endpoints
Location: app/api/v1/endpoints/products.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
import uuid
import math

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.product import Product
from app.schemas.product import ( # type: ignore
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    ProductSummary
)

router = APIRouter(prefix="/products", tags=["Products"])


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses"
        )
    return business


# ============================================================================
# Product CRUD Endpoints
# ============================================================================

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new product/service
    
    **Required:**
    - **name**: Product name
    - **unit_price**: Selling price per unit
    
    **Optional:**
    - **description**: Product description
    - **sku**: Stock Keeping Unit code
    - **cost_price**: Cost price (for profit calculation)
    - **tax_rate**: Tax rate (default: 7.5% VAT)
    - **is_taxable**: Whether product is taxable (default: true)
    - **category**: Product category
    - **track_inventory**: Enable inventory tracking
    - **quantity_in_stock**: Current stock quantity (required if tracking)
    - **low_stock_threshold**: Alert threshold for low stock
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Check for duplicate SKU
    if product_data.sku:
        existing = db.query(Product).filter(
            Product.business_id == business.id,
            Product.sku == product_data.sku
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product_data.sku}' already exists"
            )
    
    # Create product
    product = Product(
        **product_data.model_dump(),
        business_id=business.id
    )
    
    db.add(product)
    db.commit()
    db.refresh(product)
    
    return product


@router.get("/", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, SKU, or description"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    low_stock_only: bool = Query(False, description="Show only low stock items"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of products
    
    **Query Parameters:**
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (max: 100, default: 50)
    - **search**: Search in name, SKU, or description
    - **category**: Filter by category
    - **is_active**: Filter by active status
    - **low_stock_only**: Show only products with low stock
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Base query
    query = db.query(Product).filter(Product.business_id == business.id)
    
    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_term),
                Product.sku.ilike(search_term),
                Product.description.ilike(search_term)
            )
        )
    
    if category:
        query = query.filter(Product.category == category)
    
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    
    if low_stock_only:
        query = query.filter(
            Product.track_inventory == True,
            Product.quantity_in_stock <= Product.low_stock_threshold
        )
    
    # Get total count
    total = query.count()
    
    # Calculate pagination
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
    # Get paginated results
    products = query.order_by(Product.name)\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    return {
        "products": products,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/summary", response_model=list[ProductSummary])
async def list_products_summary(
    limit: int = Query(10, ge=1, le=100, description="Max items to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get lightweight summary of products (for invoice creation dropdowns)
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    products = db.query(Product)\
        .filter(Product.business_id == business.id)\
        .filter(Product.is_active == True)\
        .order_by(Product.usage_count.desc())\
        .limit(limit)\
        .all()
    
    return products


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific product by ID
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == business.id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a product
    
    All fields are optional - only provided fields will be updated.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == business.id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check for SKU conflict if updating SKU
    if product_data.sku and product_data.sku != product.sku:
        existing = db.query(Product).filter(
            Product.business_id == business.id,
            Product.sku == product_data.sku,
            Product.id != product_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product_data.sku}' already exists"
            )
    
    # Update fields
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    db.commit()
    db.refresh(product)
    
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a product (soft delete - marks as inactive)
    
    The product is not permanently removed, just marked as inactive.
    Use DELETE /products/{id}/permanent for permanent deletion.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == business.id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Soft delete
    product.is_active = False # type: ignore
    db.commit()
    
    return None


@router.delete("/{product_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a product
    
    **Warning:** This will remove the product completely.
    Consider soft delete instead to preserve historical invoice data.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == business.id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if product is used in any invoices
    if product.usage_count > 0: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete product that has been used in {product.usage_count} invoice(s). "
                   "Use soft delete instead."
        )
    
    db.delete(product)
    db.commit()
    
    return None


# ============================================================================
# Product Categories
# ============================================================================

@router.get("/categories/list")
async def list_product_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of all product categories used by the business
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    categories = db.query(Product.category)\
        .filter(Product.business_id == business.id)\
        .filter(Product.category.isnot(None))\
        .distinct()\
        .all()
    
    return {
        "categories": [cat[0] for cat in categories if cat[0]]
    }