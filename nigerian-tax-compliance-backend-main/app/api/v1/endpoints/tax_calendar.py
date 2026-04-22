"""
Tax Calendar & Obligation Tracker
Location: app/api/v1/endpoints/tax_calendar.py
"""
import logging
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.expense import Expense

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax-calendar", tags=["Tax Calendar"])


def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz


def _get_next_filing_date(obligation_type: str, today: date) -> date:
    """Calculate next filing deadline for each tax type."""
    year, month = today.year, today.month

    if obligation_type == "VAT":
        # VAT filing: 21st of the following month
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        filing_date = date(next_year, next_month, 21)
        if filing_date <= today:
            next_month = next_month + 1 if next_month < 12 else 1
            next_year = next_year if next_month > 1 else next_year + 1
            filing_date = date(next_year, next_month, 21)
        return filing_date

    if obligation_type == "PAYE":
        # PAYE: 10th of following month
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        return date(next_year, next_month, 10)

    if obligation_type == "WHT":
        # WHT: 21st of following month (same as VAT)
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        return date(next_year, next_month, 21)

    if obligation_type == "CIT":
        # Company Income Tax: 6 months after fiscal year end (assume Dec 31)
        return date(year + 1, 6, 30)

    return today + timedelta(days=30)


@router.get("/obligations")
def get_tax_obligations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return upcoming tax obligations with estimated liability amounts.
    Based on actual revenue and expense data in the system.
    """
    biz = _get_business(db, current_user)
    today = date.today()
    current_month_start = today.replace(day=1)
    prev_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    prev_month_end = current_month_start - timedelta(days=1)

    # --- VAT: 7.5% on sales from last month ---
    last_month_revenue = float(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.business_id == biz.id,
        Payment.payment_date >= prev_month_start,
        Payment.payment_date <= prev_month_end,
    ).scalar() or 0)

    vat_collected = last_month_revenue * 0.075
    vat_on_expenses = float(db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.business_id == biz.id,
        extract('year', Expense.expense_date) == prev_month_start.year,
        extract('month', Expense.expense_date) == prev_month_start.month,
    ).scalar() or 0) * 0.075
    net_vat = max(0, vat_collected - vat_on_expenses)

    # --- WHT: 5% on relevant service payments received ---
    wht_estimate = last_month_revenue * 0.05

    # --- CIT estimate: 30% of annual profit ---
    ytd_revenue = float(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.business_id == biz.id,
        extract('year', Payment.payment_date) == today.year,
    ).scalar() or 0)
    ytd_expenses = float(db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.business_id == biz.id,
        extract('year', Expense.expense_date) == today.year,
    ).scalar() or 0)
    ytd_profit = max(0, ytd_revenue - ytd_expenses)
    cit_estimate = ytd_profit * 0.30

    obligations = [
        {
            "type": "VAT",
            "full_name": "Value Added Tax (FIRS)",
            "description": f"VAT on last month's sales (₦{last_month_revenue:,.0f}) minus input VAT",
            "estimated_liability": round(net_vat, 2),
            "period": f"{prev_month_start.strftime('%B %Y')}",
            "due_date": _get_next_filing_date("VAT", today).isoformat(),
            "days_until_due": (_get_next_filing_date("VAT", today) - today).days,
            "status": "upcoming",
            "rate": "7.5%",
            "firs_form": "VAT Form 002",
            "color": "#2563eb",
        },
        {
            "type": "WHT",
            "full_name": "Withholding Tax (FIRS)",
            "description": "WHT deducted from payments to service providers",
            "estimated_liability": round(wht_estimate, 2),
            "period": f"{prev_month_start.strftime('%B %Y')}",
            "due_date": _get_next_filing_date("WHT", today).isoformat(),
            "days_until_due": (_get_next_filing_date("WHT", today) - today).days,
            "status": "upcoming",
            "rate": "5-10%",
            "firs_form": "WHT Schedule",
            "color": "#7c3aed",
        },
        {
            "type": "CIT",
            "full_name": "Company Income Tax (FIRS)",
            "description": f"30% on estimated annual profit (₦{ytd_profit:,.0f} YTD)",
            "estimated_liability": round(cit_estimate, 2),
            "period": f"FY {today.year}",
            "due_date": _get_next_filing_date("CIT", today).isoformat(),
            "days_until_due": (_get_next_filing_date("CIT", today) - today).days,
            "status": "upcoming",
            "rate": "30%",
            "firs_form": "CIT Form A",
            "color": "#dc2626",
        },
    ]

    # Sort by due date
    obligations.sort(key=lambda x: x["days_until_due"])

    return {
        "obligations": obligations,
        "total_estimated_liability": sum(o["estimated_liability"] for o in obligations),
        "next_due": obligations[0] if obligations else None,
        "as_of": today.isoformat(),
        "disclaimer": "Estimates based on recorded transactions. Consult a qualified accountant for exact FIRS filings.",
    }