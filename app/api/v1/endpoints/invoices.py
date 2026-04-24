"""
COMPLETE Invoice API Endpoints with PDF Generation
Location: app/api/v1/endpoints/invoices.py

Includes all CRUD operations + PDF generation
"""
import uuid
import math
import os
import urllib.request
import tempfile
import logging
from io import BytesIO
from typing import Optional
from datetime import date, datetime, timezone

import asyncio


from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks  # type: ignore
from fastapi.responses import Response  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import case, select
from sqlalchemy import func, text, select ,DateTime # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.core.email import send_invoice_email
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.business import Business as BusinessModel
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

# PDF Generation imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

router = APIRouter(prefix="/invoices", tags=["Invoices"])


# ============================================================================
# Helper Functions
# ============================================================================


def _register_unicode_fonts() -> tuple[str, str]:
    """Register a Unicode-capable font for PDF currency rendering."""
    if not PDF_AVAILABLE:
        return "Helvetica", "Helvetica-Bold"

    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
            os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf"),
        ),
    ]

    for regular_path, bold_path in candidates:
        if os.path.exists(regular_path) and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", regular_path))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
            return "DejaVuSans", "DejaVuSans-Bold"

    return "Helvetica", "Helvetica-Bold"


FONT_NORMAL, FONT_BOLD = _register_unicode_fonts()
PDF_CURRENCY_SYMBOL = "₦" if FONT_NORMAL != "Helvetica" else "NGN "

# Default PDF palette aligned with the frontend's TaxFlow NG theme.
DEFAULT_BRAND_GREEN = "#1a6b4a"
DEFAULT_BRAND_GOLD = "#c8952a"
DEFAULT_BRAND_PAPER = "#faf9f6"
DEFAULT_BRAND_WARM = "#ede9de"
DEFAULT_BRAND_TEXT = "#2c2a24"
DEFAULT_BRAND_TEXT_MID = "#6b6560"


def _is_valid_hex(h: str) -> bool:
    return h.startswith('#') and len(h) == 7 and all(c in '0123456789abcdefABCDEF' for c in h[1:])


