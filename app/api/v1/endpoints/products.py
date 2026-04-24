"""
Product API Endpoints
Location: app/api/v1/endpoints/products.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
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
    ProductSummary,
)

import logging
from app.models.invoice_item import InvoiceItem

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/products", tags=["Products"])


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses",
        )
    return business


async def maybe_get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business | None:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    return result.scalar_one_or_none()


async def get_product_by_id(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Product:
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == business_id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product  # type: ignore


async def get_product_by_sku(
    db: AsyncSession,
    business_id: uuid.UUID,
    sku: str,
) -> Product | None:
    result = await db.execute(
        select(Product).where(
            Product.business_id == business_id,
            Product.sku == sku,
        )
    )
    return result.scalar_one_or_none()  # type: ignore


async def generate_unique_sku(
    db: AsyncSession,
    business_id: uuid.UUID,
    base_name: str | None = None,
) -> str:
    for _ in range(10):
        if base_name:
            prefix = "".join(c for c in base_name.upper() if c.isalnum())[:3]
            suffix = "".join(secrets.choice(string.digits) for _ in range(6))
            sku = f"{prefix}-{suffix}"
        else:
            code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            sku = f"PRD-{code}"

        if not await get_product_by_sku(db, business_id, sku):
            return sku

    return f"PRD-{str(uuid.uuid4())[:8].upper()}"


# ============================================================================
# Product CRUD Endpoints
# ============================================================================

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore

    if not product_data.sku:
        product_data.sku = await generate_unique_sku(db, business.id, product_data.name)  # type: ignore

    if product_data.sku:
        existing = await get_product_by_sku(db, business.id, product_data.sku)  # type: ignore
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "duplicate_sku",
                    "message": f"A product with SKU '{product_data.sku}' already exists",
                    "existing_product": {"id": str(existing.id), "name": existing.name},
                    "suggestion": "Use a different SKU or leave blank to auto-generate",
                },
            )

    if product_data.track_inventory and product_data.quantity_in_stock is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quantity in stock is required when inventory tracking is enabled",
        )

    try:
        product = Product(**product_data.model_dump(), business_id=business.id)  # type: ignore
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with these details already exists",
        )
    except Exception as e:
        await db.rollback()
        logger.error("Database error in create_product: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/summary", response_model=list[ProductSummary])
async def list_products_summary(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await maybe_get_user_business(db, current_user.id)  # type: ignore
    if not business:
        return []
    result = await db.execute(
        select(Product)
        .where(Product.business_id == business.id, Product.is_active == True)
        .order_by(Product.usage_count.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/check-sku/{sku}")
async def check_sku_availability(
    sku: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    existing = await get_product_by_sku(db, business.id, sku)  # type: ignore
    if existing:
        return {
            "available": False,
            "sku": sku,
            "existing_product": {"id": str(existing.id), "name": existing.name},
        }
    return {"available": True, "sku": sku}


@router.get("/categories/list")
async def list_product_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await maybe_get_user_business(db, current_user.id)  # type: ignore
    if not business:
        return {"categories": []}
    result = await db.execute(
        select(Product.category)
        .where(Product.business_id == business.id, Product.category.isnot(None))
        .distinct()
    )
    return {"categories": [row[0] for row in result.all() if row[0]]}


@router.get("/", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    low_stock_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await maybe_get_user_business(db, current_user.id)  # type: ignore
    if not business:
        return {
            "products": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
        }

    query = select(Product).where(Product.business_id == business.id)

    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Product.name.ilike(term),
                Product.sku.ilike(term),
                Product.description.ilike(term),
            )
        )
    if category:
        query = query.where(Product.category == category)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)
    if low_stock_only:
        query = query.where(
            Product.track_inventory == True,
            Product.quantity_in_stock <= Product.low_stock_threshold,
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(Product.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    products = result.scalars().all()

    return {
        "products": products,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    return await get_product_by_id(db, product_id, business.id)  # type: ignore


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    product = await get_product_by_id(db, product_id, business.id)  # type: ignore

    if product_data.sku and product_data.sku != product.sku:
        existing = await get_product_by_sku(db, business.id, product_data.sku)  # type: ignore
        if existing and existing.id != product_id: # type: ignore
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another product already uses SKU '{product_data.sku}'",
            )

    if product_data.track_inventory and product_data.quantity_in_stock is None:
        if not product.quantity_in_stock:  # type: ignore
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Quantity in stock must be set when enabling inventory tracking",
            )

    try:
        for field, value in product_data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        await db.commit()
        await db.refresh(product)
        return product
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A conflict occurred while updating the product")
    except Exception as e:
        await db.rollback()
        logger.error("Database error in update_product: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    product = await get_product_by_id(db, product_id, business.id)  # type: ignore
    try:
        product.is_active = False  # type: ignore
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("Database error in delete_product: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete("/{product_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    product = await get_product_by_id(db, product_id, business.id)  # type: ignore

    usage_result = await db.execute(
        select(func.count()).select_from(InvoiceItem).where(InvoiceItem.product_id == product_id)
    )
    if usage_result.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete product used in invoices. Use soft delete instead.",
        )

    try:
        await db.delete(product)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("Database error in permanently_delete_product: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
