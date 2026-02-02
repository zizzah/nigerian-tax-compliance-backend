"""
Business API Endpoints
Location: app/api/v1/endpoints/businesses.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import os
from pathlib import Path

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.schemas.business import (
    BusinessCreate,
    BusinessUpdate,
    BusinessResponse,
    BusinessSummary
)

router = APIRouter(prefix="/businesses", tags=["Businesses"])


# ============================================================================
# Business Profile Endpoints
# ============================================================================

@router.post("/", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def create_business(
    business_data: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a business profile for the current user.
    
    - **business_name**: Required business name (2-255 chars)
    - **business_type**: Optional (e.g., "Limited Liability Company")
    - **industry**: Optional (e.g., "Technology", "Retail")
    - **tin**: Optional Tax Identification Number
    - **vat_registered**: Boolean indicating VAT registration status
    
    **Note**: Each user can only have one business profile.
    """
    # Check if user already has a business
    existing_business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if existing_business:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business profile already exists. Use PATCH /businesses/me to update."
        )
    
    # Create new business
    business = Business(
        **business_data.model_dump(),
        user_id=current_user.id
    )
    
    db.add(business)
    db.commit()
    db.refresh(business)
    
    return business


@router.get("/me", response_model=BusinessResponse)
async def get_my_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses"
        )
    
    return business


@router.patch("/me", response_model=BusinessResponse)
async def update_my_business(
    business_data: BusinessUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses"
        )
    
    # Update only provided fields
    update_data = business_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)
    
    db.commit()
    db.refresh(business)
    
    return business


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    
    db.delete(business)
    db.commit()
    
    return None


@router.get("/me/summary", response_model=BusinessSummary)
async def get_business_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a lightweight summary of the current user's business.
    
    Useful for displaying business info in headers, dashboards, etc.
    """
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    
    return business


# ============================================================================
# Logo Upload Endpoint
# ============================================================================

@router.post("/me/logo", response_model=BusinessResponse)
async def upload_business_logo(
    logo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a business logo.
    
    - **Allowed formats**: PNG, JPG, JPEG
    - **Max size**: 5MB
    - **Recommended dimensions**: 500x500px square
    
    The logo will be stored and the URL will be saved to the business profile.
    """
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    
    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg"]
    if logo.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: PNG, JPG, JPEG"
        )
    
    # Validate file size (5MB)
    file_size = 0
    chunk_size = 1024 * 1024  # 1MB
    for chunk in iter(lambda: logo.file.read(chunk_size), b""):
        file_size += len(chunk)
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File too large. Max size: 5MB"
            )
    
    # Reset file pointer
    logo.file.seek(0)
    
    # Create uploads directory if it doesn't exist
    upload_dir = Path("uploads/logos")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_extension = logo.filename.split(".")[-1] # type: ignore
    filename = f"{business.id}.{file_extension}"
    file_path = upload_dir / filename
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(logo.file.read())
    
    # Update business logo_url
    business.logo_url = f"/uploads/logos/{filename}" # type: ignore
    db.commit()
    db.refresh(business)
    
    return business


# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get("/me/next-invoice-number")
async def get_next_invoice_number(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the next invoice number that will be generated.
    
    Useful for previewing invoice numbers before creation.
    """
    business = db.query(Business).filter(
        Business.user_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    
    return {
        "next_invoice_number": business.get_next_invoice_number(),
        "current_counter": business.invoice_counter,
        "prefix": business.invoice_prefix
    }