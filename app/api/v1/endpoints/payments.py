"""
Payment API Endpoints
Location: app/api/v1/endpoints/payments.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
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


def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    return business


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record a payment for an invoice
    
    Automatically updates:
    - Invoice paid_amount and outstanding_amount
    - Invoice status (PAID if fully paid)
    - Customer analytics
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Get invoice
    invoice = db.query(Invoice).filter(
        Invoice.id == payment_data.invoice_id,
        Invoice.business_id == business.id
    ).first()
    
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
    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first()
    if customer:
        customer.update_analytics(db)
    
    db.commit()
    db.refresh(payment)
    
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
    db: Session = Depends(get_db)
):
    """Get paginated list of payments"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    query = db.query(Payment).filter(Payment.business_id == business.id)
    
    if invoice_id:
        query = query.filter(Payment.invoice_id == invoice_id)
    if customer_id:
        query = query.filter(Payment.customer_id == customer_id)
    if from_date:
        query = query.filter(Payment.payment_date >= from_date)
    if to_date:
        query = query.filter(Payment.payment_date <= to_date)
    
    total = query.count()
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
    payments = query.order_by(Payment.payment_date.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
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
    db: Session = Depends(get_db)
):
    """Get specific payment"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.business_id == business.id
    ).first()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    return payment


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: uuid.UUID,
    payment_data: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update payment details"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.business_id == business.id
    ).first()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    update_data = payment_data.model_dump(exclude_unset=True)
    
    # If amount is being updated, recalculate invoice totals
    if 'amount' in update_data:
        old_amount = payment.amount
        new_amount = update_data['amount']
        
        invoice = db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()
        invoice.paid_amount = invoice.paid_amount - old_amount + new_amount # type: ignore
        invoice.outstanding_amount = invoice.total_amount - invoice.paid_amount # type: ignore
        invoice.update_status() # type: ignore
    
    for field, value in update_data.items():
        setattr(payment, field, value)
    
    db.commit()
    db.refresh(payment)
    
    return payment


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a payment (reverses the payment)"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.business_id == business.id
    ).first()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # Update invoice
    invoice = db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()
    invoice.paid_amount -= payment.amount # type: ignore
    invoice.outstanding_amount = invoice.total_amount - invoice.paid_amount # type: ignore
    invoice.update_status() # type: ignore
    
    # Delete payment
    db.delete(payment)
    
    # Update customer analytics
    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first() # type: ignore
    if customer:
        customer.update_analytics(db)
    
    db.commit()
    
    return None