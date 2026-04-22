"""
Sales Targets Endpoint
Location: app/api/v1/endpoints/targets.py

Endpoints:
  GET    /targets                   — list targets for this business
  POST   /targets                   — create or update target for a year
  GET    /targets/{year}            — get target + actuals + performance for a year
  DELETE /targets/{year}            — delete target
  POST   /targets/{year}/ai-advice  — get Groq AI advisory based on performance
"""
import uuid
import logging
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.sales_target import SalesTarget, split_annual_target

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/targets", tags=["Sales Targets"])

MONTH_NAMES = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
               'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz


def _get_monthly_actuals(db: Session, business_id: uuid.UUID, year: int) -> list[float]:
    """Return list of 12 floats — actual revenue collected per month via payments."""
    rows = (
        db.query(
            extract('month', Payment.payment_date).label('month'),
            func.sum(Payment.amount).label('total'),
        )
        .filter(
            Payment.business_id == business_id,
            extract('year', Payment.payment_date) == year,
        )
        .group_by('month')
        .all()
    )
    actuals = [0.0] * 12
    for row in rows:
        actuals[int(row.month) - 1] = float(row.total or 0)
    return actuals


def _get_pipeline(db: Session, business_id: uuid.UUID, year: int) -> float:
    """Outstanding amount on SENT/OVERDUE/PARTIALLY_PAID invoices for the year."""
    result = (
        db.query(func.sum(Invoice.outstanding_amount))
        .filter(
            Invoice.business_id == business_id,
            extract('year', Invoice.issue_date) == year,
            Invoice.status.in_([ # type: ignore
                InvoiceStatus.SENT,
                InvoiceStatus.OVERDUE,
                InvoiceStatus.PARTIALLY_PAID,
            ]),
        )
        .scalar()
    )
    return float(result or 0)


def _get_top_customers(db: Session, business_id: uuid.UUID, year: int, limit: int = 5):
    """Top customers by revenue collected this year."""
    rows = (
        db.query(
            Customer.name,
            func.sum(Payment.amount).label('total'),
        )
        .join(Payment, Payment.customer_id == Customer.id)
        .filter(
            Payment.business_id == business_id,
            extract('year', Payment.payment_date) == year,
        )
        .group_by(Customer.id, Customer.name)
        .order_by(func.sum(Payment.amount).desc())
        .limit(limit)
        .all()
    )
    return [{"name": r.name, "amount": float(r.total)} for r in rows]


