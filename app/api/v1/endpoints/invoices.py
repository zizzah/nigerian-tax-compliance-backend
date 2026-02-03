"""
Invoice API Endpoints
Location: app/api/v1/endpoints/invoices.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import Optional
import uuid
import math
from datetime import date, datetime, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
    InvoiceSummary,
    InvoiceSendRequest,
    InvoiceCancelRequest,
    InvoiceStatistics
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


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


def verify_customer_belongs_to_business(db: Session, customer_id: uuid.UUID, business_id: uuid.UUID) -> Customer:
    """Verify customer belongs to business"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business_id
    ).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found or does not belong to your business"
        )
    
    return customer


# ============================================================================
# Invoice CRUD Endpoints
# ============================================================================

@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new invoice
    
    **Required:**
    - **customer_id**: Customer UUID
    - **items**: List of invoice items (at least 1 required)
    
    **Optional:**
    - **issue_date**: Invoice issue date (default: today)
    - **due_date**: Payment due date (default: 30 days from issue)
    - **discount_amount**: Overall discount
    - **payment_terms**: Payment terms text
    - **notes**: Customer-visible notes
    - **internal_notes**: Internal notes (not visible to customer)
    
    **Auto-calculated:**
    - Invoice number (e.g., INV-00001)
    - Subtotal, tax, and total amounts
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Verify customer
    customer = verify_customer_belongs_to_business(db, invoice_data.customer_id, business.id) # type: ignore
    
    # Generate invoice number
    invoice_number = business.get_next_invoice_number()
    
    # Create invoice
    invoice = Invoice(
        business_id=business.id,
        customer_id=customer.id,
        invoice_number=invoice_number,
        issue_date=invoice_data.issue_date,
        due_date=invoice_data.due_date,
        discount_amount=invoice_data.discount_amount,
        payment_terms=invoice_data.payment_terms or f"Payment due within {customer.payment_terms_days} days",
        notes=invoice_data.notes,
        internal_notes=invoice_data.internal_notes,
        status=InvoiceStatus.DRAFT
    )
    
    db.add(invoice)
    db.flush()  # Get invoice ID
    
    # Create invoice items
    for idx, item_data in enumerate(invoice_data.items):
        item = InvoiceItem(
            invoice_id=invoice.id,
            product_id=item_data.product_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            discount_percent=item_data.discount_percent,
            tax_rate=item_data.tax_rate,
            sort_order=item_data.sort_order if item_data.sort_order > 0 else idx
        )
        
        # Calculate item totals
        item.calculate_totals()
        
        db.add(item)
        
        # Update product usage if product_id provided
        if item_data.product_id:
            product = db.query(Product).filter(Product.id == item_data.product_id).first()
            if product:
                product.increment_usage()
    
    # Calculate invoice totals
    db.flush()  # Ensure items are saved
    db.refresh(invoice)
    invoice.calculate_totals()
    
    # Increment business invoice counter
    business.increment_invoice_counter()
    
    db.commit()
    db.refresh(invoice)
    
    return invoice


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    customer_id: Optional[uuid.UUID] = Query(None, description="Filter by customer"),
    search: Optional[str] = Query(None, description="Search invoice number or customer name"),
    from_date: Optional[date] = Query(None, description="Filter from issue date"),
    to_date: Optional[date] = Query(None, description="Filter to issue date"),
    overdue_only: bool = Query(False, description="Show only overdue invoices"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of invoices
    
    **Query Parameters:**
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (max: 100, default: 50)
    - **status**: Filter by status (DRAFT, SENT, PAID, OVERDUE, CANCELLED)
    - **customer_id**: Filter by specific customer
    - **search**: Search in invoice number or customer name
    - **from_date**: Filter invoices from this date
    - **to_date**: Filter invoices up to this date
    - **overdue_only**: Show only overdue invoices
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Base query
    query = db.query(Invoice).filter(Invoice.business_id == business.id)
    
    # Apply filters
    if status:
        try:
            status_enum = InvoiceStatus[status.upper()]
            query = query.filter(Invoice.status == status_enum) # type: ignore
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, # type: ignore
                detail=f"Invalid status. Must be one of: {', '.join([s.value for s in InvoiceStatus])}"
            )
    
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    
    if search:
        search_term = f"%{search}%"
        query = query.join(Customer).filter(
            or_(
                Invoice.invoice_number.ilike(search_term),
                Customer.name.ilike(search_term)
            )
        )
    
    if from_date:
        query = query.filter(Invoice.issue_date >= from_date)
    
    if to_date:
        query = query.filter(Invoice.issue_date <= to_date)
    
    if overdue_only:
        query = query.filter(
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), # type: ignore
            Invoice.due_date < date.today()
        )
    
    # Get total count
    total = query.count()
    
    # Calculate pagination
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
    # Get paginated results
    invoices = query.order_by(Invoice.created_at.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    return {
        "invoices": invoices,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/summary", response_model=list[InvoiceSummary])
async def list_invoices_summary(
    limit: int = Query(10, ge=1, le=100, description="Max items to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get lightweight summary of invoices (for dropdowns, etc.)
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoices = db.query(Invoice)\
        .filter(Invoice.business_id == business.id)\
        .order_by(Invoice.created_at.desc())\
        .limit(limit)\
        .all()
    
    return invoices


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific invoice by ID
    
    Returns complete invoice details including all line items
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id
    ).first()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    invoice_data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an invoice
    
    **Note:** Only DRAFT invoices can be fully updated.
    SENT invoices can only update notes and payment terms.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id
    ).first()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Check if invoice can be edited
    if invoice.status not in [InvoiceStatus.DRAFT]:
        # Only allow updating notes and payment terms for sent invoices
        allowed_fields = {'payment_terms', 'notes', 'internal_notes'}
        update_data = invoice_data.model_dump(exclude_unset=True)
        if not set(update_data.keys()).issubset(allowed_fields):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft invoices can be fully edited. Sent invoices can only update payment_terms, notes, and internal_notes."
            )
    
    # Update fields
    update_data = invoice_data.model_dump(exclude_unset=True)
    
    # Handle customer change
    if 'customer_id' in update_data:
        verify_customer_belongs_to_business(db, update_data['customer_id'], business.id) # type: ignore
    
    # Handle items update
    if 'items' in update_data and update_data['items']:
        # Delete existing items
        db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).delete()
        
        # Create new items
        for idx, item_data in enumerate(update_data['items']):
            item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item_data.product_id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount_percent=item_data.discount_percent,
                tax_rate=item_data.tax_rate,
                sort_order=item_data.sort_order if item_data.sort_order > 0 else idx
            )
            item.calculate_totals()
            db.add(item)
        
        del update_data['items']
    
    # Update invoice fields
    for field, value in update_data.items():
        setattr(invoice, field, value)
    
    # Recalculate totals if items were updated
    if 'items' in invoice_data.model_dump(exclude_unset=True):
        db.flush()
        db.refresh(invoice)
        invoice.calculate_totals()
    
    db.commit()
    db.refresh(invoice)
    
    return invoice


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an invoice
    
    **Note:** Only DRAFT invoices can be deleted.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id
    ).first()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Only allow deleting draft invoices
    if invoice.status != InvoiceStatus.DRAFT: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft invoices can be deleted. Use cancel endpoint for sent invoices."
        )
    
    db.delete(invoice)
    db.commit()
    
    return None


