"""
Product API Endpoints - IMPROVED VERSION
Location: app/api/v1/endpoints/products.py

IMPROVEMENTS:
1. Better error messages for duplicate SKU
2. Optional SKU auto-generation
3. Clearer validation errors
4. Better handling of edge cases
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_ # type: ignore
from sqlalchemy.exc import IntegrityError # type: ignore
from typing import Optional
import uuid
import math
import secrets
import string

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.product import Product
from app.schemas.product import (
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


def generate_unique_sku(db: Session, business_id: uuid.UUID, base_name: str = None) -> str: # type: ignore
    """
    Generate a unique SKU for a product
    
    Args:
        db: Database session
        business_id: Business ID
        base_name: Optional base name to derive SKU from
    
    Returns:
        Unique SKU string
    """
    max_attempts = 10
    
    for attempt in range(max_attempts):
        if base_name:
            # Create SKU from product name (first 3 chars + random suffix)
            prefix = ''.join(c for c in base_name.upper() if c.isalnum())[:3]
            random_suffix = ''.join(secrets.choice(string.digits) for _ in range(6))
            sku = f"{prefix}-{random_suffix}"
        else:
            # Generate random SKU
            random_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            sku = f"PRD-{random_code}"
        
        # Check if SKU already exists
        existing = db.query(Product).filter(
            Product.business_id == business_id,
            Product.sku == sku
        ).first()
        
        if not existing:
            return sku
    
    # If we couldn't generate a unique SKU after max_attempts, use UUID
    return f"PRD-{str(uuid.uuid4())[:8].upper()}"


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
    - **sku**: Stock Keeping Unit code (auto-generated if not provided)
    - **cost_price**: Cost price (for profit calculation)
    - **tax_rate**: Tax rate (default: 7.5% VAT)
    - **is_taxable**: Whether product is taxable (default: true)
    - **category**: Product category
    - **track_inventory**: Enable inventory tracking
    - **quantity_in_stock**: Current stock quantity (required if tracking)
    - **low_stock_threshold**: Alert threshold for low stock
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Auto-generate SKU if not provided
    if not product_data.sku:
        product_data.sku = generate_unique_sku(db, business.id, product_data.name) # type: ignore
    
    # Check for duplicate SKU (with better error message)
    if product_data.sku:
        existing = db.query(Product).filter(
            Product.business_id == business.id,
            Product.sku == product_data.sku
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,  # Changed from 400 to 409
                detail={
                    "error": "duplicate_sku",
                    "message": f"A product with SKU '{product_data.sku}' already exists",
                    "existing_product": {
                        "id": str(existing.id),
                        "name": existing.name,
                        "sku": existing.sku
                    },
                    "suggestion": "Please use a different SKU or leave it blank to auto-generate"
                }
            )
    
    # Validate inventory tracking requirements
    if product_data.track_inventory and product_data.quantity_in_stock is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "validation_error",
                "message": "Quantity in stock is required when inventory tracking is enabled",
                "field": "quantity_in_stock"
            }
        )
    
    try:
        # Create product
        product = Product(
            **product_data.model_dump(),
            business_id=business.id
        )
        
        db.add(product)
        db.commit()
        db.refresh(product)
        
        return product
    
    except IntegrityError as e:
        db.rollback()
        # Handle any database constraint violations
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "database_constraint_violation",
                    "message": "A product with these details already exists",
                    "suggestion": "Please check SKU or other unique fields"
                }
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the product"
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


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


@router.get("/check-sku/{sku}")
async def check_sku_availability(
    sku: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if a SKU is available for use
    
    Useful for validation before creating/updating products
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    existing = db.query(Product).filter(
        Product.business_id == business.id,
        Product.sku == sku
    ).first()
    
    if existing:
        return {
            "available": False,
            "sku": sku,
            "existing_product": {
                "id": str(existing.id),
                "name": existing.name,
                "is_active": existing.is_active
            }
        }
    
    return {
        "available": True,
        "sku": sku
    }


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
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "duplicate_sku",
                    "message": f"Another product already uses SKU '{product_data.sku}'",
                    "existing_product": {
                        "id": str(existing.id),
                        "name": existing.name
                    }
                }
            )
    
    # Validate inventory tracking if being enabled
    if product_data.track_inventory and product_data.quantity_in_stock is None:
        if not product.quantity_in_stock: # type: ignore
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "validation_error",
                    "message": "Quantity in stock must be set when enabling inventory tracking",
                    "field": "quantity_in_stock"
                }
            )
    
    try:
        # Update fields
        update_data = product_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(product, field, value)
        
        db.commit()
        db.refresh(product)
        
        return product
    
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conflict occurred while updating the product"
        )


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
            detail={
                "error": "product_in_use",
                "message": f"Cannot delete product that has been used in {product.usage_count} invoice(s)",
                "suggestion": "Use soft delete instead to preserve historical data"
            }
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