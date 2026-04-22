"""
Payment API Endpoints
Location: app/api/v1/endpoints/payments.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import select,func


from typing import Optional
import uuid
import math
from datetime import date

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.customer import Customer
from app.models.payment import Payment
from app.schemas.payment import (
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    PaymentListResponse
)

router = APIRouter(prefix="/payments", tags=["Payments"])


async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business =await db.execute(select(Business).where(Business.user_id == user_id))
    business = business.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    return business


async def get_payment_by_id(db:AsyncSession, payment_id:uuid.UUID, business_id:uuid.UUID) -> Payment:
    payment = await db.execute(select(Payment).where(Payment.id == payment_id,Payment.business_id == business_id))
    payment = payment.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    return payment
        
    



@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession= Depends(get_db)
):
    """
    Record a payment for an invoice
    
    Automatically updates:
    - Invoice paid_amount and outstanding_amount
    - Invoice status (PAID if fully paid)
    - Customer analytics
    """
    business = await get_user_business(db, current_user.id) # type: ignore
    
    # Get invoice
    
    invoice = await db.execute(select(Invoice).where(Invoice.id==payment_data.invoice_id))
    invoice= invoice.scalar_one_or_none()
    
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Validate payment amount
    if payment_data.amount > invoice.outstanding_amount: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment amount (₦{payment_data.amount}) exceeds outstanding amount (₦{invoice.outstanding_amount})"
        )
    
    # Create payment
    payment = Payment(
        **payment_data.model_dump(exclude={'invoice_id'}),
        invoice_id=invoice.id,
        business_id=business.id,
        customer_id=invoice.customer_id
    )
    
    # Generate receipt number
    payment.generate_receipt_number(business.invoice_prefix) # type: ignore
    
    db.add(payment)
    
    # Update invoice
    invoice.paid_amount += payment_data.amount # type: ignore
    invoice.outstanding_amount = invoice.total_amount - invoice.paid_amount
    invoice.update_status()
    
    # Update customer analytics
    customer =await  db.execute( select(Customer).where(Customer.id == invoice.customer_id))
    customer = customer.scalar_one_or_none()
    if customer:
        await customer.update_analytics(db) 
    
    await db.commit()
    await db.refresh(payment)
    
    return payment


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    invoice_id: Optional[uuid.UUID] = Query(None),
    customer_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import func

    business = await get_user_business(db, current_user.id)  # type: ignore

    # Build statement with filters BEFORE executing
    filters = [Payment.business_id == business.id]
    if invoice_id:
        filters.append(Payment.invoice_id == invoice_id)
    if customer_id:
        filters.append(Payment.customer_id == customer_id)
    if from_date:
        filters.append(Payment.payment_date >= from_date)
    if to_date:
        filters.append(Payment.payment_date <= to_date)

    # Count query
    total = (await db.execute(
        select(func.count()).select_from(Payment).where(*filters)
    )).scalar_one()

    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size

    # Data query
    payments = (await db.execute(
        select(Payment)
        .where(*filters)
        .order_by(Payment.payment_date.desc())
        .offset(offset)
        .limit(page_size)
    )).scalars().all()

    return {
        "payments": payments,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific payment"""
    business =await  get_user_business(db, current_user.id) # type: ignore
    
    payment =await  get_payment_by_id(db, payment_id,business.id) # type: ignore
    
    return payment


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: uuid.UUID,
    payment_data: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update payment details"""
    business =await  get_user_business(db, current_user.id) # type: ignore
    
    payment =await  get_payment_by_id(db, payment_id,business.id) # type: ignore
    
    update_data = payment_data.model_dump(exclude_unset=True)
    
    # If amount is being updated, recalculate invoice totals
    if 'amount' in update_data:
        old_amount = payment.amount
        new_amount = update_data['amount']
        
        invoice = await  db.execute(select(Invoice).where(Invoice.id == payment.invoice_id))
        invoice =invoice.scalar_one_or_none()
        invoice.paid_amount = invoice.paid_amount - old_amount + new_amount # type: ignore
        invoice.outstanding_amount = invoice.total_amount - invoice.paid_amount # type: ignore
        invoice.update_status() # type: ignore
    
    for field, value in update_data.items():
        setattr(payment, field, value)
    
    await db.commit()
    await db.refresh(payment)
    
    return payment


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a payment (reverses the payment)"""
    business =await  get_user_business(db, current_user.id) # type: ignore
    
    payment =await  get_payment_by_id(db, payment_id,business.id) # type: ignore
    
    # Update invoice
    invoice =await  db.execute(select(Invoice).where(Invoice.id == payment.invoice_id))
    invoice = invoice.scalar_one_or_none()
    invoice.paid_amount -= payment.amount # type: ignore
    invoice.outstanding_amount = invoice.total_amount - invoice.paid_amount # type: ignore
    invoice.update_status() # type: ignore
    
    # Delete payment
    await db.delete(payment)
    
    # Update customer analytics
    customer = await  db.execute(select(Customer).where(Customer.id == invoice.customer_id)) # type: ignore
    customer= customer.scalar_one_or_none()
    if customer:
        await customer.update_analytics(db) # type: ignore
    
    await db.commit()
    
    return None