"""
Business API Endpoints
Location: app/api/v1/endpoints/businesses.py
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import select



from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.schemas.business import (
    BusinessCreate, # type: ignore
    BusinessUpdate,
    BusinessResponse,
    BusinessSummary
)


import cloudinary
import cloudinary.uploader
from app.core.encryption import encrypt

from app.core.config import settings
logger = logging.getLogger(__name__)
# Configure Cloudinary — put this at the top of businesses.py
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,  # always use HTTPS
)

router = APIRouter(prefix="/businesses", tags=["Businesses"])


# ============================================================================
# Business Profile Endpoints
# ============================================================================

async def get_business_or_404(db: AsyncSession, user_id) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    return business

@router.post("/", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def create_business(
    business_data: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.user_id == current_user.id))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business profile already exists. Use PATCH /businesses/me to update."
        )

    business = Business(**business_data.model_dump(), user_id=current_user.id)
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business

@router.get("/me", response_model=BusinessResponse)
async def get_my_business(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current user's business profile.
    
    Returns the complete business profile including:
    - Business information
    - Tax details
    - Contact information
    - Branding settings
    - Invoice settings
    - Subscription details
    """
    business = await get_business_or_404(db, current_user.id)
    
    return business


@router.patch("/me", response_model=BusinessResponse)
async def update_my_business(
    business_data: BusinessUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the current user's business profile.
    
    All fields are optional - only provided fields will be updated.
    
    **Updatable fields:**
    - Business information (name, type, industry)
    - Tax details (TIN, VAT registration)
    - Contact information
    - Branding (colors, logo)
    - Invoice settings (prefix)
    """
    business = await get_business_or_404(db, current_user.id)
    
    # Update only provided fields
    update_data = business_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)
    
    await db.commit()
    await db.refresh(business)
    
    return business


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_business(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete the current user's business profile.
    
    **Warning**: This will also delete all associated data:
    - Customers
    - Invoices
    - Documents
    - Analytics
    
    This action cannot be undone!
    """
    business = await get_business_or_404(db, current_user.id)
    
    await db.delete(business)
    await db.commit()
    
    return None


@router.get("/me/summary", response_model=BusinessSummary)
async def get_business_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a lightweight summary of the current user's business.
    
    Useful for displaying business info in headers, dashboards, etc.
    """
    business = await get_business_or_404(db, current_user.id)

    
    return business


# ============================================================================
# Logo Upload Endpoint
# ============================================================================

@router.post("/me/logo", response_model=BusinessResponse)
async def upload_business_logo(
    logo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a business logo to Cloudinary.

    - **Allowed formats**: PNG, JPG, JPEG
    - **Max size**: 5MB
    - **Recommended dimensions**: 500x500px square
    """
    business = await get_business_or_404(db, current_user.id)

    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg"]
    if logo.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: PNG, JPG, JPEG"
        )

    # Read file into memory asynchronously
    contents = await logo.read()

    # Validate file size (5MB)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Max size: 5MB"
        )

    # Upload to Cloudinary
    # cloudinary.uploader.upload() is sync — run in threadpool to avoid blocking
    try:
        
        result = await asyncio.get_running_loop().run_in_executor(
            None,  # uses default threadpool
            lambda: cloudinary.uploader.upload(
                contents,
                folder="business_logos",
                public_id=str(business.id),  # use business ID as filename
                overwrite=True,              # replace existing logo on re-upload
                resource_type="image",
                transformation=[
                    {"width": 500, "height": 500, "crop": "limit"},  # resize to max 500x500
                    {"quality": "auto"},                               # auto-optimise quality
                    {"fetch_format": "auto"},                          # serve webp to browsers that support it
                ]
            )
        )
    except Exception as e:
        logger.error("Cloudinary upload failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload logo. Please try again."
        )

    # Save the Cloudinary URL to the business profile
    business.logo_url = result["secure_url"]  # type: ignore
    await db.commit()
    await db.refresh(business)

    return business

# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get("/me/next-invoice-number")
async def get_next_invoice_number(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the next invoice number that will be generated.
    
    Useful for previewing invoice numbers before creation.
    """
    business = await get_business_or_404(db, current_user.id)
    
    return {
        "next_invoice_number": business.get_next_invoice_number(),
        "current_counter": business.invoice_counter,
        "prefix": business.invoice_prefix
    }

# ============================================================================
# Paystack Keys Endpoint
# ============================================================================

class PaystackKeysRequest(BaseModel):
    public_key: str = ""
    secret_key: str = ""


@router.post("/me/paystack", status_code=status.HTTP_200_OK)
async def save_paystack_keys(
    data: PaystackKeysRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save Paystack API keys for this business.
    Each business on the platform has their own Paystack account and keys.
    Keys are stored per-business so payments go directly into each business's account.
    """
    business = await get_business_or_404(db, current_user.id)

    if data.public_key:
        business.paystack_public_key = data.public_key # type: ignore
    if data.secret_key:
        business.paystack_secret_key = encrypt(data.secret_key)  # type: ignore # Encrypt secret key before saving

    await db.commit()
    await db.refresh(business)

    return {
        "message": "Paystack keys saved successfully",
        "has_public_key": bool(getattr(business, "paystack_public_key", None)),
        "has_secret_key": bool(getattr(business, "paystack_secret_key", None)),
    }


@router.get("/me/paystack/status", status_code=status.HTTP_200_OK)
async def get_paystack_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check whether this business has Paystack keys configured."""
    business = await get_business_or_404(db, current_user.id)

    
    return {
        "has_public_key": bool(getattr(business, "paystack_public_key", None)),
        "has_secret_key": bool(getattr(business, "paystack_secret_key", None)),
        "configured": bool(
            getattr(business, "paystack_public_key", None) and
            getattr(business, "paystack_secret_key", None)
        ),
    }