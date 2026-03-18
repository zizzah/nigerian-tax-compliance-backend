"""
Paystack Payment Endpoints
Location: app/api/v1/endpoints/paystack.py

Endpoints:
  POST /paystack/links/{invoice_id}   — generate or fetch payment link for an invoice (auth required)
  GET  /paystack/pay/{token}          — public: get invoice data for payment page
  POST /paystack/pay/{token}/initiate — public: create Paystack transaction → returns payment URL
  POST /paystack/webhook              — Paystack callback: auto-mark invoice PAID
  GET  /paystack/verify/{reference}   — verify a transaction manually

Register in main.py:
  from app.api.v1.endpoints import paystack
  app.include_router(paystack.router, prefix=settings.API_V1_PREFIX)
"""
import uuid
import hmac
import hashlib
import logging
import secrets
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment_link import PaymentLink
from app.models.payment import Payment

logger = logging.getLogger(__name__)

# ─── Pydantic response schemas ────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402


class PaymentLinkResponse(BaseModel):
    token:       str
    payment_url: str
    created_at:  datetime
    is_new:      bool


class InitiateResponse(BaseModel):
    payment_url: str
    reference:   str
    access_code: str


class WebhookResponse(BaseModel):
    received: bool


# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/paystack", tags=["Paystack"])

PAYSTACK_BASE = "https://api.paystack.co"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_business_secret_key(business: Business) -> str:
    """Get Paystack secret key for a specific business."""
    key = getattr(business, "paystack_secret_key", None)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paystack is not configured for your business. "
                   "Go to Settings → Payments and add your Paystack API keys.",
        )
    return str(key)


def _get_business_public_key(business: Business) -> Optional[str]:
    """Get Paystack public key for a specific business."""
    key = getattr(business, "paystack_public_key", None)
    return str(key) if key else None