def _build_performance(target: SalesTarget, actuals: list[float], year: int) -> dict:
    """Build full performance breakdown."""
    today = date.today()
    current_month = today.month if today.year == year else (12 if today.year > year else 0)
    current_quarter = ((current_month - 1) // 3 + 1) if current_month > 0 else 0

    annual_target = float(target.annual_target) # type: ignore
    total_actual  = sum(actuals)
    annual_pct    = round((total_actual / annual_target * 100), 1) if annual_target else 0

    # Monthly breakdown
    monthly = []
    for i, (label, key) in enumerate(zip(MONTH_LABELS, MONTH_NAMES)):
        t = float(getattr(target, f"{key}_target") or 0)
        a = actuals[i]
        is_past = (i + 1) < current_month or today.year > year
        is_current = (i + 1) == current_month and today.year == year
        pct = round((a / t * 100), 1) if t else 0
        monthly.append({
            "month":      i + 1,
            "label":      label,
            "target":     t,
            "actual":     a,
            "pct":        pct,
            "status":     _status(pct, is_past, is_current),
            "is_past":    is_past,
            "is_current": is_current,
        })

    # Quarterly breakdown
    quarters = []
    for q in range(1, 5):
        months_slice = actuals[(q - 1) * 3: q * 3]
        qt = float(getattr(target, f"q{q}_target") or 0)
        qa = sum(months_slice)
        is_past = q < current_quarter or today.year > year
        is_current = q == current_quarter and today.year == year
        pct = round((qa / qt * 100), 1) if qt else 0
        quarters.append({
            "quarter":    q,
            "label":      f"Q{q}",
            "target":     qt,
            "actual":     qa,
            "pct":        pct,
            "status":     _status(pct, is_past, is_current),
            "is_past":    is_past,
            "is_current": is_current,
        })

    # Projected year-end (simple linear extrapolation from months elapsed)
    months_elapsed = max(current_month - 1, 1) if today.year == year else 12
    run_rate = total_actual / months_elapsed if months_elapsed else 0
    projected = round(run_rate * 12, 2)

    return {
        "year":           year,
        "annual_target":  annual_target,
        "total_actual":   round(total_actual, 2),
        "annual_pct":     annual_pct,
        "annual_status":  _status(annual_pct, today.year > year, today.year == year),
        "gap":            round(annual_target - total_actual, 2),
        "projected":      projected,
        "months_elapsed": months_elapsed,
        "run_rate_monthly": round(run_rate, 2),
        "monthly":        monthly,
        "quarters":       quarters,
    }


def _status(pct: float, is_past: bool, is_current: bool) -> str:
    if not is_past and not is_current:
        return "future"
    if pct >= 110:
        return "exceeding"
    if pct >= 95:
        return "on_track"
    if pct >= 70:
        return "at_risk"
    return "behind"


# ── Schemas ───────────────────────────────────────────────────────────────────

class TargetCreate(BaseModel):
    year:          int   = Field(..., ge=2020, le=2035)
    annual_target: float = Field(..., gt=0, description="Annual revenue target in Naira")
    # Optional monthly overrides — if not provided, auto-split is used
    jan_target: Optional[float] = None
    feb_target: Optional[float] = None
    mar_target: Optional[float] = None
    apr_target: Optional[float] = None
    may_target: Optional[float] = None
    jun_target: Optional[float] = None
    jul_target: Optional[float] = None
    aug_target: Optional[float] = None
    sep_target: Optional[float] = None
    oct_target: Optional[float] = None
    nov_target: Optional[float] = None
    dec_target: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all targets for this business."""
    biz = _get_business(db, current_user)
    targets = (
        db.query(SalesTarget)
        .filter(SalesTarget.business_id == biz.id)
        .order_by(SalesTarget.year.desc())
        .all()
    )
    return [{"id": str(t.id), "year": t.year,
             "annual_target": float(t.annual_target)} for t in targets] # type: ignore


@router.post("/", status_code=201)
def create_or_update_target(
    data: TargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new target or update existing one for the year."""
    biz = _get_business(db, current_user)

    # Auto-split unless overrides provided
    splits = split_annual_target(data.annual_target)

    # Apply any manual overrides
    for key in MONTH_NAMES:
        override = getattr(data, f"{key}_target", None)
        if override is not None:
            splits[key] = override

    # Recompute quarterly totals from monthly
    splits['q1_target'] = round(splits['jan'] + splits['feb'] + splits['mar'], 2)
    splits['q2_target'] = round(splits['apr'] + splits['may'] + splits['jun'], 2)
    splits['q3_target'] = round(splits['jul'] + splits['aug'] + splits['sep'], 2)
    splits['q4_target'] = round(splits['oct'] + splits['nov'] + splits['dec'], 2)

    existing = db.query(SalesTarget).filter(
        SalesTarget.business_id == biz.id,
        SalesTarget.year == data.year,
    ).first()

    if existing:
        existing.annual_target = data.annual_target  # type: ignore
        for key in MONTH_NAMES:
            setattr(existing, f"{key}_target", splits[key])
        for q in ['q1_target', 'q2_target', 'q3_target', 'q4_target']:
            setattr(existing, q, splits[q])
        existing.updated_at = datetime.utcnow()  # type: ignore
        db.commit()
        db.refresh(existing)
        return {"message": f"{data.year} target updated", "id": str(existing.id),
                "splits": splits}
    else:
        target = SalesTarget(
            id=uuid.uuid4(),
            business_id=biz.id,
            year=data.year,
            annual_target=data.annual_target,
            **{f"{key}_target": splits[key] for key in MONTH_NAMES},
            q1_target=splits['q1_target'],
            q2_target=splits['q2_target'],
            q3_target=splits['q3_target'],
            q4_target=splits['q4_target'],
        )
        db.add(target)
        db.commit()
        db.refresh(target)
        return {"message": f"{data.year} target created", "id": str(target.id),
                "splits": splits}


@router.get("/{year}")
def get_target_performance(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get target + actual performance breakdown for a year."""
    biz = _get_business(db, current_user)

    target = db.query(SalesTarget).filter(
        SalesTarget.business_id == biz.id,
        SalesTarget.year == year,
    ).first()

    if not target:
        raise HTTPException(status_code=404,
                            detail=f"No target set for {year}. Create one first.")

    actuals  = _get_monthly_actuals(db, biz.id, year) # type: ignore
    pipeline = _get_pipeline(db, biz.id, year) # type: ignore
    top_customers = _get_top_customers(db, biz.id, year) # type: ignore
    perf = _build_performance(target, actuals, year)
    perf["pipeline"] = pipeline
    perf["top_customers"] = top_customers

    return perf


@router.delete("/{year}", status_code=204)
def delete_target(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = _get_business(db, current_user)
    target = db.query(SalesTarget).filter(
        SalesTarget.business_id == biz.id,
        SalesTarget.year == year,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    db.commit()
    return None


@router.post("/{year}/ai-advice")
def get_ai_advice(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate AI advisory using Groq based on:
    - Gap analysis (how far behind/ahead)
    - Customer recommendations (who to chase)
    - Seasonal patterns from past data
    - Invoice pipeline forecast
    """
    biz = _get_business(db, current_user)

    target = db.query(SalesTarget).filter(
        SalesTarget.business_id == biz.id,
        SalesTarget.year == year,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="No target set for this year.")

    actuals       = _get_monthly_actuals(db, biz.id, year) # type: ignore
    pipeline      = _get_pipeline(db, biz.id, year)  # type: ignore
    top_customers = _get_top_customers(db, biz.id, year, limit=5)  # type: ignore
    perf          = _build_performance(target, actuals, year)

    # Also get last year's actuals for seasonal context
    prev_actuals = _get_monthly_actuals(db, biz.id, year - 1) # type: ignore
    prev_total   = sum(prev_actuals)

    # Overdue invoice count
    overdue_count = db.query(func.count(Invoice.id)).filter(
        Invoice.business_id == biz.id,
        Invoice.status == InvoiceStatus.OVERDUE,  # type: ignore
    ).scalar() or 0

    overdue_amount = db.query(func.sum(Invoice.outstanding_amount)).filter(
        Invoice.business_id == biz.id,
        Invoice.status == InvoiceStatus.OVERDUE,  # type: ignore
    ).scalar() or 0

    # Build context for Groq
    today = date.today()
    months_elapsed = max(perf['months_elapsed'], 1)
    remaining_months = 12 - months_elapsed

    prompt = f"""You are a sharp Nigerian business financial advisor. 
Analyse this business's sales performance and give specific, actionable advice.

BUSINESS: {biz.business_name}
YEAR: {year} (Today: {today.strftime('%d %B %Y')})

ANNUAL TARGET: ₦{perf['annual_target']:,.0f}
ACHIEVED SO FAR: ₦{perf['total_actual']:,.0f} ({perf['annual_pct']}% of target)
REMAINING GAP: ₦{perf['gap']:,.0f}
MONTHS ELAPSED: {months_elapsed} of 12 ({remaining_months} months left)
CURRENT RUN RATE: ₦{perf['run_rate_monthly']:,.0f}/month
PROJECTED YEAR-END: ₦{perf['projected']:,.0f}
PIPELINE (unpaid invoices): ₦{pipeline:,.0f}
OVERDUE INVOICES: {overdue_count} invoices worth ₦{float(overdue_amount):,.0f}

QUARTERLY PERFORMANCE:
{chr(10).join(f"  Q{q['quarter']}: Target ₦{q['target']:,.0f} | Actual ₦{q['actual']:,.0f} | {q['pct']}% ({q['status'].upper()})" for q in perf['quarters'])}

MONTHLY ACTUALS THIS YEAR:
{chr(10).join(f"  {m['label']}: Target ₦{m['target']:,.0f} | Actual ₦{m['actual']:,.0f} | {m['pct']}%" for m in perf['monthly'] if m['is_past'] or m['is_current'])}

TOP CUSTOMERS BY REVENUE ({year}):
{chr(10).join(f"  {c['name']}: ₦{c['amount']:,.0f}" for c in top_customers) if top_customers else "  No payment data yet"}

LAST YEAR TOTAL REVENUE: ₦{prev_total:,.0f}

Give your response in this exact JSON structure:
{{
  "headline": "One punchy sentence summarising their current position",
  "overall_status": "exceeding|on_track|at_risk|behind",
  "gap_analysis": "2-3 sentences about where they stand vs target, what the gap means practically",
  "customer_recommendations": "2-3 specific actions — which customer segments to focus on, whether to chase overdue payments, upsell opportunities. Be specific with numbers.",
  "seasonal_insight": "1-2 sentences about seasonal patterns based on monthly data and comparison to last year",
  "pipeline_forecast": "1-2 sentences — will the current pipeline + run rate get them to target? What needs to happen?",
  "top_3_actions": ["Action 1 with specific ₦ figure", "Action 2 with specific ₦ figure", "Action 3 with specific ₦ figure"],
  "confidence_score": 0-100
}}

Respond ONLY with the JSON. No markdown, no preamble."""

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
        # Strip any accidental markdown
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        import json
        advice = json.loads(raw)
        return {"advice": advice, "generated_at": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Groq AI advice error: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI advisor temporarily unavailable. Please try again."
        )