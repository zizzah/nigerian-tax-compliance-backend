"""
COMPLETE Invoice API Endpoints with PDF Generation
Location: app/api/v1/endpoints/invoices.py

Includes all CRUD operations + PDF generation
"""
from asyncio.log import logger
from fastapi import APIRouter, Depends, HTTPException, status, Query # type: ignore
from fastapi.responses import Response # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import or_, and_, func # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore
from typing import Optional
import uuid
import math
from datetime import date, datetime, timedelta
import time
from io import BytesIO

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
from sqlalchemy import select # type: ignore
from app.models.business import Business as BusinessModel
from app.models.invoice import Invoice
import logging
import time


# PDF Generation imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

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






# Replace the generate_unique_invoice_number function with this:


def generate_unique_invoice_number(db: Session, business: Business, max_retries: int = 10) -> str:
    """
    Generate unique invoice number with database locking (IMPROVED - handles existing duplicates)
    
    This function:
    1. Prevents race conditions using SELECT FOR UPDATE
    2. Skips over existing duplicate invoice numbers from previous runs
    3. Automatically finds the next available number
    """
    
    logger = logging.getLogger(__name__)
    
    for attempt in range(max_retries):
        try:
            # Lock business row to prevent race conditions
            stmt = select(BusinessModel).where(
                BusinessModel.id == business.id
            ).with_for_update()
            
            locked_business = db.execute(stmt).scalar_one_or_none()
            
            if not locked_business:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )
            
            # Increment counter
            locked_business.invoice_counter += 1
            next_counter = locked_business.invoice_counter
            
            # Generate invoice number
            invoice_number = f"{locked_business.invoice_prefix}-{str(next_counter).zfill(5)}"
            
            # ================================================================
            # NEW: Check if this number already exists (from old duplicates)
            # ================================================================
            existing = db.query(Invoice).filter(
                Invoice.invoice_number == invoice_number
            ).first()
            
            if existing:
                # Duplicate found! Log warning and continue to next number
                logger.warning(
                    f"Invoice number {invoice_number} already exists (from previous run). "
                    f"Skipping to next number... (attempt {attempt + 1}/{max_retries})"
                )
                # Commit the incremented counter and try again
                db.commit()
                time.sleep(0.05)
                continue
            
            # ================================================================
            # Number is unique - commit and return
            # ================================================================
            db.commit()
            business.invoice_counter = next_counter
            
            logger.info(f"✓ Generated unique invoice number: {invoice_number}")
            return invoice_number
            
        except Exception as e:
            logger.error(f"Error generating invoice number (attempt {attempt + 1}/{max_retries}): {e}")
            db.rollback()
            
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to generate unique invoice number after {max_retries} attempts"
                )
            
            time.sleep(0.1 * (attempt + 1))
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate invoice number"
    )

