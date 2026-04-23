"""
Expenses Endpoint
Location: app/api/v1/endpoints/expenses.py

Endpoints:
  GET    /expenses/             — paginated list with filters
  POST   /expenses/             — create expense
  GET    /expenses/summary      — monthly/category breakdown + P&L
  GET    /expenses/recurring    — list recurring expenses due soon
  GET    /expenses/{id}         — get single expense
  PATCH  /expenses/{id}         — update expense
  DELETE /expenses/{id}         — delete expense

Register in main.py:
  from app.api.v1.endpoints import expenses
  app.include_router(expenses.router, prefix=settings.API_V1_PREFIX)
"""
import uuid
import math
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from decimal import Decimal
from sqlalchemy import cast, Float as SAFloat, distinct
from sqlalchemy import text
from datetime import timezone


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import select
from sqlalchemy import func, extract, and_
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.expense import Expense, ExpenseCategory, ExpensePaymentMethod
from app.models.expense import CATEGORY_LABELS, TAX_DEDUCTIBLE, CATEGORY_GROUPS
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.models.payment import Payment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/expenses", tags=["Expenses"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_business(db: AsyncSession, user: User) -> Business:
    result =await  db.execute(select(Business).where(Business.user_id == user.id))
    biz = result.scalar_one_or_none()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz


def _next_due(period: str, from_date: date) -> date:
    if period == "monthly":
        # Same day next month
        m = from_date.month + 1
        y = from_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        try:
            return from_date.replace(year=y, month=m)
        except ValueError:
            return from_date.replace(year=y, month=m, day=28)
    elif period == "quarterly":
        return from_date + timedelta(days=91)
    elif period == "annual":
        try:
            return from_date.replace(year=from_date.year + 1)
        except ValueError:
            return from_date.replace(year=from_date.year + 1, day=28)
    return from_date + timedelta(days=30)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    category:          str   = Field(..., description="ExpenseCategory value")
    subcategory:       Optional[str]  = None
    description:       str   = Field(..., min_length=1, max_length=500)
    amount:            float = Field(..., gt=0)
    expense_date:      date  = Field(default_factory=date.today)
    vendor_name:       Optional[str]  = None
    reference_number:  Optional[str]  = None
    payment_method:    str   = Field(default="CASH")
    is_tax_deductible: Optional[bool] = None   # None = auto from category
    is_recurring:      bool  = False
    recurrence_period: Optional[str]  = None   # monthly|quarterly|annual
    receipt_url:       Optional[str]  = None
    notes:             Optional[str]  = None


class ExpenseUpdate(BaseModel):
    category:          Optional[str]   = None
    subcategory:       Optional[str]   = None
    description:       Optional[str]   = None
    amount:            Optional[float] = Field(None, gt=0)
    expense_date:      Optional[date]  = None
    vendor_name:       Optional[str]   = None
    reference_number:  Optional[str]   = None
    payment_method:    Optional[str]   = None
    is_tax_deductible: Optional[bool]  = None
    is_recurring:      Optional[bool]  = None
    recurrence_period: Optional[str]   = None
    receipt_url:       Optional[str]   = None
    notes:             Optional[str]   = None


def _serialize(e: Expense) -> dict:
    cat = e.category.value if hasattr(e.category, "value") else str(e.category)
    pm  = e.payment_method.value if hasattr(e.payment_method, "value") else str(e.payment_method)
    return {
        "id":               str(e.id),
        "category":         cat,
        "category_label":   CATEGORY_LABELS.get(cat, cat),
        "subcategory":      e.subcategory,
        "description":      e.description,
        "amount":           float(e.amount), # type: ignore
        "expense_date":     e.expense_date.isoformat() if e.expense_date else None, # type: ignore
        "vendor_name":      e.vendor_name,
        "reference_number": e.reference_number,
        "payment_method":   pm,
        "is_tax_deductible":e.is_tax_deductible,
        "is_recurring":     e.is_recurring,
        "recurrence_period":e.recurrence_period,
        "next_due_date":    e.next_due_date.isoformat() if e.next_due_date else None, # type: ignore
        "receipt_url":      e.receipt_url,
        "notes":            e.notes,
        "tax_year":         e.tax_year,
        "created_at":       e.created_at.isoformat() if e.created_at else None, # type: ignore
        "updated_at":       e.updated_at.isoformat() if e.updated_at else None, # type: ignore
    }


