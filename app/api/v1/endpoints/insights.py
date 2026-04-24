"""
AI Insights API Endpoints (ASYNC SAFE)
"""

import uuid
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.ai_insight import AIInsight
from app.services.ai.insights_engine import InsightsEngine

router = APIRouter(prefix="/insights", tags=["AI Insights"])
logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────

async def _get_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalar_one_or_none()

    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")

    return biz


async def _maybe_get_business(db: AsyncSession, user: User) -> Business | None:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    return result.scalar_one_or_none()


def _serialize_insight(insight: AIInsight) -> dict:
    return {
        "id": str(insight.id),
        "insight_type": insight.insight_type,
        "severity": insight.severity,
        "title": insight.title,
        "body": insight.body,
        "action_label": insight.action_label,
        "action_url": insight.action_url,
        "is_dismissed": insight.is_dismissed,
        "created_at": insight.created_at.isoformat() if insight.created_at else None, # type: ignore
    }


# ── GET /insights/ ──────────────────────────────────────

@router.get("/")
async def get_insights(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _maybe_get_business(db, current_user)
    if not biz:
        return {"insights": [], "cached": True}

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.business_id == biz.id,
            AIInsight.is_dismissed == False,
            AIInsight.created_at >= today_start,
        )
        .order_by(AIInsight.created_at.desc())
    )
    existing = result.scalars().all()

    if existing and not refresh:
        return {
            "insights": [_serialize_insight(i) for i in existing],
            "cached": True
        }

    # ⚠️ KEEP SYNC (do NOT change unless engine is async)
    engine = InsightsEngine()
    new_insights = engine.generate_insights(db, biz) # type: ignore

    return {
        "insights": [_serialize_insight(i) for i in new_insights], # type: ignore
        "cached": False
    }


# ── POST /insights/{id}/dismiss ─────────────────────────

