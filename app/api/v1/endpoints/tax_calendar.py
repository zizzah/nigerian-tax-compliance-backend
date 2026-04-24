"""
Tax Calendar & Obligation Tracker (Async)
Location: app/api/v1/endpoints/tax_calendar.py
"""

import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.payment import Payment
from app.models.expense import Expense

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax-calendar", tags=["Tax Calendar"])


# ── Helpers ─────────────────────────────────────

async def _get_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalars().first()

    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    return biz


async def _maybe_get_business(db: AsyncSession, user: User) -> Business | None:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    return result.scalars().first()


def _get_next_filing_date(obligation_type: str, today: date) -> date:
    year, month = today.year, today.month

    if obligation_type == "VAT":
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        filing_date = date(next_year, next_month, 21)
        if filing_date <= today:
            next_month = next_month + 1 if next_month < 12 else 1
            next_year = next_year if next_month > 1 else next_year + 1
            filing_date = date(next_year, next_month, 21)
        return filing_date

    if obligation_type == "PAYE":
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        return date(next_year, next_month, 10)

    if obligation_type == "WHT":
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        return date(next_year, next_month, 21)

    if obligation_type == "CIT":
        return date(year + 1, 6, 30)

    return today + timedelta(days=30)


# ── GET /tax-calendar/obligations ─────────────────

@router.get("/obligations")
async def get_tax_obligations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Async tax obligation estimator based on real financial data.
    """

    today = date.today()
    biz = await _maybe_get_business(db, current_user)
    if not biz:
        return {
            "obligations": [],
            "total_estimated_liability": 0,
            "next_due": None,
            "as_of": today.isoformat(),
            "disclaimer": "Create a business profile to start tracking tax obligations.",
        }

    current_month_start = today.replace(day=1)
    prev_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    prev_month_end = current_month_start - timedelta(days=1)

    # ── LAST MONTH REVENUE ───────────────────────
    last_month_revenue = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.business_id == biz.id,
                    Payment.payment_date >= prev_month_start,
                    Payment.payment_date <= prev_month_end,
                )
            )
        ).scalar_one()
    )

    # ── VAT INPUT (EXPENSES) ─────────────────────
    vat_on_expenses = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0)).where(
                    Expense.business_id == biz.id,
                    extract("year", Expense.expense_date) == prev_month_start.year,
                    extract("month", Expense.expense_date) == prev_month_start.month,
                )
            )
        ).scalar_one()
    ) * 0.075

    vat_collected = last_month_revenue * 0.075
    net_vat = max(0, vat_collected - vat_on_expenses)

    # ── WHT ──────────────────────────────────────
    wht_estimate = last_month_revenue * 0.05

    # ── YTD REVENUE + EXPENSES (BATCHED) ─────────
    ytd_revenue = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.business_id == biz.id,
                    extract("year", Payment.payment_date) == today.year,
                )
            )
        ).scalar_one()
    )

    ytd_expenses = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0)).where(
                    Expense.business_id == biz.id,
                    extract("year", Expense.expense_date) == today.year,
                )
            )
        ).scalar_one()
    )

    ytd_profit = max(0, ytd_revenue - ytd_expenses)
    cit_estimate = ytd_profit * 0.30

    # ── PRE-COMPUTE DATES (avoid repetition) ─────
    vat_due = _get_next_filing_date("VAT", today)
    wht_due = _get_next_filing_date("WHT", today)
    cit_due = _get_next_filing_date("CIT", today)

    obligations = [
        {
            "type": "VAT",
            "full_name": "Value Added Tax (FIRS)",
            "description": f"VAT on last month's sales (₦{last_month_revenue:,.0f}) minus input VAT",
            "estimated_liability": round(net_vat, 2),
            "period": prev_month_start.strftime("%B %Y"),
            "due_date": vat_due.isoformat(),
            "days_until_due": (vat_due - today).days,
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
            "period": prev_month_start.strftime("%B %Y"),
            "due_date": wht_due.isoformat(),
            "days_until_due": (wht_due - today).days,
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
            "due_date": cit_due.isoformat(),
            "days_until_due": (cit_due - today).days,
            "status": "upcoming",
            "rate": "30%",
            "firs_form": "CIT Form A",
            "color": "#dc2626",
        },
    ]

    obligations.sort(key=lambda x: x["days_until_due"])

    return {
        "obligations": obligations,
        "total_estimated_liability": sum(o["estimated_liability"] for o in obligations),
        "next_due": obligations[0] if obligations else None,
        "as_of": today.isoformat(),
        "disclaimer": "Estimates only. Confirm filings with a qualified accountant.",
    }