def _relative_luminance(hex_color: str) -> float:
    """Return relative luminance from 0 (black) to 1 (white)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _sanitise_brand_color(hex_input: str, fallback: str) -> str:
    h = (hex_input or "").strip().lower()
    if not _is_valid_hex(h):
        return fallback

    lum = _relative_luminance(h)
    if lum < 0.05 or lum > 0.90:
        return fallback

    return h


def _pdf_money(amount: float) -> str:
    return f"{PDF_CURRENCY_SYMBOL}{float(amount):,.2f}"

async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses"
        )
    return business


async def verify_customer_belongs_to_business(db: AsyncSession, customer_id: uuid.UUID, business_id: uuid.UUID) -> Customer:
    """Verify customer belongs to business"""
    result = await db.execute(select(Customer).where(
        Customer.id == customer_id,
        Customer.business_id == business_id
    ))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found or does not belong to your business"
        )
    
    return customer



async def get_invoice_by_id(db: AsyncSession, invoice_id: uuid.UUID, business_id: uuid.UUID) -> Invoice:
    """Get invoice by ID, ensuring it belongs to the business"""
    result = await db.execute(select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.business_id == business_id
    ))
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    return invoice


async def get_customer_by_id(db: AsyncSession, customer_id: uuid.UUID, business_id: uuid.UUID) -> Customer:
    """Get customer by ID, ensuring it belongs to the business"""
    result = await db.execute(select(Customer).where(
        Customer.id == customer_id,
        Customer.business_id == business_id
    ))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    return customer

# Replace the generate_unique_invoice_number function with this:


async def generate_unique_invoice_number(db: AsyncSession, business: Business, max_retries: int = 10) -> str:
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
            
            result = await db.execute(stmt)
            locked_business = result.scalar_one_or_none()
            
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
            check_stmt = select(Invoice).where(Invoice.invoice_number == invoice_number)
            result = await db.execute(check_stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Duplicate found! Log warning and continue to next number
                logger.warning(
                    "Invoice number %s already exists from previous run; skipping to next number (%d/%d)",
                    invoice_number,
                    attempt + 1,
                    max_retries
                )
                # Commit the incremented counter and try again
                await db.commit()
                await asyncio.sleep(0.05)
                continue
            
            # ================================================================
            # Number is unique - commit and return
            # ================================================================
            await db.commit()
            business.invoice_counter = next_counter
            
            logger.info("Generated unique invoice number:&%s", invoice_number)
            return invoice_number
            
        except Exception as e:
            logger.error("Error generating invoice number (attempt %d/%d): %s", attempt + 1, max_retries, e)
            await db.rollback()
            
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to generate unique invoice number after {max_retries} attempts"
                )
            
            await asyncio.sleep(0.1 * (attempt + 1))
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate invoice number"
    )

def generate_invoice_pdf(invoice: Invoice, business: Business, customer: Customer) -> BytesIO:
    """
    Generate a professional PDF invoice using the business's brand colours.
    primary_color   -> accent (header bar, divider line, totals highlight)
    secondary_color -> table header background
    """
    if not PDF_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation not available. Install reportlab: pip install reportlab"
        )

    # Brand colours
    primary_hex = _sanitise_brand_color(
        getattr(business, 'primary_color', None) or '',
        DEFAULT_BRAND_GREEN,
    )
    secondary_hex = _sanitise_brand_color(
        getattr(business, 'secondary_color', None) or '',
        DEFAULT_BRAND_GOLD,
    )

    col_primary   = colors.HexColor(primary_hex)
    col_secondary = colors.HexColor(secondary_hex)
    col_ink       = colors.HexColor(DEFAULT_BRAND_TEXT)
    col_dim       = colors.HexColor(DEFAULT_BRAND_TEXT_MID)
    col_border    = colors.HexColor(DEFAULT_BRAND_WARM)
    col_paper     = colors.HexColor(DEFAULT_BRAND_PAPER)

    def _tint(hex_color: str, factor: float = 0.10) -> colors.Color:
        r = int(hex_color[1:3], 16); g = int(hex_color[3:5], 16); b = int(hex_color[5:7], 16)
        return colors.Color(int(255+(r-255)*factor)/255, int(255+(g-255)*factor)/255, int(255+(b-255)*factor)/255)

    col_row_alt = _tint(primary_hex, 0.08)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    elements = []
    styles   = getSampleStyleSheet()

    normal_style = ParagraphStyle(
        'N',
        parent=styles['Normal'],
        fontSize=9,
        textColor=col_ink,
        leading=13,
        fontName=FONT_NORMAL,
    )
    dim_style = ParagraphStyle(
        'D',
        parent=styles['Normal'],
        fontSize=8,
        textColor=col_dim,
        leading=11,
        fontName=FONT_NORMAL,
    )
    heading_style = ParagraphStyle(
        'H',
        parent=styles['Normal'],
        fontSize=10,
        textColor=col_ink,
        fontName=FONT_BOLD,
    )
    label_style = ParagraphStyle(
        'L',
        parent=styles['Normal'],
        fontSize=7.5,
        textColor=col_dim,
        fontName=FONT_NORMAL,
        leading=10,
    )

    # Logo
    logo_img = None
    tmp_path = None
    if getattr(business, 'logo_url', None):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                tmp_path = tmp.name
            req = urllib.request.Request(business.logo_url, headers={'User-Agent': 'Mozilla/5.0'})  # type: ignore
            with urllib.request.urlopen(req, timeout=8) as resp:
                open(tmp_path, 'wb').write(resp.read())
            logo_img = Image(tmp_path, width=1.4*inch, height=0.7*inch)
            logo_img.hAlign = 'LEFT'
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
            logo_img = None

    # Header: logo/name left | INVOICE right
    brand_para = Paragraph(
        f"<b>{business.business_name or 'Business'}</b>",  # type: ignore
        ParagraphStyle('Brand', parent=styles['Normal'], fontSize=15, textColor=col_ink, fontName=FONT_BOLD)
    )
    invoice_label = Paragraph(
        f"<font color='{primary_hex}' size='26'><b>INVOICE</b></font>"
        f"<br/><font size='9' color='#6b6560'>{invoice.invoice_number}</font>",
        ParagraphStyle('InvLabel', parent=styles['Normal'], fontSize=26, alignment=TA_RIGHT, fontName=FONT_BOLD)
    )
    left_cell = [logo_img, Spacer(1, 4), brand_para] if logo_img else [brand_para]
    header_table = Table([[left_cell, invoice_label]], colWidths=[3.5*inch, 3.5*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',        (1, 0), (1, 0),   'RIGHT'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW',    (0, 0), (-1, 0),  2, col_primary),
        ('BOTTOMPADDING',(0, 0), (-1, 0),  10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 14))

    # From / Bill To
    def _addr(lines):
        return Paragraph('<br/>'.join(l for l in lines if l), normal_style)

    biz_lines = [
        f"<b>{business.business_name or ''}</b>",  # type: ignore
        business.address or '',  # type: ignore
        f"{business.city or ''}{', ' + business.state if business.state else ''}",  # type: ignore
        f"TIN: {business.tin}" if business.tin else '',  # type: ignore
        business.phone or '',  # type: ignore
    ]
    cus_lines = [
        f"<b>{customer.name}</b>",
        customer.address or '',
        f"{customer.city or ''}{', ' + customer.state if customer.state else ''}",  # type: ignore
        f"TIN: {customer.tin}" if customer.tin else '',  # type: ignore
        customer.phone or '',
    ]
    info_table = Table(
        [[Paragraph('<b>FROM</b>', label_style), Paragraph('<b>BILL TO</b>', label_style)],
         [_addr(biz_lines), _addr(cus_lines)]],
        colWidths=[3.5*inch, 3.5*inch]
    )
    info_table.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 0), (-1, 0),  4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # Meta bar
    due_str   = invoice.due_date.strftime('%d %b %Y')   if invoice.due_date   else '—'   # type: ignore
    issue_str = invoice.issue_date.strftime('%d %b %Y') if invoice.issue_date else '—'   # type: ignore
    try:    status_val = invoice.status.value
    except: status_val = str(invoice.status)

    meta_table = Table([[
        Paragraph(f'<font color="white" size="7">ISSUE DATE</font><br/><font color="white" size="9"><b>{issue_str}</b></font>', styles['Normal']),
        Paragraph(f'<font color="white" size="7">DUE DATE</font><br/><font color="white" size="9"><b>{due_str}</b></font>', styles['Normal']),
        Paragraph(f'<font color="white" size="7">STATUS</font><br/><font color="white" size="9"><b>{status_val}</b></font>', styles['Normal']),
        Paragraph(f'<font color="white" size="7">PAYMENT TERMS</font><br/><font color="white" size="9"><b>{invoice.payment_terms or "—"}</b></font>', styles['Normal']),
    ]], colWidths=[1.75*inch]*4)
    meta_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), col_secondary),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING',   (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 16))

    # Line items
    hdr_style = ParagraphStyle('TH', parent=styles['Normal'], fontSize=7.5, textColor=colors.white, fontName=FONT_BOLD)
    def _p(text, st=normal_style): return Paragraph(str(text), st)

    items_data = [[_p('DESCRIPTION', hdr_style), _p('QTY', hdr_style), _p('UNIT PRICE', hdr_style), _p('TAX', hdr_style), _p('AMOUNT', hdr_style)]]
    for item in invoice.items:
        items_data.append([
            _p(item.description or 'Item'),
            _p(str(item.quantity)),
            _p(_pdf_money(float(item.unit_price))),
            _p(f'{item.tax_rate or 0}%'),
            _p(_pdf_money(float(item.line_total))),
        ])
    items_table = Table(items_data, colWidths=[2.6*inch, 0.5*inch, 1.3*inch, 0.6*inch, 1.2*inch], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  col_primary),
        ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN',         (0, 0), (0, -1),  'LEFT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [col_paper, col_row_alt]),
        ('LINEBELOW',     (0, 1), (-1, -2), 0.3, col_border),
        ('FONTSIZE',      (0, 1), (-1, -1), 9),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 12))

    # Totals
    def _total_row(label, amount, bold=False, highlight=False):
        ls = ParagraphStyle('tl', parent=styles['Normal'], fontSize=9,
                            fontName=FONT_BOLD if bold else FONT_NORMAL,
                            textColor=col_primary if highlight else col_ink, alignment=TA_RIGHT)
        vs = ParagraphStyle('tv', parent=styles['Normal'], fontSize=9,
                            fontName=FONT_BOLD if bold else FONT_NORMAL,
                            textColor=col_primary if highlight else col_ink, alignment=TA_RIGHT)
        return ['', '', '', Paragraph(label, ls), Paragraph(amount, vs)]

    totals_data = [_total_row('Subtotal', _pdf_money(float(invoice.subtotal)))]  # type: ignore
    if float(invoice.discount_amount or 0) > 0:  # type: ignore
        totals_data.append(_total_row('Discount', f'-{_pdf_money(float(invoice.discount_amount))}'))  # type: ignore
    totals_data.append(_total_row('VAT', _pdf_money(float(invoice.tax_amount))))  # type: ignore
    totals_data.append(_total_row('TOTAL DUE', _pdf_money(float(invoice.total_amount)), bold=True, highlight=True))  # type: ignore
    if float(invoice.paid_amount or 0) > 0:  # type: ignore
        totals_data.append(_total_row('Paid', _pdf_money(float(invoice.paid_amount))))  # type: ignore
        totals_data.append(_total_row('Balance Due', _pdf_money(float(invoice.outstanding_amount)), bold=True, highlight=True))  # type: ignore

    total_row_idx = next(i for i, r in enumerate(totals_data) if 'TOTAL DUE' in r[3].text)
    totals_table = Table(totals_data, colWidths=[2.5*inch, 0.8*inch, 0.8*inch, 1.8*inch, 1.1*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN',        (3, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ('LINEABOVE',    (3, total_row_idx), (-1, total_row_idx), 1.5, col_primary),
        ('LINEBELOW',    (3, total_row_idx), (-1, total_row_idx), 1.5, col_primary),
    ]))
    elements.append(totals_table)

    if invoice.notes:  # type: ignore
        elements.append(Spacer(1, 16))
        elements.append(Paragraph('<b>Notes</b>', heading_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(invoice.notes, normal_style))  # type: ignore

    elements.append(Spacer(1, 28))
    elements.append(Paragraph(
        f'<font color="{primary_hex}">\u2014 </font>'
        f'Thank you for your business! '
        f'Questions? Contact {business.email or business.phone or "us"}',  # type: ignore
        ParagraphStyle('Foot', parent=styles['Normal'], fontSize=8, textColor=col_dim, alignment=TA_CENTER, fontName=FONT_NORMAL)
    ))

    doc.build(elements)
    try:
        if tmp_path:
            os.unlink(tmp_path)
    except Exception:
        pass
    buffer.seek(0)
    return buffer



# ============================================================================
# INVOICE CRUD ENDPOINTS (keeping existing code)
# ============================================================================




@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[InvoiceStatus] = Query(None),
    customer_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of invoices"""
    business = await get_user_business(db, current_user.id) # type: ignore

    filters = [Invoice.business_id == business.id]
    if status:
        filters.append(Invoice.status == status) # type: ignore
    if customer_id:
        filters.append(Invoice.customer_id == customer_id)
    if from_date:
        filters.append(Invoice.issue_date >= from_date)
    if to_date:
        filters.append(Invoice.issue_date <= to_date)

    total = (await db.execute(
        select(func.count()).select_from(Invoice).where(*filters)
    )).scalar_one()

    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size

    invoices = (await db.execute(
        select(Invoice)
        .where(*filters)
        .order_by(Invoice.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )).scalars().all()
    
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
    db: AsyncSession = Depends(get_db)
):
    """Get a specific invoice by ID"""
    business = await get_user_business(db, current_user.id) # type: ignore
    
    invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
    
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    invoice_data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an invoice (only DRAFT invoices can be fully updated)"""
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        
        invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
        
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
        
        await db.commit()
        await db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update invoice"
        )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a draft invoice"""
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        
        invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
        
        if invoice.status != InvoiceStatus.DRAFT: # type: ignore
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft invoices can be deleted. Use cancel endpoint for sent invoices."
            )
        
        await db.delete(invoice)
        await db.commit()
        
        return None
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete invoice"
        )