# ============================================================================
# Invoice Actions
# ============================================================================

@router.post("/{invoice_id}/finalize", response_model=InvoiceResponse)
async def finalize_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Finalize a draft invoice (mark as SENT)
    
    This changes the status from DRAFT to SENT and records the sent timestamp.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id
    ).first()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    if invoice.status != InvoiceStatus.DRAFT: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft invoices can be finalized"
        )
    
    invoice.mark_as_sent()
    db.commit()
    db.refresh(invoice)
    
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    cancel_data: InvoiceCancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel an invoice
    
    Cancels the invoice and optionally records cancellation reason in internal notes.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id
    ).first()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    if invoice.status == InvoiceStatus.PAID: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a paid invoice"
        )
    
    if invoice.status == InvoiceStatus.CANCELLED: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already cancelled"
        )
    
    # Add cancellation reason to internal notes
    if cancel_data.reason:
        cancellation_note = f"\n[CANCELLED - {datetime.now().strftime('%Y-%m-%d %H:%M')}]: {cancel_data.reason}"
        invoice.internal_notes = (invoice.internal_notes or "") + cancellation_note # type: ignore
    
    invoice.mark_as_cancelled()
    db.commit()
    db.refresh(invoice)
    
    return invoice


# ============================================================================
# Invoice Statistics
# ============================================================================

@router.get("/stats/overview", response_model=InvoiceStatistics)
async def get_invoice_statistics(
    from_date: Optional[date] = Query(None, description="Statistics from date"),
    to_date: Optional[date] = Query(None, description="Statistics to date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get invoice statistics
    
    Returns:
    - Count of invoices by status
    - Total amounts (invoiced, paid, outstanding)
    - Average invoice value
    - Average days to payment
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Base query
    query = db.query(Invoice).filter(Invoice.business_id == business.id)
    
    # Apply date filters
    if from_date:
        query = query.filter(Invoice.issue_date >= from_date)
    if to_date:
        query = query.filter(Invoice.issue_date <= to_date)
    
    invoices = query.all()
    
    # Calculate statistics
    total_invoices = len(invoices)
    draft_invoices = len([i for i in invoices if i.status == InvoiceStatus.DRAFT]) # type: ignore
    sent_invoices = len([i for i in invoices if i.status == InvoiceStatus.SENT]) # type: ignore
    paid_invoices = len([i for i in invoices if i.status == InvoiceStatus.PAID]) # type: ignore
    overdue_invoices = len([i for i in invoices if i.is_overdue])
    cancelled_invoices = len([i for i in invoices if i.status == InvoiceStatus.CANCELLED]) # type: ignore
    
    non_cancelled = [i for i in invoices if i.status != InvoiceStatus.CANCELLED] # type: ignore
    total_invoiced = sum(i.total_amount for i in non_cancelled)
    total_paid = sum(i.paid_amount for i in non_cancelled)
    total_outstanding = total_invoiced - total_paid
    
    average_invoice_value = total_invoiced / len(non_cancelled) if non_cancelled else 0
    
    # Calculate average days to payment
    paid_inv = [i for i in invoices if i.status == InvoiceStatus.PAID and i.paid_at] # type: ignore
    if paid_inv:
        payment_days = [(i.paid_at.date() - i.issue_date).days for i in paid_inv]
        average_days_to_payment = sum(payment_days) / len(payment_days)
    else:
        average_days_to_payment = None
    
    return {
        "total_invoices": total_invoices,
        "draft_invoices": draft_invoices,
        "sent_invoices": sent_invoices,
        "paid_invoices": paid_invoices,
        "overdue_invoices": overdue_invoices,
        "cancelled_invoices": cancelled_invoices,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "average_invoice_value": average_invoice_value,
        "average_days_to_payment": average_days_to_payment
    }