def _get_business_for_user(db: Session, user: User) -> Business:
    business = db.query(Business).filter(Business.user_id == user.id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return business


def _fmt_ngn(amount) -> str:
    try:
        return f"₦{float(amount):,.0f}"
    except (TypeError, ValueError):
        return "₦0"


def _kobo(amount) -> int:
    """Convert Naira to kobo (Paystack uses kobo)."""
    try:
        return int(float(amount) * 100)
    except (TypeError, ValueError):
        return 0


# ─── POST /paystack/links/{invoice_id} — generate payment link ────────────────

@router.post("/links/{invoice_id}", response_model=PaymentLinkResponse)
def create_payment_link(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate (or retrieve existing) payment link for an invoice.
    Returns the public payment URL to send to the customer.
    """
    business = _get_business_for_user(db, current_user)

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.business_id == business.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create payment link for a {invoice.status.value} invoice.",
        )

    if invoice.status == InvoiceStatus.DRAFT:  # type: ignore
        raise HTTPException(
            status_code=400,
            detail="Finalise the invoice before generating a payment link.",
        )

    # Return existing active link if present
    existing = db.query(PaymentLink).filter(
        PaymentLink.invoice_id == invoice.id,
        PaymentLink.is_active == True,  # noqa: E712
    ).first()

    if existing:
        base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        return {
            "token":       existing.token,
            "payment_url": f"{base_url}/pay/{existing.token}",
            "created_at":  existing.created_at,
            "is_new":      False,
        }

    # Create new link
    token = secrets.token_urlsafe(32)
    link = PaymentLink(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        business_id=business.id,
        token=token,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    return {
        "token":       token,
        "payment_url": f"{base_url}/pay/{token}",
        "created_at":  link.created_at,
        "is_new":      True,
    }


# ─── GET /paystack/pay/{token} — public invoice data ─────────────────────────

@router.get("/pay/{token}")
def get_payment_page(token: str, db: Session = Depends(get_db)):
    """
    Public endpoint — no auth required.
    Returns invoice + business data needed to render the payment page.
    """
    link = db.query(PaymentLink).filter(
        PaymentLink.token == token,
        PaymentLink.is_active == True,  # noqa: E712
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Payment link not found or has expired.")

    invoice = db.query(Invoice).filter(Invoice.id == link.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    if invoice.status == InvoiceStatus.PAID:  # type: ignore
        return {"status": "already_paid", "invoice_number": invoice.invoice_number}

    if invoice.status == InvoiceStatus.CANCELLED:  # type: ignore
        return {"status": "cancelled", "invoice_number": invoice.invoice_number}

    business = db.query(Business).filter(Business.id == link.business_id).first()
    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first()

    public_key = _get_business_public_key(business) if business else None

    return {
        "status":           "pending",
        "token":            token,
        "paystack_key":     public_key,
        "invoice": {
            "id":             str(invoice.id),
            "number":         invoice.invoice_number,
            "issue_date":     str(invoice.issue_date),
            "due_date":       str(invoice.due_date),
            "total_amount":   str(invoice.total_amount),
            "paid_amount":    str(invoice.paid_amount),
            "outstanding":    str(invoice.outstanding_amount),
            "status":         invoice.status.value,  # type: ignore
            "notes":          invoice.notes,
            "items": [
                {
                    "description": item.description,
                    "quantity":    str(item.quantity),
                    "unit_price":  str(item.unit_price),
                    "line_total":  str(item.line_total),
                    "tax_rate":    str(item.tax_rate),
                }
                for item in (invoice.items or [])
            ],
        },
        "business": {
            "name":          business.business_name if business else "",
            "email":         str(business.email or "") if business else "",
            "phone":         str(business.phone or "") if business else "",
            "address":       str(business.address or "") if business else "",
            "city":          str(business.city or "") if business else "",
            "primary_color": str(business.primary_color or "#c8952a") if business else "#c8952a",
            "logo_url":      str(business.logo_url or "") if business else "",
        },
        "customer": {
            "name":  customer.name if customer else "",
            "email": str(customer.email or "") if customer else "",
        },
    }


# ─── POST /paystack/pay/{token}/initiate — start Paystack transaction ─────────

@router.post("/pay/{token}/initiate", response_model=InitiateResponse)
def initiate_payment(token: str, db: Session = Depends(get_db)):
    """
    Public endpoint — no auth required.
    Calls Paystack Initialize Transaction API and returns the payment URL.
    Uses the business's own Paystack secret key.
    """
    # Load link and business first to get their specific Paystack keys
    _link_check = db.query(PaymentLink).filter(
        PaymentLink.token == token,
        PaymentLink.is_active == True,  # noqa: E712
    ).first()
    if not _link_check:
        raise HTTPException(status_code=404, detail="Payment link not found.")
    _biz_check = db.query(Business).filter(Business.id == _link_check.business_id).first()
    if not _biz_check:
        raise HTTPException(status_code=404, detail="Business not found.")
    secret_key = _get_business_secret_key(_biz_check)

    link = db.query(PaymentLink).filter(
        PaymentLink.token == token,
        PaymentLink.is_active == True,  # noqa: E712
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Payment link not found.")

    invoice = db.query(Invoice).filter(Invoice.id == link.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    if invoice.status == InvoiceStatus.PAID:  # type: ignore
        raise HTTPException(status_code=400, detail="Invoice is already paid.")

    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first()
    business = db.query(Business).filter(Business.id == link.business_id).first()

    customer_email = str(customer.email) if customer and customer.email else ""  # type: ignore
    if not customer_email:
        raise HTTPException(
            status_code=422,
            detail="Customer has no email address — cannot process Paystack payment.",
        )

    amount_kobo = _kobo(invoice.outstanding_amount)
    ref = f"INV-{invoice.invoice_number}-{secrets.token_hex(6).upper()}"

    # Save reference on the link
    link.paystack_ref = ref # type: ignore
    db.commit()

    base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    callback_url = f"{base_url}/pay/{token}/complete"

    payload = {
        "email":        customer_email,
        "amount":       amount_kobo,
        "reference":    ref,
        "callback_url": callback_url,
        "metadata": {
            "invoice_id":     str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "business_name":  str(business.business_name) if business else "",
            "payment_token":  token,
        },
    }

    try:
        resp = httpx.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=payload,
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Paystack init failed: {e.response.text}")
        raise HTTPException(status_code=502, detail="Paystack payment initiation failed.")
    except Exception as e:
        logger.error(f"Paystack request error: {e}")
        raise HTTPException(status_code=502, detail="Could not reach Paystack. Try again.")

    if not data.get("status"):
        raise HTTPException(status_code=502, detail=data.get("message", "Paystack error"))

    return {
        "payment_url":  data["data"]["authorization_url"],
        "reference":    ref,
        "access_code":  data["data"]["access_code"],
    }


# ─── POST /paystack/webhook — Paystack payment notification ───────────────────

@router.post("/webhook", response_model=WebhookResponse)
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Paystack calls this endpoint when a payment is completed.
    Verifies the HMAC signature, then marks the invoice as PAID.

    Register this URL in your Paystack dashboard:
      https://your-api.com/api/v1/paystack/webhook
    """
    import json
    body = await request.body()
    event = json.loads(body)
    logger.info(f"Paystack webhook event: {event.get('event')}")

    # Look up the business from the payment token in metadata
    # so we can use their specific Paystack secret key for signature verification
    data_meta  = event.get("data", {}).get("metadata", {})
    pay_token  = data_meta.get("payment_token", "")
    secret_key = ""

    if pay_token:
        link = db.query(PaymentLink).filter(PaymentLink.token == pay_token).first()
        if link:
            biz = db.query(Business).filter(Business.id == link.business_id).first()
            if biz:
                secret_key = str(getattr(biz, "paystack_secret_key", "") or "")

    # Fallback to platform-level key if business key not found
    if not secret_key:
        secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")

    # Verify Paystack HMAC signature
    sig = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(
        secret_key.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected):
        logger.warning("Paystack webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event.get("event") != "charge.success":
        return {"received": True}

    data      = event.get("data", {})
    reference = data.get("reference", "")
    amount    = data.get("amount", 0)          # in kobo
    status_ps = data.get("status", "")
    metadata  = data.get("metadata", {})
    invoice_id_str = metadata.get("invoice_id", "")

    if status_ps != "success":
        return {"received": True}

    # Find invoice
    try:
        invoice_uuid = uuid.UUID(invoice_id_str)
    except (ValueError, TypeError):
        logger.error(f"Webhook: bad invoice_id in metadata: {invoice_id_str}")
        return {"received": True}

    invoice = db.query(Invoice).filter(Invoice.id == invoice_uuid).first()
    if not invoice:
        logger.error(f"Webhook: invoice {invoice_id_str} not found")
        return {"received": True}

    if invoice.status == InvoiceStatus.PAID:  # type: ignore
        return {"received": True}   # Already processed

    # Convert kobo → naira
    paid_naira = amount / 100

    # Record payment
    payment = Payment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        business_id=invoice.business_id,
        customer_id=invoice.customer_id,
        amount=paid_naira,
        payment_method="CARD",
        payment_date=datetime.utcnow().date(),
        reference_number=reference,
        transaction_id=reference,
        notes=f"Paystack online card payment — ref: {reference}",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(payment)

    # Update invoice amounts
    new_paid = float(invoice.paid_amount or 0) + paid_naira # type: ignore
    invoice.paid_amount = new_paid  # type: ignore
    outstanding = float(invoice.total_amount or 0) - new_paid # type: ignore
    invoice.outstanding_amount = max(0, outstanding)  # type: ignore

    if outstanding <= 0.01:   # fully paid (allow 1 kobo rounding)
        invoice.mark_as_paid()  # type: ignore

    # Deactivate payment link
    link = db.query(PaymentLink).filter(
        PaymentLink.invoice_id == invoice.id
    ).first()
    if link:
        link.is_active = False # type: ignore

    db.commit()
    logger.info(f"Webhook: invoice {invoice.invoice_number} marked PAID via Paystack ref {reference}")

    return {"received": True}


# ─── GET /paystack/verify/{reference} — verify and record payment ────────────
# Public endpoint — called by frontend after Paystack popup closes successfully.
# Works as a fallback when webhook can't reach localhost during development.

@router.get("/verify/{reference}")
def verify_payment(
    reference: str,
    db: Session = Depends(get_db),
):
    """
    Verify a Paystack transaction and mark the invoice as PAID if successful.

    - Public endpoint — no auth required (token is in payment link metadata).
    - Called by the frontend immediately after Paystack popup closes.
    - Acts as webhook fallback for local development where Paystack can't
      reach localhost. In production the webhook handles this automatically,
      but verify runs too and is safely idempotent (skips if already PAID).
    """
    # Look up the payment link by reference to get the business + secret key
    link = db.query(PaymentLink).filter(
        PaymentLink.paystack_ref == reference,
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Payment reference not found.")

    business = db.query(Business).filter(Business.id == link.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")

    secret_key = _get_business_secret_key(business)

    # Verify with Paystack
    try:
        resp = httpx.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Paystack verify error: {e}")
        raise HTTPException(status_code=502, detail="Could not verify with Paystack.")

    ps_data   = data.get("data", {})
    ps_status = ps_data.get("status", "")
    amount    = ps_data.get("amount", 0)  # kobo

    if ps_status != "success":
        return {"verified": False, "status": ps_status, "message": "Payment not successful"}

    # Load invoice
    invoice = db.query(Invoice).filter(Invoice.id == link.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    # Idempotent — skip if already paid
    if invoice.status == InvoiceStatus.PAID:  # type: ignore
        return {
            "verified":       True,
            "already_paid":   True,
            "invoice_number": invoice.invoice_number,
            "status":         "paid",
        }

    # Record the payment
    paid_naira = amount / 100
    payment = Payment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        business_id=invoice.business_id,
        customer_id=invoice.customer_id,
        amount=paid_naira,
        payment_method="CARD",
        payment_date=datetime.utcnow().date(),
        reference_number=reference,
        transaction_id=reference,
        notes=f"Paystack online card payment — ref: {reference}",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(payment)

    # Update invoice paid/outstanding amounts
    new_paid    = float(invoice.paid_amount or 0) + paid_naira   # type: ignore
    outstanding = float(invoice.total_amount or 0) - new_paid   # type: ignore
    invoice.paid_amount        = new_paid        # type: ignore
    invoice.outstanding_amount = max(0, outstanding)  # type: ignore

    if outstanding <= 0.01:
        invoice.mark_as_paid()  # type: ignore

    # Deactivate payment link
    link.is_active = False # type: ignore
    db.commit()

    logger.info(
        f"Verify: invoice {invoice.invoice_number} marked PAID "
        f"via Paystack ref {reference}"
    )

    return {
        "verified":       True,
        "already_paid":   False,
        "invoice_number": invoice.invoice_number,
        "amount_paid":    paid_naira,
        "status":         "paid",
    }