@router.post("/{insight_id}/dismiss")
async def dismiss_insight(
    insight_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)

    result = await db.execute(
        select(AIInsight).where(
            AIInsight.id == insight_id,
            AIInsight.business_id == biz.id,
        )
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    insight.is_dismissed = True  # type: ignore
    insight.dismissed_at = datetime.now(timezone.utc)# type: ignore

    await db.commit()

    return {"success": True}


# ── GET /payment-prediction/{invoice_id} ────────────────

@router.get("/payment-prediction/{invoice_id}")
async def predict_payment_date(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.invoice import Invoice, InvoiceStatus

    biz = await _get_business(db, current_user)

    try:
        inv_uuid = uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid invoice ID")

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == inv_uuid,
            Invoice.business_id == biz.id,
        )
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Historical invoices
    result = await db.execute(
        select(Invoice)
        .where(
            Invoice.business_id == biz.id,
            Invoice.customer_id == invoice.customer_id,
            Invoice.status == InvoiceStatus.PAID, # type: ignore
            Invoice.paid_at.isnot(None), # type: ignore
        )
        .order_by(Invoice.paid_at.desc()) # type: ignore
        .limit(20)
    )
    historical = result.scalars().all()

    if not historical:
        return {
            "has_prediction": False,
            "reason": "No payment history for this customer",
            "avg_days": None,
            "predicted_date": None,
        }

    payment_days = []
    for h in historical:
        if h.paid_at and h.issue_date: # type: ignore
            d = (h.paid_at.date() - h.issue_date).days
            if 0 <= d <= 365:
                payment_days.append(d)

    if not payment_days:
        return {
            "has_prediction": False,
            "reason": "Insufficient data",
            "avg_days": None,
            "predicted_date": None
        }

    avg_days = round(sum(payment_days) / len(payment_days))
    median_days = sorted(payment_days)[len(payment_days) // 2]

    std_dev = (
        sum((d - avg_days) ** 2 for d in payment_days) / len(payment_days)
    ) ** 0.5

    predicted_days = round(avg_days * 0.4 + median_days * 0.6)
    predicted_date = (
        invoice.issue_date + timedelta(days=predicted_days) # type: ignore
    ).isoformat()

    consistency = max(0, 1 - (std_dev / max(avg_days, 1)))
    confidence = min(0.95, consistency * min(1.0, len(payment_days) / 10))

    today = date.today()
    days_since_issue = (today - invoice.issue_date).days
    remaining_days = max(0, predicted_days - days_since_issue)

    return {
        "has_prediction": True,
        "avg_days": avg_days,
        "median_days": median_days,
        "predicted_days_from_issue": predicted_days,
        "predicted_date": predicted_date,
        "days_remaining": remaining_days,
        "confidence": round(confidence, 2),
        "sample_size": len(payment_days),
        "is_likely_late": days_since_issue > predicted_days * 1.2,
        "historical_range": {
            "min": min(payment_days),
            "max": max(payment_days),
        },
    }


# ── GET /invoice-anomalies/{invoice_id} ─────────────────

@router.get("/invoice-anomalies/{invoice_id}")
async def check_invoice_anomalies(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.invoice import Invoice, InvoiceStatus
    from app.models.customer import Customer

    biz = await _get_business(db, current_user)

    try:
        inv_uuid = uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid invoice ID")

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == inv_uuid,
            Invoice.business_id == biz.id,
        )
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    anomalies = []
    inv_amount = float(invoice.total_amount or 0) # type: ignore

    # Historical
    result = await db.execute(
        select(Invoice)
        .where(
            Invoice.customer_id == invoice.customer_id,
            Invoice.business_id == biz.id,
            Invoice.status != InvoiceStatus.DRAFT, # type: ignore
            Invoice.status != InvoiceStatus.CANCELLED, # type: ignore
            Invoice.id != invoice.id,
        )
        .order_by(Invoice.created_at.desc())
        .limit(20)
    )
    historical = result.scalars().all()

    if historical:
        amounts = [float(i.total_amount or 0) for i in historical] # type: ignore
        avg_amount = sum(amounts) / len(amounts)

        if avg_amount > 0 and inv_amount > avg_amount * 5:
            anomalies.append({
                "type": "amount_unusual",
                "severity": "warning",
                "message": f"Invoice unusually large vs history",
            })

        last_invoice = max(historical, key=lambda i: i.issue_date)
        days_since = (date.today() - last_invoice.issue_date).days

        if days_since > 90:
            anomalies.append({
                "type": "dormant_customer",
                "severity": "info",
                "message": f"No invoice in {days_since} days",
            })

    # Duplicate check
    result = await db.execute(
        select(Invoice).where(
            Invoice.business_id == biz.id,
            Invoice.customer_id == invoice.customer_id,
            Invoice.total_amount == invoice.total_amount,
            Invoice.issue_date >= date.today() - timedelta(days=7),
            Invoice.id != invoice.id,
        )
    )
    recent_same = result.scalar_one_or_none()

    if recent_same:
        anomalies.append({
            "type": "possible_duplicate",
            "severity": "warning",
            "message": "Possible duplicate invoice",
        })

    # Customer
    result = await db.execute(
        select(Customer).where(Customer.id == invoice.customer_id)
    )
    customer = result.scalar_one_or_none()

    if customer:
        outstanding = float(customer.total_invoiced_amount or 0) - float(customer.total_paid_amount or 0) # type: ignore

        if outstanding > inv_amount * 2:
            anomalies.append({
                "type": "high_outstanding",
                "severity": "warning",
                "message": "Customer has high outstanding balance",
            })

    return {
        "anomalies": anomalies,
        "invoice_id": invoice_id,
        "count": len(anomalies)
    }


# ── GET /fx-rates ──────────────────────────────────────

@router.get("/fx-rates")
async def get_fx_rates(
    current_user: User = Depends(get_current_user),
):
    try:
        from app.services.fx_rates import get_fx_rates as _rates
        rates = _rates()

        return {
            "rates": rates,
            "base": "NGN",
            "disclaimer": "Indicative rates only",
        }
    except Exception as e:
        logger.error(f"FX rate fetch error: {e}")

        return {
            "rates": {"USD": 0.00065, "GBP": 0.00052, "EUR": 0.00060, "NGN": 1.0},
            "base": "NGN",
            "disclaimer": "Fallback rates",
        }
