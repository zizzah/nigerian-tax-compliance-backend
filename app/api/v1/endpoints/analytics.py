"""
Analytics API Endpoints
Location: app/api/v1/endpoints/analytics.py

Provides aggregated dashboard statistics from invoices, payments, and customers.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import select
from sqlalchemy import func, extract
from datetime import date,  timedelta
import uuid
import logging

from sqlalchemy import text
from fastapi import HTTPException, status

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.expense import Expense
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _empty_dashboard_payload() -> dict:
    """Return a safe empty dashboard for newly registered users without a business profile."""
    return {
        "total_invoices": 0,
        "draft_count": 0,
        "sent_count": 0,
        "paid_count": 0,
        "overdue_count": 0,
        "cancelled_count": 0,
        "partially_paid_count": 0,
        "total_invoiced": 0.0,
        "total_collected": 0.0,
        "total_outstanding": 0.0,
        "overdue_amount": 0.0,
        "total_expenses": 0.0,
        "cogs": 0.0,
        "net_profit": 0.0,
        "profit_margin": 0.0,
        "health": "no_data",
        "active_customers": 0,
        "revenue_by_month": [],
        "recent_invoices": [],
        "recent_payments": [],
    }


async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    result  = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalars().first()
    if not business:
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    return business


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(Business).where(Business.user_id == current_user.id))
        business = result.scalars().first()
        if not business:
            return _empty_dashboard_payload()
        bid = business.id

        # ------------------------------------------------------------------ #
        # 0. Auto-mark stale invoices as OVERDUE                               #
        # ------------------------------------------------------------------ #
        stale = await db.execute(select(Invoice).where(
            Invoice.business_id == bid,
            Invoice.due_date < date.today(),
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]),  # type: ignore
        ))
        stale = stale.scalars().all()
        if stale:
            for inv in stale:
                inv.status = InvoiceStatus.OVERDUE  # type: ignore
            await db.commit()

        # ------------------------------------------------------------------ #
        # 1. Invoice counts & amounts                                          #
        # ------------------------------------------------------------------ #
        result = await db.execute(
            select(
                Invoice.status,  # type: ignore
                func.count(Invoice.id).label("cnt"),
                func.coalesce(func.sum(Invoice.total_amount), 0).label("total"),
                func.coalesce(func.sum(Invoice.paid_amount), 0).label("paid"),
                func.coalesce(func.sum(Invoice.outstanding_amount), 0).label("outstanding"),
            )  # type: ignore
            .where(Invoice.business_id == bid)
            .group_by(Invoice.status)
        )
        inv_rows = result.all()  # type: ignore

        counts = {
            "DRAFT": 0, "SENT": 0, "PAID": 0,
            "OVERDUE": 0, "CANCELLED": 0, "PARTIALLY_PAID": 0,
        }
        total_invoiced    = 0.0
        total_collected   = 0.0
        total_outstanding = 0.0
        overdue_amount    = 0.0

        for row in inv_rows:
            key = row.status.value if hasattr(row.status, "value") else str(row.status)
            counts[key]        = int(row.cnt)
            total_invoiced    += float(row.total)
            total_collected   += float(row.paid)
            total_outstanding += float(row.outstanding)
            if key == "OVERDUE":
                overdue_amount = float(row.outstanding)

        total_invoices = sum(counts.values())

        # ------------------------------------------------------------------ #
        # 1b. True overdue                                                     #
        # ------------------------------------------------------------------ #
        today_date = date.today()
        true_overdue_result = await db.execute(
            select(
                func.count(Invoice.id).label("cnt"),
                func.coalesce(func.sum(Invoice.outstanding_amount), 0).label("outstanding"),
            )
            .where(
                Invoice.business_id == bid,
                Invoice.due_date < today_date,
                Invoice.status.in_([  # type: ignore
                    InvoiceStatus.SENT,
                    InvoiceStatus.OVERDUE,
                    InvoiceStatus.PARTIALLY_PAID,
                ]),
            )
        )
        true_overdue_row    = true_overdue_result.first()
        true_overdue_count  = int(true_overdue_row.cnt or 0)  # type: ignore
        true_overdue_amount = float(true_overdue_row.outstanding or 0)  # type: ignore

        counts["OVERDUE"] = true_overdue_count
        overdue_amount    = true_overdue_amount

        # ------------------------------------------------------------------ #
        # 1c. Expense totals                                                   #
        # ------------------------------------------------------------------ #
        current_year = date.today().year
        expense_result = await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(
                Expense.business_id == bid,
                extract('year', Expense.expense_date) == current_year,
            )
        )
        expense_total = float(expense_result.scalar() or 0)

        today     = date.today()
        ytd_start = date(current_year, 1, 1)
        try:
            cogs_result = await db.execute(
                text("""
                    SELECT COALESCE(SUM(
                        CAST(ii.quantity AS FLOAT) * CAST(p.cost_price AS FLOAT)
                    ), 0)
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
                {"biz_id": str(bid), "start_date": ytd_start, "end_date": today}
            )
            cogs_total = float(cogs_result.scalar() or 0)
        except Exception:
            cogs_total = 0.0

        net_profit = total_collected - cogs_total - expense_total

        # ------------------------------------------------------------------ #
        # 2. Customer count                                                    #
        # ------------------------------------------------------------------ #
        customer_result  = await db.execute(
            select(func.count(Customer.id))
            .where(Customer.business_id == bid, Customer.is_active == True)
        )
        active_customers = int(customer_result.scalar() or 0)

        # ------------------------------------------------------------------ #
        # 3. Revenue by month                                                  #
        # ------------------------------------------------------------------ #
        today          = date.today()
        six_months_ago = today.replace(day=1) - timedelta(days=150)

        monthly_result = await db.execute(
            select(
                extract('year',  Payment.payment_date).label("yr"),
                extract('month', Payment.payment_date).label("mo"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
                func.count(Payment.id).label("count"),
            ).where(
                Payment.business_id == bid,
                Payment.payment_date >= six_months_ago,
                Payment.payment_date <= today,
            ).group_by("yr", "mo")
        )
        monthly_payments = monthly_result.all()

        month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                       "Jul","Aug","Sep","Oct","Nov","Dec"]

        payment_map: dict[tuple[int, int], dict] = {
            (int(r.yr), int(r.mo)): {
                "revenue": float(r.revenue),
                "count":   int(r.count),  # type: ignore
            }
            for r in monthly_payments
        }

        revenue_by_month = []
        for i in range(5, -1, -1):
            target = (today.replace(day=1) - timedelta(days=i * 30))
            yr, mo = target.year, target.month
            data   = payment_map.get((yr, mo), {"revenue": 0.0, "count": 0})
            revenue_by_month.append({
                "month":   month_names[mo - 1],
                "year":    yr,
                "revenue": data["revenue"],
                "count":   data["count"],
            })

        # ------------------------------------------------------------------ #
        # 4. Recent invoices                                                   #
        # ------------------------------------------------------------------ #
        recent_invoice_result = await db.execute(
            select(Invoice, Customer.name.label("customer_name"))
            .join(Customer, Invoice.customer_id == Customer.id, isouter=True)
            .where(Invoice.business_id == bid)
            .order_by(Invoice.created_at.desc())
            .limit(5)
        )
        recent_invoice_rows = recent_invoice_result.all()

        recent_invoices = [
            {
                "id":                 str(inv.id),
                "invoice_number":     inv.invoice_number,
                "customer_name":      cust_name or "—",
                "total_amount":       float(inv.total_amount),
                "outstanding_amount": float(inv.outstanding_amount),
                "status":             inv.status.value if hasattr(inv.status, "value") else str(inv.status),
                "issue_date":         inv.issue_date.isoformat() if inv.issue_date else None,
                "due_date":           inv.due_date.isoformat()   if inv.due_date   else None,
            }
            for inv, cust_name in recent_invoice_rows
        ]

        # ------------------------------------------------------------------ #
        # 5. Recent payments                                                   #
        # ------------------------------------------------------------------ #
        recent_payment_result = await db.execute(
            select(Payment, Customer.name.label("customer_name"))
            .join(Customer, Payment.customer_id == Customer.id, isouter=True)
            .where(Payment.business_id == bid)
            .order_by(Payment.payment_date.desc())
            .limit(5)
        )
        recent_payment_rows = recent_payment_result.all()

        recent_payments = [
            {
                "id":             str(pmt.id),
                "amount":         float(pmt.amount),
                "payment_date":   pmt.payment_date.isoformat() if pmt.payment_date else None,
                "payment_method": pmt.payment_method.value if hasattr(pmt.payment_method, "value") else str(pmt.payment_method),
                "receipt_number": pmt.receipt_number,
                "customer_name":  cust_name or "—",
                "created_at":     pmt.created_at.isoformat() if pmt.created_at else None,
            }
            for pmt, cust_name in recent_payment_rows
        ]

        # ------------------------------------------------------------------ #
        # 6. Return                                                            #
        # ------------------------------------------------------------------ #
        return {
            "total_invoices":        total_invoices,
            "draft_count":           counts["DRAFT"],
            "sent_count":            counts["SENT"],
            "paid_count":            counts["PAID"],
            "overdue_count":         counts["OVERDUE"],
            "cancelled_count":       counts["CANCELLED"],
            "partially_paid_count":  counts.get("PARTIALLY_PAID", 0),
            "total_invoiced":        total_invoiced,
            "total_collected":       total_collected,
            "total_outstanding":     total_outstanding,
            "overdue_amount":        overdue_amount,
            "total_expenses":        expense_total,
            "cogs":                  round(cogs_total, 2),
            "net_profit":            round(net_profit, 2),
            "profit_margin":         round((net_profit / total_collected * 100), 1) if total_collected > 0 else 0,
            "health": (
                "no_data"       if total_collected == 0 else
                "healthy"       if (net_profit / total_collected) >= 0.20 else
                "stable"        if (net_profit / total_collected) >= 0.05 else
                "breaking_even" if net_profit >= 0 else
                "loss"
            ),
            "active_customers":   int(active_customers),
            "revenue_by_month":   revenue_by_month,
            "recent_invoices":    recent_invoices,
            "recent_payments":    recent_payments,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Dashboard error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load dashboard stats")
