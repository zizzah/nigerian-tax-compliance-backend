"""
Business API Endpoints
Location: app/api/v1/endpoints/businesses.py
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.encryption import encrypt
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.schemas.business import (
    BusinessCreate,  # type: ignore
    BusinessUpdate,
    BusinessResponse,
    BusinessSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/businesses", tags=["Businesses"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_business_or_404(db: AsyncSession, user_id) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return business


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/", response_model=BusinessResponse, status_code=201)
async def create_business(
    business_data: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.user_id == current_user.id))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Business profile already exists. Use PATCH /businesses/me to update.",
        )

    business = Business(**business_data.model_dump(), user_id=current_user.id)
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/me", response_model=BusinessResponse)
async def get_my_business(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_business_or_404(db, current_user.id)


@router.patch("/me", response_model=BusinessResponse)
async def update_my_business(
    business_data: BusinessUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business_or_404(db, current_user.id)
    for field, value in business_data.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    await db.commit()
    await db.refresh(business)
    return business


@router.delete("/me", status_code=204)
async def delete_my_business(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business_or_404(db, current_user.id)
    await db.delete(business)
    await db.commit()


@router.get("/me/summary", response_model=BusinessSummary)
async def get_business_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_business_or_404(db, current_user.id)


# ── Logo upload ───────────────────────────────────────────────────────────────
# Cloudinary removed — logo is now stored as base64 in the database.
# Max 200KB to keep DB row size reasonable.

@router.post("/me/logo", response_model=BusinessResponse)
async def upload_business_logo(
    logo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a business logo.
    Stored as a base64 data URL in the database.
    Allowed formats: PNG, JPG. Max size: 200KB.
    """
    business = await get_business_or_404(db, current_user.id)

    allowed_types = {"image/png", "image/jpeg", "image/jpg"}
    if logo.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PNG, JPG")

    contents = await logo.read()

    if len(contents) > 200 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max size: 200KB")

    import base64
    data_url = f"data:{logo.content_type};base64,{base64.b64encode(contents).decode()}"
    business.logo_url = data_url  # type: ignore

    await db.commit()
    await db.refresh(business)
    return business


# ── Utility ───────────────────────────────────────────────────────────────────

@router.get("/me/next-invoice-number")
async def get_next_invoice_number(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business_or_404(db, current_user.id)
    return {
        "next_invoice_number": business.get_next_invoice_number(),
        "current_counter":     business.invoice_counter,
        "prefix":              business.invoice_prefix,
    }


# ── Paystack ──────────────────────────────────────────────────────────────────

class PaystackKeysRequest(BaseModel):
    public_key: str = ""
    secret_key: str = ""


@router.post("/me/paystack", status_code=200)
async def save_paystack_keys(
    data: PaystackKeysRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business_or_404(db, current_user.id)

    if data.public_key:
        business.paystack_public_key = data.public_key  # type: ignore
    if data.secret_key:
        business.paystack_secret_key = encrypt(data.secret_key)  # type: ignore

    await db.commit()
    await db.refresh(business)

    return {
        "message":        "Paystack keys saved successfully",
        "has_public_key": bool(getattr(business, "paystack_public_key", None)),
        "has_secret_key": bool(getattr(business, "paystack_secret_key", None)),
    }


@router.get("/me/paystack/status", status_code=200)
async def get_paystack_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.user_id == current_user.id))
    business = result.scalar_one_or_none()

    if not business:
        return {"has_public_key": False, "has_secret_key": False, "configured": False}

    return {
        "has_public_key": bool(getattr(business, "paystack_public_key", None)),
        "has_secret_key": bool(getattr(business, "paystack_secret_key", None)),
        "configured":     bool(
            getattr(business, "paystack_public_key", None)
            and getattr(business, "paystack_secret_key", None)
        ),
    }