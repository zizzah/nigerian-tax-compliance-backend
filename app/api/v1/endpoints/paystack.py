"""
Paystack Payment Endpoints (Async)
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment_link import PaymentLink
from app.models.payment import Payment

from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paystack", tags=["Paystack"])

PAYSTACK_BASE = "https://api.paystack.co"


# ── Schemas ─────────────────────────────────────

class PaymentLinkResponse(BaseModel):
    token: str
    payment_url: str
    created_at: datetime
    is_new: bool


class InitiateResponse(BaseModel):
    payment_url: str
    reference: str
    access_code: str


class WebhookResponse(BaseModel):
    received: bool


# ── Helpers ─────────────────────────────────────

async def _get_business_for_user(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalars().first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz


def _get_business_secret_key(business: Business) -> str:
    key = getattr(business, "paystack_secret_key", None)
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Paystack not configured for this business",
        )
    return str(key)


def _kobo(amount) -> int:
    try:
        return int(float(amount) * 100)
    except:
        return 0


# ────────────────────────────────────────────────
# CREATE PAYMENT LINK
# ────────────────────────────────────────────────

@router.post("/links/{invoice_id}", response_model=PaymentLinkResponse)
async def create_payment_link(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = await _get_business_for_user(db, current_user)

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.business_id == business.id,
        )
    )
    invoice = result.scalars().first()

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):
        raise HTTPException(400, "Invalid invoice status")

    # existing link
    existing = (
        await db.execute(
            select(PaymentLink).where(
                PaymentLink.invoice_id == invoice.id,
                PaymentLink.is_active == True,
            )
        )
    ).scalars().first()

    base_url = getattr(settings, "FRONTEND_URL", "")

    if existing:
        return {
            "token": existing.token,
            "payment_url": f"{base_url}/pay/{existing.token}",
            "created_at": existing.created_at,
            "is_new": False,
        }

    # create
    token = secrets.token_urlsafe(32)

    async with db.begin():
        link = PaymentLink(
            id=uuid.uuid4(),
            invoice_id=invoice.id,
            business_id=business.id,
            token=token,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(link)

    return {
        "token": token,
        "payment_url": f"{base_url}/pay/{token}",
        "created_at": link.created_at,
        "is_new": True,
    }


# ────────────────────────────────────────────────
# INITIATE PAYMENT (ASYNC HTTP)
# ────────────────────────────────────────────────

@router.post("/pay/{token}/initiate", response_model=InitiateResponse)
async def initiate_payment(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentLink).where(
            PaymentLink.token == token,
            PaymentLink.is_active == True,
        )
    )
    link = result.scalars().first()

    if not link:
        raise HTTPException(404, "Link not found")

    invoice = (
        await db.execute(select(Invoice).where(Invoice.id == link.invoice_id))
    ).scalars().first()

    business = (
        await db.execute(select(Business).where(Business.id == link.business_id))
    ).scalars().first()

    customer = (
        await db.execute(select(Customer).where(Customer.id == invoice.customer_id)) # type: ignore
    ).scalars().first()

    secret_key = _get_business_secret_key(business) # type: ignore

    ref = f"INV-{invoice.invoice_number}-{secrets.token_hex(6).upper()}" # type: ignore

    async with db.begin():
        link.paystack_ref = ref # type: ignore

    payload = {
        "email": customer.email, # type: ignore
        "amount": _kobo(invoice.outstanding_amount), # type: ignore
        "reference": ref,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        data = resp.json()

    if not data.get("status"):
        raise HTTPException(502, "Paystack error")

    return {
        "payment_url": data["data"]["authorization_url"],
        "reference": ref,
        "access_code": data["data"]["access_code"],
    }


# ────────────────────────────────────────────────
# WEBHOOK (ASYNC + SAFE)
# ────────────────────────────────────────────────

@router.post("/webhook", response_model=WebhookResponse)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    sig = request.headers.get("x-paystack-signature", "")

    # NOTE: use global key fallback
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", "")

    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Invalid signature")

    event = await request.json()

    if event.get("event") != "charge.success":
        return {"received": True}

    data = event["data"]
    reference = data["reference"]
    amount = data["amount"] / 100

    # find link
    link = (
        await db.execute(
            select(PaymentLink).where(PaymentLink.paystack_ref == reference)
        )
    ).scalars().first()

    if not link:
        return {"received": True}

    invoice = (
        await db.execute(select(Invoice).where(Invoice.id == link.invoice_id))
    ).scalars().first()

    if not invoice or invoice.status == InvoiceStatus.PAID: # type: ignore
        return {"received": True}

    async with db.begin():
        payment = Payment(
            id=uuid.uuid4(),
            invoice_id=invoice.id,
            business_id=invoice.business_id,
            customer_id=invoice.customer_id,
            amount=amount,
            reference_number=reference,
            transaction_id=reference,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(payment)

        invoice.paid_amount = (invoice.paid_amount or 0) + amount
        invoice.outstanding_amount = max( # type: ignore
            0,
            (invoice.total_amount or 0) - invoice.paid_amount,
        )

        if invoice.outstanding_amount <= 0.01: # type: ignore
            invoice.mark_as_paid()

        link.is_active = False # type: ignore

    return {"received": True}


# ────────────────────────────────────────────────
# VERIFY (ASYNC HTTP)
# ────────────────────────────────────────────────

@router.get("/verify/{reference}")
async def verify_payment(
    reference: str,
    db: AsyncSession = Depends(get_db),
):
    link = (
        await db.execute(
            select(PaymentLink).where(PaymentLink.paystack_ref == reference)
        )
    ).scalars().first()

    if not link:
        raise HTTPException(404, "Reference not found")

    business = (
        await db.execute(select(Business).where(Business.id == link.business_id))
    ).scalars().first()

    secret = _get_business_secret_key(business) # type: ignore

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret}"},
        )
        data = resp.json()

    if data.get("data", {}).get("status") != "success":
        return {"verified": False}

    return {"verified": True}