def generate_invoice_pdf(invoice: Invoice, business: Business, customer: Customer) -> BytesIO:
    """
    Generate a professional PDF invoice
    
    Args:
        invoice: Invoice object with items loaded
        business: Business object
        customer: Customer object
    
    Returns:
        BytesIO: PDF file as bytes
    """
    if not PDF_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation not available. Install reportlab: pip install reportlab"
        )
    
    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           rightMargin=20*mm, leftMargin=20*mm,
                           topMargin=20*mm, bottomMargin=20*mm)
    
    # Container for PDF elements
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=12,
        alignment=TA_LEFT
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#34495E'),
        spaceAfter=6,
        alignment=TA_LEFT
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#2C3E50')
    )
    
    # ========== HEADER ==========
    # Business name and invoice title
    elements.append(Paragraph(business.business_name or "Business Name", title_style)) # type: ignore
    elements.append(Paragraph(f"<b>INVOICE {invoice.invoice_number}</b>", heading_style))
    elements.append(Spacer(1, 12))
    
    # ========== BUSINESS & CUSTOMER INFO ==========
    # Create a table for business and customer info side by side
    info_data = [
        [
            Paragraph("<b>From:</b>", normal_style),
            Paragraph("<b>Bill To:</b>", normal_style)
        ],
        [
            Paragraph(f"{business.business_name or 'N/A'}<br/>"
                     f"{business.address or ''}<br/>"
                     f"{business.city or ''}, {business.state or ''}<br/>"
                     f"TIN: {business.tin or 'N/A'}<br/>"
                     f"Phone: {business.phone or 'N/A'}", normal_style),
            Paragraph(f"{customer.name}<br/>"
                     f"{customer.address or ''}<br/>"
                     f"{customer.city or ''}, {customer.state or ''}<br/>"
                     f"TIN: {customer.tin or 'N/A'}<br/>"
                     f"Phone: {customer.phone or 'N/A'}", normal_style)
        ]
    ]
    
    info_table = Table(info_data, colWidths=[3*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # ========== INVOICE DETAILS ==========
    details_data = [
        [Paragraph("<b>Invoice Date:</b>", normal_style), 
         Paragraph(f"{invoice.issue_date.strftime('%B %d, %Y')}", normal_style),
         Paragraph("<b>Due Date:</b>", normal_style),
         Paragraph(f"{invoice.due_date.strftime('%B %d, %Y')}", normal_style)],
        [Paragraph("<b>Status:</b>", normal_style),
         Paragraph(f"{invoice.status.value}", normal_style),
         Paragraph("<b>Payment Terms:</b>", normal_style),
         Paragraph(f"{invoice.payment_terms or 'N/A'}", normal_style)]
    ]
    
    details_table = Table(details_data, colWidths=[1.2*inch, 1.8*inch, 1.2*inch, 1.8*inch])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(details_table)
    elements.append(Spacer(1, 20))
    
    # ========== LINE ITEMS TABLE ==========
    # Table headers
    items_data = [
        [Paragraph("<b>Description</b>", normal_style),
         Paragraph("<b>Qty</b>", normal_style),
         Paragraph("<b>Unit Price</b>", normal_style),
         Paragraph("<b>Tax</b>", normal_style),
         Paragraph("<b>Amount</b>", normal_style)]
    ]
    
    # Add invoice items
    for item in invoice.items:
        items_data.append([
            Paragraph(item.description or "Item", normal_style),
            Paragraph(f"{item.quantity}", normal_style),
            Paragraph(f"₦{item.unit_price:,.2f}", normal_style),
            Paragraph(f"{item.tax_rate}%", normal_style),
            Paragraph(f"₦{item.line_total:,.2f}", normal_style)
        ])
    
    items_table = Table(items_data, colWidths=[3*inch, 0.6*inch, 1*inch, 0.6*inch, 1*inch])
    items_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Data rows
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#34495E')),
    ]))
    
    elements.append(items_table)
    elements.append(Spacer(1, 20))
    
    # ========== TOTALS ==========
    totals_data = [
        ['', '', '', Paragraph("<b>Subtotal:</b>", normal_style), 
         Paragraph(f"₦{invoice.subtotal:,.2f}", normal_style)],
    ]
    
    if invoice.discount_amount > 0: # type: ignore
        totals_data.append([
            '', '', '', Paragraph("<b>Discount:</b>", normal_style),
            Paragraph(f"-₦{invoice.discount_amount:,.2f}", normal_style)
        ])
    
    totals_data.extend([
        ['', '', '', Paragraph("<b>Tax:</b>", normal_style),
         Paragraph(f"₦{invoice.tax_amount:,.2f}", normal_style)],
        ['', '', '', Paragraph("<b>TOTAL:</b>", heading_style),
         Paragraph(f"<b>₦{invoice.total_amount:,.2f}</b>", heading_style)],
    ])
    
    if invoice.paid_amount > 0: # type: ignore
        totals_data.extend([
            ['', '', '', Paragraph("<b>Paid:</b>", normal_style),
             Paragraph(f"₦{invoice.paid_amount:,.2f}", normal_style)],
            ['', '', '', Paragraph("<b>Balance Due:</b>", heading_style),
             Paragraph(f"<b>₦{invoice.outstanding_amount:,.2f}</b>", heading_style)],
        ])
    
    totals_table = Table(totals_data, colWidths=[2*inch, 1*inch, 1*inch, 1.2*inch, 1*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (3, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (3, 0), (-1, -1), 10),
        ('TOPPADDING', (3, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (3, 0), (-1, -1), 3),
        ('LINEABOVE', (3, -2), (-1, -2), 2, colors.HexColor('#34495E')),
    ]))
    
    elements.append(totals_table)
    
    # ========== NOTES ==========
    if invoice.notes: # type: ignore
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("<b>Notes:</b>", heading_style))
        elements.append(Paragraph(invoice.notes, normal_style)) # type: ignore
    
    # ========== FOOTER ==========
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Paragraph(
        f"Thank you for your business!<br/>"
        f"For questions, contact {business.email or business.phone or 'us'}",
        footer_style
    ))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF bytes
    buffer.seek(0)
    return buffer


