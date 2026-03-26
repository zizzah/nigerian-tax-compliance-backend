"""
AI Insights API Endpoints
Location: app/api/v1/endpoints/insights.py

Provides:
  GET  /insights/                          - Get/generate proactive insights
  POST /insights/{insight_id}/dismiss      - Dismiss an insight
  GET  /insights/payment-prediction/{id}  - Predict payment date for an invoice
  GET  /insights/invoice-anomalies/{id}   - Check anomalies before sending invoice
  GET  /insights/fx-rates                 - Current NGN exchange rates

Register in app/main.py:
  from app.api.v1.endpoints import insights
  app.include_router(insights.router, prefix=settings.API_V1_PREFIX)
"""
import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.ai_insight import AIInsight
from app.services.ai.insights_engine import InsightsEngine

router = APIRouter(prefix="/insights", tags=["AI Insights"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz


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


# ── GET /insights/ ────────────────────────────────────────────────────────────

@router.get("/")
def get_insights(
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get AI insights for the current business.
    Returns cached today's insights unless ?refresh=true is passed.
    Generating fresh insights costs one Groq API call.
    """
    biz = _get_business(db, current_user)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    existing = (
        db.query(AIInsight)
        .filter(
            AIInsight.business_id == biz.id,
            AIInsight.is_dismissed == False,
            AIInsight.created_at >= today_start,
        )
        .order_by(AIInsight.created_at.desc())
        .all()
    )

    if existing and not refresh:
        return {"insights": [_serialize_insight(i) for i in existing], "cached": True}

    engine = InsightsEngine()
    new_insights = engine.generate_insights(db, biz)
    return {"insights": [_serialize_insight(i) for i in new_insights], "cached": False}


# ── POST /insights/{id}/dismiss ───────────────────────────────────────────────

@router.post("/{insight_id}/dismiss")
def dismiss_insight(
    insight_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss an AI insight so it no longer appears on the dashboard."""
    biz = _get_business(db, current_user)
    insight = db.query(AIInsight).filter(
        AIInsight.id == insight_id,
        AIInsight.business_id == biz.id,
    ).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    insight.is_dismissed = True # type: ignore
    insight.dismissed_at = datetime.now(timezone.utc) # type: ignore
    db.commit()
    return {"success": True}


# ── GET /insights/payment-prediction/{invoice_id} ─────────────────────────────

@router.get("/payment-prediction/{invoice_id}")
def predict_payment_date(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Predict when an invoice will be paid based on the customer's historical
    payment behaviour.

    Returns:
    - predicted_date: ISO date string
    - avg_days / median_days: historical averages
    - confidence: 0.0–1.0
    - is_likely_late: whether payment is already overdue relative to prediction
    """
    from app.models.invoice import Invoice, InvoiceStatus

    biz = _get_business(db, current_user)
    try:
        inv_uuid = uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid invoice ID")

    invoice = db.query(Invoice).filter(
        Invoice.id == inv_uuid,
        Invoice.business_id == biz.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Historical paid invoices for this customer
    historical = (
        db.query(Invoice)
        .filter(
            Invoice.business_id == biz.id,
            Invoice.customer_id == invoice.customer_id,
            Invoice.status == InvoiceStatus.PAID, # type: ignore
            Invoice.paid_at.isnot(None), # type: ignore
        )
        .order_by(Invoice.paid_at.desc()) # type: ignore
        .limit(20)
        .all()
    )

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
        return {"has_prediction": False, "reason": "Insufficient data", "avg_days": None, "predicted_date": None}

    avg_days = round(sum(payment_days) / len(payment_days))
    median_days = sorted(payment_days)[len(payment_days) // 2]
    std_dev = (sum((d - avg_days) ** 2 for d in payment_days) / len(payment_days)) ** 0.5

    # Weighted blend (median weighted higher for reliability)
    predicted_days = round(avg_days * 0.4 + median_days * 0.6)
    predicted_date = (invoice.issue_date + timedelta(days=predicted_days)).isoformat() # type: ignore

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
        "historical_range": {"min": min(payment_days), "max": max(payment_days)},
    }


# ── GET /insights/invoice-anomalies/{invoice_id} ──────────────────────────────

@router.get("/invoice-anomalies/{invoice_id}")
def check_invoice_anomalies(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check a DRAFT invoice for anomalies before it is finalised/sent.

    Returns a list of warnings the user should review:
    - Unusually large amount compared to customer history
    - Dormant customer (no invoice in 90+ days)
    - Possible duplicate (same amount in last 7 days)
    - Customer already has a large outstanding balance
    """
    from app.models.invoice import Invoice, InvoiceStatus
    from app.models.customer import Customer

    biz = _get_business(db, current_user)
    try:
        inv_uuid = uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid invoice ID")

    invoice = db.query(Invoice).filter(
        Invoice.id == inv_uuid,
        Invoice.business_id == biz.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    anomalies = []
    inv_amount = float(invoice.total_amount or 0) # type: ignore

    # Historical invoices for this customer (excluding the current one)
    historical = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == invoice.customer_id,
            Invoice.business_id == biz.id,
            Invoice.status != InvoiceStatus.DRAFT, # type: ignore
            Invoice.status != InvoiceStatus.CANCELLED, # type: ignore
            Invoice.id != invoice.id,
        )
        .order_by(Invoice.created_at.desc())
        .limit(20)
        .all()
    )

    if historical:
        amounts = [float(i.total_amount or 0) for i in historical] # type: ignore
        avg_amount = sum(amounts) / len(amounts)

        # Flag if this invoice is 5× or more than customer average
        if avg_amount > 0 and inv_amount > avg_amount * 5:
            anomalies.append({
                "type": "amount_unusual",
                "severity": "warning",
                "message": (
                    f"This invoice (₦{inv_amount:,.0f}) is {inv_amount / avg_amount:.1f}× larger than "
                    f"your average for this customer (₦{avg_amount:,.0f}). Is that intentional?"
                ),
            })

        # Flag dormant customer
        last_invoice = max(historical, key=lambda i: i.issue_date)
        days_since = (date.today() - last_invoice.issue_date).days
        if days_since > 90:
            anomalies.append({
                "type": "dormant_customer",
                "severity": "info",
                "message": (
                    f"You haven't invoiced this customer in {days_since} days. "
                    "Make sure their contact details are still current."
                ),
            })

    # Possible duplicate: same amount in last 7 days
    recent_same = (
        db.query(Invoice)
        .filter(
            Invoice.business_id == biz.id,
            Invoice.customer_id == invoice.customer_id,
            Invoice.total_amount == invoice.total_amount,
            Invoice.issue_date >= date.today() - timedelta(days=7),
            Invoice.id != invoice.id,
        )
        .first()
    )
    if recent_same:
        days_ago = (date.today() - recent_same.issue_date).days
        anomalies.append({
            "type": "possible_duplicate",
            "severity": "warning",
            "message": (
                f"Invoice {recent_same.invoice_number} for the same amount (₦{inv_amount:,.0f}) "
                f"was created {days_ago} day(s) ago. Possible duplicate?"
            ),
        })

    # Large outstanding balance warning
    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first()
    if customer:
        outstanding = float(customer.total_invoiced_amount or 0) - float(customer.total_paid_amount or 0) # type: ignore
        if outstanding > inv_amount * 2:
            anomalies.append({
                "type": "high_outstanding",
                "severity": "warning",
                "message": (
                    f"This customer already has ₦{outstanding:,.0f} outstanding. "
                    f"Adding this invoice brings the total to ₦{outstanding + inv_amount:,.0f}."
                ),
            })

    return {"anomalies": anomalies, "invoice_id": invoice_id, "count": len(anomalies)}


# ── GET /insights/fx-rates ────────────────────────────────────────────────────

@router.get("/fx-rates")
def get_fx_rates(
    current_user: User = Depends(get_current_user),
):
    """
    Get indicative NGN exchange rates (1-hour cache).
    Uses exchangerate-api.com free tier.
    """
    try:
        from app.services.fx_rates import get_fx_rates as _rates
        rates = _rates()
        return {
            "rates": rates,
            "base": "NGN",
            "disclaimer": "Indicative rates only. Use CBN official rates for formal filings.",
        }
    except Exception as e:
        logger.error(f"FX rate fetch error: {e}")
        # Return hardcoded fallback rates if service unavailable
        return {
            "rates": {"USD": 0.00065, "GBP": 0.00052, "EUR": 0.00060, "NGN": 1.0},
            "base": "NGN",
            "disclaimer": "Fallback rates — live rates unavailable.",
        }