# ── GET /expenses/ ────────────────────────────────────────────────────────────

@router.get("/")
async def list_expenses(
    page:      int            = Query(1, ge=1),
    page_size: int            = Query(50, ge=1, le=100),
    category:  Optional[str]  = Query(None),
    from_date: Optional[date] = Query(None),
    to_date:   Optional[date] = Query(None),
    year:      Optional[int]  = Query(None),
    month:     Optional[int]  = Query(None, ge=1, le=12),
    search:    Optional[str]  = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await  _get_business(db, current_user)
    q   = select(Expense).where(Expense.business_id == biz.id)

    if category:
        try:
            q = q.where(Expense.category == ExpenseCategory(category))
        except ValueError:
            pass
    if from_date:
        q = q.where(Expense.expense_date >= from_date)
    if to_date:
        q = q.where(Expense.expense_date <= to_date)
    if year:
        q = q.where(extract("year", Expense.expense_date) == year)
    if month:
        q = q.where(extract("month", Expense.expense_date) == month)
    if search:
        like = f"%{search}%"
        q = q.where(
            Expense.description.ilike(like) |
            Expense.vendor_name.ilike(like) |
            Expense.reference_number.ilike(like)
        )

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar()
    total_pages = math.ceil(total / page_size) # type: ignore
    offset = (page - 1) * page_size
    result =await db.execute(
        q.order_by(Expense.expense_date.desc()).offset(offset).limit(page_size)

        
    )
    expenses = result.scalars().all()


    return {
        "expenses":    [_serialize(e) for e in expenses],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
    }


# ── POST /expenses/ ───────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_expense(
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz =await  _get_business(db, current_user)

    try:
        cat = ExpenseCategory(data.category)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid category: {data.category}")

    try:
        pm = ExpensePaymentMethod(data.payment_method)
    except ValueError:
        pm = ExpensePaymentMethod.CASH

    # Auto-set tax_deductible from category if not provided
    is_deductible = data.is_tax_deductible
    if is_deductible is None:
        is_deductible = TAX_DEDUCTIBLE.get(data.category, True)

    # Compute next_due_date for recurring
    next_due = None
    if data.is_recurring and data.recurrence_period:
        next_due = _next_due(data.recurrence_period, data.expense_date)

    try:
        expense = Expense(
            id=uuid.uuid4(),
            business_id=biz.id,
            category=cat,
            subcategory=data.subcategory,
            description=data.description,
            amount=Decimal(str(data.amount)),
            expense_date=data.expense_date,
            vendor_name=data.vendor_name,
            reference_number=data.reference_number,
            payment_method=pm,
            is_tax_deductible=is_deductible,
            tax_year=data.expense_date.year,
            is_recurring=data.is_recurring,
            recurrence_period=data.recurrence_period,
            next_due_date=next_due,
            receipt_url=data.receipt_url,
            notes=data.notes,
        )
        db.add(expense)
        await db.commit()
        await db.refresh(expense)
        return _serialize(expense)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Database error in create_expense: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# ── GET /expenses/summary ─────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    year:  int           = Query(default_factory=lambda: date.today().year),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns:
    - Total expenses for period
    - Breakdown by category
    - Monthly totals for the year
    - P&L (revenue collected vs total expenses)
    - Cash flow (payments received vs expenses paid)
    - YTD totals
    - Tax-deductible total
    """
    biz =await  _get_business(db, current_user)
    today = date.today()

    # ── Expense totals by category for the year ──────────────────────────────
    cat_rows = await db.execute(
        select(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),

        ).where(Expense.business_id == biz.id,extract("year", Expense.expense_date) == year,).group_by(Expense.category)
    )
    
    cat_rows = cat_rows.all()

    by_category = {}
    total_expenses = 0.0
    total_deductible = 0.0
    for row in cat_rows:
        cat = row.category.value if hasattr(row.category, "value") else str(row.category)
        amt = float(row.total or 0)
        by_category[cat] = {
            "category":       cat,
            "label":          CATEGORY_LABELS.get(cat, cat),
            "amount":         amt,
            "count":          int(row.count), # type: ignore
            "is_deductible":  TAX_DEDUCTIBLE.get(cat, True),
        }
        total_expenses += amt
        if TAX_DEDUCTIBLE.get(cat, True):
            total_deductible += amt

    # Organise into groups
    groups = []
    for group_name, cats in CATEGORY_GROUPS.items():
        group_total = sum(by_category.get(c, {}).get("amount", 0) for c in cats)
        if group_total > 0:
            groups.append({
                "group":      group_name,
                "total":      round(group_total, 2),
                "categories": [by_category[c] for c in cats if c in by_category],
            })

    # ── Monthly expense totals for the year ──────────────────────────────────
    month_rows = await(
        db.execute(
            select(extract("month", Expense.expense_date).label("mo"),
            func.sum(Expense.amount).label("total"),
        )
        .where(
            Expense.business_id == biz.id,
            extract("year", Expense.expense_date) == year,
        ).group_by("mo"))
        

    )
    monthly_expenses = {int(r.mo): float(r.total or 0) for r in month_rows}

    # ── Monthly revenue (from payments) ──────────────────────────────────────
    rev_rows = (
        await db.execute(
            select(extract("month", Payment.payment_date).label("mo"),
            func.sum(Payment.amount).label("total"),
        )
        .where(
            Payment.business_id == biz.id,
            extract("year", Payment.payment_date) == year,
        ).group_by("mo"))
        
        
    )
    
    rev_rows = rev_rows.all()
    monthly_revenue = {int(r.mo): float(r.total or 0) for r in rev_rows}

    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly = []
    for i, name in enumerate(month_names):
        mo = i + 1
        rev = monthly_revenue.get(mo, 0)
        exp = monthly_expenses.get(mo, 0)
        monthly.append({
            "month":    mo,
            "label":    name,
            "revenue":  round(rev, 2),
            "expenses": round(exp, 2),
            "profit":   round(rev - exp, 2),
            "is_past":  mo < today.month or year < today.year,
            "is_current": mo == today.month and year == today.year,
        })

    # ── YTD Revenue (cash collected) ─────────────────────────────────────────
    result = (
        await db.execute(select(func.sum(Payment.amount))
        .where(
            Payment.business_id == biz.id,
            extract("year", Payment.payment_date) == year,
            Payment.payment_date <= today,
        ))
        
    )
    
    ytd_revenue = float(result.scalar() or 0)

    # ── YTD Revenue from invoices (accrual — total invoiced) ─────────────────
    # Use all non-cancelled, non-draft invoices for the year
    # Filter by string values to avoid enum mismatch issues
    active_statuses = [
        InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID
    ]
    result = (
        await db.execute(select(func.sum(Invoice.total_amount))
        .where(
            Invoice.business_id == biz.id,
            extract("year", Invoice.issue_date) == year,
            Invoice.status.in_(active_statuses), # type: ignore
        ))
        
    )
    
    # Fallback: if invoice query returns 0 but we have cash revenue, use cash
    ytd_invoiced =float(result.scalar() or 0)
    if ytd_invoiced == 0 and ytd_revenue > 0:
        ytd_invoiced = ytd_revenue

    # ── COGS: auto-calculated from invoice items × product cost_price ─────────
    # Match COGS to invoices that are PAID this year (same basis as revenue)
    # This ensures COGS and Revenue are on the same cash basis
    ytd_start = date(year, 1, 1)
    ytd_end   = today if today.year == year else date(year, 12, 31)

    cogs_rows = (
        await db.execute(
            select(func.sum(
                cast(InvoiceItem.quantity, SAFloat) *
                cast(Product.cost_price, SAFloat)
            ).label("cogs")
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .join(Product, InvoiceItem.product_id == Product.id)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.business_id == biz.id,
            Payment.business_id == biz.id,
            Payment.payment_date >= ytd_start,
            Payment.payment_date <= ytd_end,
            Product.cost_price.isnot(None),
            Product.cost_price > 0,
        ))
        
    )
    cogs_rows = cogs_rows.scalar_one_or_none()
    cogs_ytd = float(cogs_rows or 0)

    # ── Fallback COGS via raw SQL if join returns 0 ───────────────────────────
    if cogs_ytd == 0:
        try:
            result =await  db.execute(
                text("""
                    SELECT COALESCE(SUM(CAST(ii.quantity AS FLOAT) * CAST(p.cost_price AS FLOAT)), 0)
                    FROM invoice_items ii
                    JOIN invoices i ON ii.invoice_id = i.id
                    JOIN products p ON ii.product_id = p.id
                    JOIN payments pay ON pay.invoice_id = i.id
                    WHERE i.business_id = :biz_id
                      AND pay.business_id = :biz_id
                      AND pay.payment_date >= :start_date
                      AND pay.payment_date <= :end_date
                      AND p.cost_price IS NOT NULL
                      AND p.cost_price > 0
                """),
                {"biz_id": str(biz.id), "start_date": ytd_start, "end_date": ytd_end}
            )
            cogs_ytd = float(result.scalar() or 0)
        except Exception:
            cogs_ytd = 0.0

    # ── Expense categories for proper P&L ─────────────────────────────────────
    COGS_CATS    = {"COST_OF_SALES"}
    FINANCE_CATS = {"BANK_CHARGES", "LOAN_INTEREST", "LOAN_REPAYMENT"}
    TAX_CATS     = {"COMPANY_TAX", "VAT_REMITTED", "WHT_REMITTED",
                    "PAYE_TAX", "GOVT_LEVIES", "NHF_CONTRIBUTION"}

    opex_total    = sum(v["amount"] for k, v in by_category.items()
                        if k not in COGS_CATS | FINANCE_CATS | TAX_CATS)
    finance_total = sum(v["amount"] for k, v in by_category.items()
                        if k in FINANCE_CATS)
    tax_exp_total = sum(v["amount"] for k, v in by_category.items()
                        if k in TAX_CATS)
    cogs_exp      = by_category.get("COST_OF_SALES", {}).get("amount", 0.0)

    # Use higher of: auto-calculated COGS from products OR manual COST_OF_SALES entry
    total_cogs    = max(cogs_ytd, cogs_exp)

    # ── Proper P&L Calculation ─────────────────────────────────────────────────
    # Use cash collected (ytd_revenue) as revenue - this is what the business
    # actually received, regardless of when invoices were issued.
    # ytd_invoiced is kept for reference but NOT used as revenue basis
    # because it misses invoices issued in prior years but paid this year.
    revenue        = ytd_revenue
    gross_profit   = revenue - total_cogs
    gross_margin   = round((gross_profit / revenue * 100), 1) if revenue > 0 else 0.0
    ebit           = gross_profit - opex_total
    net_before_tax = ebit - finance_total
    net_after_tax  = net_before_tax - tax_exp_total
    margin         = round((net_after_tax / revenue * 100), 1) if revenue > 0 else 0.0

    # ── Business health: YTD basis ─────────────────────────────────────────────
    if revenue == 0:
        health = "no_data"
    elif margin >= 20:
        health = "healthy"
    elif margin >= 5:
        health = "stable"
    elif margin >= 0:
        health = "breaking_even"
    else:
        health = "loss"

    # Warn if margin is suspiciously high (likely missing COGS)
    missing_cogs = revenue > 0 and total_cogs == 0
    net_profit = net_after_tax

    # ── Recurring expenses due soon (next 30 days) ───────────────────────────
    in_30 = today + timedelta(days=30)
    due_soon_result = (
        await db.execute(select(Expense)
        .where(
            Expense.business_id == biz.id,
            Expense.is_recurring == True,  # noqa: E712
            Expense.next_due_date <= in_30,
            Expense.next_due_date >= today,
        ).order_by(Expense.next_due_date).limit(5))  
    )
    
    due_soon = due_soon_result.scalars().all()

    return {
        "year":              year,
        "total_expenses":    round(total_expenses, 2),
        "total_deductible":  round(total_deductible, 2),
        # Cash basis
        "ytd_revenue":       round(ytd_revenue, 2),
        # Accrual basis (invoiced)
        "ytd_invoiced":      round(ytd_invoiced, 2),
        # P&L breakdown
        "cogs":              round(total_cogs, 2),
        "cogs_auto":         round(cogs_ytd, 2),
        "gross_profit":      round(gross_profit, 2),
        "gross_margin":      gross_margin,
        "opex":              round(opex_total, 2),
        "ebit":              round(ebit, 2),
        "finance_costs":     round(finance_total, 2),
        "net_before_tax":    round(net_before_tax, 2),
        "tax_expenses":      round(tax_exp_total, 2),
        "net_profit":        round(net_after_tax, 2),
        "profit_margin":     margin,
        "health":            health,
        "missing_cogs":      missing_cogs,
        "by_category":       by_category,
        "groups":            groups,
        "monthly":           monthly,
        "due_soon":          [_serialize(e) for e in due_soon], 
    }


# ── GET /expenses/recurring ───────────────────────────────────────────────────

@router.get("/recurring")
async def list_recurring(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await  _get_business(db, current_user)
    expenses = (
        await db.execute(select(Expense)
        .where(
            Expense.business_id == biz.id,
            Expense.is_recurring == True,  # noqa: E712
        )
        .order_by(Expense.next_due_date)
    )
    )
    expenses = expenses.scalars().all()
    today  = date.today()
    result = []
    for e in expenses:
        s = _serialize(e)
        s["days_until_due"] = (e.next_due_date - today).days if e.next_due_date else None # type: ignore
        s["is_overdue"]     = bool(e.next_due_date and e.next_due_date < today)
        result.append(s)
    return result


# ── GET /expenses/{id} ────────────────────────────────────────────────────────

@router.get("/{expense_id}")
async def get_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz =await _get_business(db, current_user)
    e =await  db.execute(select(Expense).where(
        Expense.id == expense_id,
        Expense.business_id == biz.id,
    ))
    
    e= e.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _serialize(e)


# ── PATCH /expenses/{id} ──────────────────────────────────────────────────────

@router.patch("/{expense_id}")
async def update_expense(
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz =await  _get_business(db, current_user)
    e =await  db.execute(select(Expense).where(
        Expense.id == expense_id,
        Expense.business_id == biz.id,
    ))
    e = e.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")

    update = data.model_dump(exclude_unset=True)

    if "category" in update:
        try:
            update["category"] = ExpenseCategory(update["category"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid category")

    if "payment_method" in update:
        try:
            update["payment_method"] = ExpensePaymentMethod(update["payment_method"])
        except ValueError:
            update["payment_method"] = ExpensePaymentMethod.CASH

    if "amount" in update:
        update["amount"] = Decimal(str(update["amount"]))

    # Recompute next_due_date if recurrence changed
    if "recurrence_period" in update or "expense_date" in update:
        period = update.get("recurrence_period") or e.recurrence_period
        base   = update.get("expense_date") or e.expense_date
        if period and (update.get("is_recurring", e.is_recurring)): # type: ignore
            update["next_due_date"] = _next_due(period, base) # type: ignore

    if "category" in update and "is_tax_deductible" not in update:
        cat = update["category"].value if hasattr(update["category"], "value") else str(update["category"])
        update["is_tax_deductible"] = TAX_DEDUCTIBLE.get(cat, True)

    for field, value in update.items():
        setattr(e, field, value)

    try:
        e.updated_at = datetime.now(timezone.utc)  # type: ignore
        await db.commit()
        await db.refresh(e)
        return _serialize(e)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Database error in update_expense: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# ── DELETE /expenses/{id} ─────────────────────────────────────────────────────

@router.delete("/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)
    e =await db.execute(select(Expense).where(
        Expense.id == expense_id,
        Expense.business_id == biz.id,
    ))
    e = e.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    try:
        await db.delete(e)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Database error in delete_expense: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