@router.post("/{invoice_id}/finalize", response_model=InvoiceResponse)
async def finalize_invoice(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Finalize a draft invoice (mark as SENT)"""
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        
        invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
        
        if invoice.status != InvoiceStatus.DRAFT: # type: ignore
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft invoices can be finalized"
            )
        
        invoice.mark_as_sent()
        await db.commit()
        await db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize invoice"
        )


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    cancel_data: InvoiceCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel an invoice"""
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        
        invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
        
        
        
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
        await db.commit()
        await db.refresh(invoice)
        
        return invoice
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel invoice"
        )


@router.get("/stats/overview", response_model=InvoiceStatistics)
async def get_invoice_statistics(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get invoice statistics"""
    business = await get_user_business(db, current_user.id)  # type: ignore

    stmt = select(
        func.count().label("total_invoices"),
        func.count(case((Invoice.status == InvoiceStatus.DRAFT,      1))).label("draft_invoices"), # type: ignore
        func.count(case((Invoice.status == InvoiceStatus.SENT,       1))).label("sent_invoices"), # type: ignore
        func.count(case((Invoice.status == InvoiceStatus.PAID,       1))).label("paid_invoices"), # type: ignore
        func.count(case((Invoice.status == InvoiceStatus.OVERDUE,    1))).label("overdue_invoices"), # type: ignore
        func.count(case((Invoice.status == InvoiceStatus.CANCELLED,  1))).label("cancelled_invoices"), # type: ignore
        func.coalesce(
            func.sum(case((Invoice.status != InvoiceStatus.CANCELLED, Invoice.total_amount))), # type: ignore
            0
        ).label("total_invoiced"),
        func.coalesce(
            func.sum(case((Invoice.status != InvoiceStatus.CANCELLED, Invoice.paid_amount))), # type: ignore
            0
        ).label("total_paid"),
    ).select_from(Invoice).where(Invoice.business_id == business.id)

    if from_date:
        stmt = stmt.where(Invoice.issue_date >= from_date)
    if to_date:
        stmt = stmt.where(Invoice.issue_date <= to_date)

    row = (await db.execute(stmt)).one()

    # Average days to payment — separate query, only for PAID invoices
    avg_stmt = select(
        func.avg(
            func.extract("epoch", Invoice.paid_at) - # type: ignore
            func.extract("epoch", func.cast(Invoice.issue_date, DateTime))
        ) / 86400
    ).where(
        Invoice.business_id == business.id,
        Invoice.status == InvoiceStatus.PAID, # type: ignore
        Invoice.paid_at.isnot(None) # type: ignore
    )
    avg_days = (await db.execute(avg_stmt)).scalar()

    total_invoiced = float(row.total_invoiced)
    total_paid     = float(row.total_paid)

    return {
        "total_invoices":          row.total_invoices,
        "draft_invoices":          row.draft_invoices,
        "sent_invoices":           row.sent_invoices,
        "paid_invoices":           row.paid_invoices,
        "overdue_invoices":        row.overdue_invoices,
        "cancelled_invoices":      row.cancelled_invoices,
        "total_invoiced":          total_invoiced,
        "total_paid":              total_paid,
        "total_outstanding":       total_invoiced - total_paid,
        "average_invoice_value":   total_invoiced / row.total_invoices if row.total_invoices else 0,
        "average_days_to_payment": float(avg_days) if avg_days is not None else None,
    }

# ============================================================================
# PDF GENERATION ENDPOINT (NEW!)
# ============================================================================

@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
        business = await get_user_business(db, current_user.id) # type: ignore
        
        # Get invoice with relationships
        invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore
        
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
            detail="Failed to generate PDF"
        )

class SendInvoiceRequest(BaseModel):
    """Request body for POST /invoices/{id}/send"""
    message: Optional[str] = None
    cc:      Optional[str] = None


def _fmt_ngn(amount) -> str:
    try:
        return f"\u20a6{float(amount):,.0f}"
    except (TypeError, ValueError):
        return "\u20a60"


def _fmt_date_str(d) -> str:
    if d is None:
        return "\u2014"
    if hasattr(d, 'strftime'):
        return d.strftime("%d %B %Y")
    return str(d)


@router.post("/{invoice_id}/send", status_code=status.HTTP_200_OK)
async def send_invoice(
    invoice_id: uuid.UUID,
    body: SendInvoiceRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Email an invoice to the customer with PDF attached."""
    business = await get_user_business(db, current_user.id) # type: ignore

    invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore

    if invoice.status == InvoiceStatus.DRAFT: # type: ignore
        raise HTTPException(status_code=400, detail="Cannot email a draft invoice. Finalise it first.")

    if invoice.status == InvoiceStatus.CANCELLED: # type: ignore
        raise HTTPException(status_code=400, detail="Cannot email a cancelled invoice.")

    customer = invoice.customer # type: ignore 
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    customer_email = str(customer.email or "")
    customer_name  = str(customer.name  or "")

    if not customer_email:
        raise HTTPException(status_code=422, detail=f"Customer '{customer_name}' has no email address.")

    try:
        pdf_buffer = generate_invoice_pdf(invoice, business, customer)
        pdf_bytes  = pdf_buffer.getvalue()
    except Exception as e:
        logger.warning("PDF generation failed, sending without attachment: %s", e, exc_info=True)
        pdf_bytes = None


    
    invoice.email_sent = True # type: ignore
    invoice.email_sent_at = datetime.now(timezone.utc) # type: ignore

    await db.commit()
    await db.refresh(invoice)
    
    background_tasks.add_task(
        send_invoice_email,
        to_email=customer_email,
        customer_name=customer_name,
        invoice_number=str(invoice.invoice_number or ""),
        invoice_date=_fmt_date_str(invoice.issue_date),
        due_date=_fmt_date_str(invoice.due_date),
        total_amount=_fmt_ngn(invoice.total_amount),
        business_name=str(business.business_name or ""),
        pdf_bytes=pdf_bytes,
        custom_message=body.message or None,
        cc_email=body.cc or None,
        
        
        
    )

    logger.info("Invoice %s queued for email to %s", invoice.invoice_number, customer_email)

    return {
        "message":      f"Invoice {invoice.invoice_number} emailed to {customer_email}",
        "email_sent":    True,
        "email_sent_at": invoice.email_sent_at,
        "recipient":     customer_email,
        "pdf_attached":  pdf_bytes is not None,
    }


@router.get("/{invoice_id}/email-status", status_code=status.HTTP_200_OK)
async def get_email_status(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns whether and when this invoice was last emailed."""
    business = await get_user_business(db, current_user.id) # type: ignore

    invoice = await get_invoice_by_id(db, invoice_id, business.id) # type: ignore

   

    return {
        "invoice_id":    str(invoice.id),
        "email_sent":    bool(invoice.email_sent),
        "email_sent_at": invoice.email_sent_at,
    }
    
    
    
@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    try:
        business = await get_user_business(db, current_user.id)  # type: ignore
        customer = await verify_customer_belongs_to_business(
            db, invoice_data.customer_id, business.id  # type: ignore
        )

        invoice_number = await generate_unique_invoice_number(db, business)
        invoice = Invoice(
            business_id=business.id,
            customer_id=customer.id,
            invoice_number=invoice_number,
            issue_date=invoice_data.issue_date,
            due_date=invoice_data.due_date,
            discount_amount=invoice_data.discount_amount,
            payment_terms=(
                invoice_data.payment_terms
                or f"Payment due within {customer.payment_terms_days} days"
            ),
            notes=invoice_data.notes,
            internal_notes=invoice_data.internal_notes,
            status=InvoiceStatus.DRAFT,
        )
        db.add(invoice)
        try:
            await db.flush()
        except IntegrityError as e:
            await db.rollback()
            if "ix_invoices_invoice_number" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Invoice number {invoice_number} already exists. Please try again.",
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
                sort_order=item_data.sort_order if item_data.sort_order > 0 else idx,
            )
            item.calculate_totals()
            db.add(item)
            if item_data.product_id:
                product_result = await db.execute(
                    select(Product).where(Product.id == item_data.product_id)
                )
                product = product_result.scalar_one_or_none()
                if product:
                    product.increment_usage()
                    if product.track_inventory:  # type: ignore
                        if product.quantity_in_stock < item_data.quantity:  # type: ignore
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=(
                                    f"Insufficient stock for '{product.name}'. "
                                    f"Available: {product.quantity_in_stock}, "
                                    f"requested: {item_data.quantity}"
                                ),
                            )

                    
                    
                    try:
                        await db.execute(
                            text("""
                                 INSERT INTO stock_movements
                                 (id, business_id, product_id, invoice_id,
                                 movement_type, quantity, unit_cost, note, movement_date)
                                 VALUES
                                 (gen_random_uuid(), :biz_id, :product_id, :invoice_id,
                                 'OUT', :qty, :cost, :note, :dt)
                                 """),
                            {
                                "biz_id": str(invoice.business_id),
                                "product_id": str(product.id),
                                "invoice_id": str(invoice.id),
                                "qty": float(item_data.quantity),
                                "cost": float(product.cost_price) if product.cost_price else None,  # type: ignore
                                "note": "Sale - " + invoice.invoice_number,
                                "dt": invoice.issue_date or date.today(),
                            },
                        )
                        result = await db.execute(
                            text("""
                            SELECT
                            COALESCE(SUM(CASE WHEN movement_type='IN'  THEN quantity ELSE 0 END), 0)
                            - COALESCE(SUM(CASE WHEN movement_type='OUT' THEN quantity ELSE 0 END), 0)
                            FROM stock_movements
                            WHERE product_id = :pid
                            """),
                            {"pid": str(product.id)},
                        )
                        new_qty = result.scalar()
                        product.quantity_in_stock = max(float(new_qty or 0), 0)  # type: ignore

                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(
                            "Stock movement failed for product %s on invoice %s: %s",
                            product.id,
                            invoice.invoice_number,
                            e,
                            exc_info=True,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to record stock movement for product '{product.name}'",
                        )

                    
                            
    
    
        await db.flush()
        await db.refresh(invoice)
        invoice.calculate_totals()
        await db.commit()
        await db.refresh(invoice)
        return invoice

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.error("Error creating invoice: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invoice"
        )