# ============================================================================
# INVOICE CRUD ENDPOINTS (keeping existing code)
# ============================================================================

@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new invoice with improved error handling"""
    try:
        business = get_user_business(db, current_user.id) # type: ignore
        customer = verify_customer_belongs_to_business(db, invoice_data.customer_id, business.id) # type: ignore
        invoice_number = generate_unique_invoice_number(db, business)
        
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
        
        try:
            db.flush()
        except IntegrityError as e:
            db.rollback()
            if "ix_invoices_invoice_number" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Invoice number {invoice_number} already exists. Please try again."
                )
            raise
        
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
            
            item.calculate_totals()
            db.add(item)
            
            if item_data.product_id:
                product = db.query(Product).filter(Product.id == item_data.product_id).first()
                if product:
                    product.increment_usage()
        
        db.flush()
        db.refresh(invoice)
        invoice.calculate_totals()
        business.invoice_counter += 1
        
        db.commit()
        db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create invoice: {str(e)}"
        )


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[InvoiceStatus] = Query(None),
    customer_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get paginated list of invoices"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    query = db.query(Invoice).filter(Invoice.business_id == business.id)
    
    if status:
        query = query.filter(Invoice.status == status) # type: ignore
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    if from_date:
        query = query.filter(Invoice.issue_date >= from_date)
    if to_date:
        query = query.filter(Invoice.issue_date <= to_date)
    
    total = query.count()
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
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


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific invoice by ID"""
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
    """Update an invoice (only DRAFT invoices can be fully updated)"""
    try:
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
            allowed_fields = {'notes', 'internal_notes', 'payment_terms'}
            update_data = invoice_data.model_dump(exclude_unset=True)
            invalid_fields = set(update_data.keys()) - allowed_fields
            
            if invalid_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Only notes and payment_terms can be updated for non-draft invoices. "
                           f"Attempted to update: {', '.join(invalid_fields)}"
                )
        
        update_data = invoice_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(invoice, field, value)
        
        db.commit()
        db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update invoice: {str(e)}"
        )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a draft invoice"""
    try:
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
                detail="Only draft invoices can be deleted. Use cancel endpoint for sent invoices."
            )
        
        db.delete(invoice)
        db.commit()
        
        return None
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete invoice: {str(e)}"
        )


@router.post("/{invoice_id}/finalize", response_model=InvoiceResponse)
async def finalize_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Finalize a draft invoice (mark as SENT)"""
    try:
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
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to finalize invoice: {str(e)}"
        )


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    cancel_data: InvoiceCancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel an invoice"""
    try:
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
        
        if cancel_data.reason:
            cancellation_note = f"\n[CANCELLED - {datetime.now().strftime('%Y-%m-%d %H:%M')}]: {cancel_data.reason}"
            invoice.internal_notes = (invoice.internal_notes or "") + cancellation_note # type: ignore
        
        invoice.mark_as_cancelled()
        db.commit()
        db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel invoice: {str(e)}"
        )


@router.get("/stats/overview", response_model=InvoiceStatistics)
async def get_invoice_statistics(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get invoice statistics"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    query = db.query(Invoice).filter(Invoice.business_id == business.id)
    
    if from_date:
        query = query.filter(Invoice.issue_date >= from_date)
    if to_date:
        query = query.filter(Invoice.issue_date <= to_date)
    
    invoices = query.all()
    
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


# ============================================================================
# PDF GENERATION ENDPOINT (NEW!)
# ============================================================================

@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate and download invoice as PDF
    
    **Returns:**
    - PDF file with professional invoice layout
    - Filename: invoice_{invoice_number}.pdf
    
    **Features:**
    - Professional formatting with business branding
    - Itemized line items with tax breakdown
    - Payment status and balance due
    - Customer and business information
    """
    if not PDF_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF generation is not available. Install reportlab: pip install reportlab --break-system-packages"
        )
    
    try:
        # Get business
        business = get_user_business(db, current_user.id) # type: ignore
        
        # Get invoice with relationships
        invoice = db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.business_id == business.id
        ).first()
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found"
            )
        
        # Get customer
        customer = invoice.customer
        
        # Generate PDF
        pdf_buffer = generate_invoice_pdf(invoice, business, customer)
        
        # Return as downloadable file
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=invoice_{invoice.invoice_number}.pdf"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )