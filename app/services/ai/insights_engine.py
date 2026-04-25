"""
AI Insights Engine (Async)
Location: app/services/ai/insights_engine.py
"""

import json
import logging
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, extract, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.ai_insight import AIInsight

logger = logging.getLogger(__name__)


class InsightsEngine:
    def __init__(self):
        from groq import Groq
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = "llama-3.3-70b-versatile"

    # ✅ MAIN ASYNC ENTRY
    async def generate_insights(
        self, db: AsyncSession, business: Business
    ) -> list[AIInsight]:
        try:
            metrics = await self._gather_metrics(db, business)
            raw_insights = await self._call_groq(metrics, business)
            saved = await self._save_insights(db, business, raw_insights, metrics)
            return saved
        except Exception as e:
            logger.error(
                f"InsightsEngine failed for business {business.id}: {e}",
                exc_info=True,
            )
            return []

    # ⚠️ OPTIONAL: TEMP SYNC WRAPPER (remove later)
    def generate_insights_sync(self, db: AsyncSession, business: Business):
        return asyncio.create_task(self.generate_insights(db, business))

    # -------------------------
    # METRICS
    # -------------------------
    async def _gather_metrics(
        self, db: AsyncSession, business: Business
    ) -> dict[str, Any]:
        today = date.today()
        bid = business.id

        # --- invoices 30d ---
        invoices_30d = (
            await db.execute(
                select(Invoice).where(
                    Invoice.business_id == bid,
                    Invoice.issue_date >= today - timedelta(days=30),
                    Invoice.status != InvoiceStatus.CANCELLED, # type: ignore
                )
            )
        ).scalars().all()

        # --- overdue ---
        overdue = (
            await db.execute(
                select(Invoice).where(
                    Invoice.business_id == bid,
                    Invoice.status.in_( # type: ignore
                        [
                            InvoiceStatus.OVERDUE,
                            InvoiceStatus.SENT,
                            InvoiceStatus.PARTIALLY_PAID,
                        ]
                    ),
                    Invoice.due_date.isnot(None),
                    Invoice.due_date < today,
                )
            )
        ).scalars().all()

        # --- paid invoices ---
        paid_invoices = (
            await db.execute(
                select(Invoice).where(
                    Invoice.business_id == bid,
                    Invoice.status == InvoiceStatus.PAID, # type: ignore
                    Invoice.paid_at.isnot(None), # type: ignore
                    Invoice.paid_at
                    >= datetime.now(timezone.utc) - timedelta(days=180), # type: ignore
                )
            )
        ).scalars().all()

        customer_payment_days: dict[str, list[int]] = {}
        for inv in paid_invoices:
            if inv.paid_at and inv.issue_date: # type: ignore
                days = (inv.paid_at.date() - inv.issue_date).days
                cid = str(inv.customer_id)
                customer_payment_days.setdefault(cid, []).append(days)

        # --- revenue ---
        revenue_30d = float(
            (
                await db.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.business_id == bid,
                        Payment.payment_date >= today - timedelta(days=30),
                    )
                )
            ).scalar_one()
        )

        revenue_prev_30d = float(
            (
                await db.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.business_id == bid,
                        Payment.payment_date >= today - timedelta(days=60),
                        Payment.payment_date < today - timedelta(days=30),
                    )
                )
            ).scalar_one()
        )

        # --- expenses ---
        ytd_expenses = float(
            (
                await db.execute(
                    select(func.coalesce(func.sum(Expense.amount), 0)).where(
                        Expense.business_id == bid,
                        extract("year", Expense.expense_date) == today.year,
                    )
                )
            ).scalar_one()
        )

        # --- top customers ---
        top_customers = (
            await db.execute(
                select(
                    Customer.name,
                    func.sum(Payment.amount).label("total"),
                )
                .join(Payment, Payment.customer_id == Customer.id)
                .where(
                    Payment.business_id == bid,
                    Payment.payment_date >= today - timedelta(days=90),
                )
                .group_by(Customer.id, Customer.name)
                .order_by(func.sum(Payment.amount).desc())
                .limit(5)
            )
        ).all()

        all_days = [d for days in customer_payment_days.values() for d in days]
        overall_avg_days = round(sum(all_days) / len(all_days), 1) if all_days else 0

        total_overdue = sum(float(inv.outstanding_amount or 0) for inv in overdue) # type: ignore

        return {
            "business_name": business.business_name,
            "today": today.isoformat(),
            "overdue_count": len(overdue),
            "overdue_amount": total_overdue,
            "overdue_invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "amount": float(inv.outstanding_amount or 0), # type: ignore
                    "days_overdue": (today - inv.due_date).days
                    if inv.due_date # type: ignore
                    else 0,
                    "customer_id": str(inv.customer_id),
                }
                for inv in overdue[:10]
            ],
            "revenue_30d": revenue_30d,
            "revenue_prev_30d": revenue_prev_30d,
            "revenue_change_pct": round(
                (
                    (revenue_30d - revenue_prev_30d)
                    / revenue_prev_30d
                    * 100
                )
                if revenue_prev_30d > 0
                else 0,
                1,
            ),
            "avg_payment_days": overall_avg_days,
            "customer_payment_days": {
                cid: round(sum(v) / len(v), 1)
                for cid, v in customer_payment_days.items()
            },
            "ytd_expenses": ytd_expenses,
            "top_customers": [
                {"name": r.name, "revenue_90d": float(r.total)}
                for r in top_customers
            ],
            "invoices_30d_count": len(invoices_30d),
        }

    # -------------------------
    # GROQ (NON-BLOCKING)
    # -------------------------
    async def _call_groq(self, metrics: dict, business: Business) -> list[dict]:
        loop = asyncio.get_running_loop()

        def _sync_call():
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": self._build_prompt(metrics)}],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = response.choices[0].message.content or "[]"
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw)

        try:
            return await loop.run_in_executor(None, _sync_call)
        except Exception as e:
            logger.error(f"Groq insights failed: {e}")
            return self._generate_rule_based_insights(metrics) # type: ignore

    def _build_prompt(self, metrics: dict) -> str:
        return f"""You are a financial intelligence system for Nigerian SMEs.

METRICS:
{json.dumps(metrics, indent=2)}

Return JSON array only (3-6 insights)."""

    # -------------------------
    # SAVE (TRANSACTION SAFE)
    # -------------------------
    async def _save_insights(
        self,
        db: AsyncSession,
        business: Business,
        raw_insights: list[dict],
        metrics: dict,
    ) -> list[AIInsight]:

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        async with db.begin_nested():

            await db.execute(
                delete(AIInsight).where(
                    AIInsight.business_id == business.id,
                    AIInsight.created_at >= today_start,
                    AIInsight.is_dismissed == False,
                )
            )

            saved = []

            for item in raw_insights[:6]:
                try:
                    insight = AIInsight(
                        business_id=business.id,
                        insight_type=item.get("insight_type", "info"),
                        severity=item.get("severity", "info"),
                        title=item.get("title", "")[:255],
                        body=item.get("body", ""),
                        action_label=item.get("action_label"),
                        action_url=item.get("action_url"),
                        data_snapshot=metrics,
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(hours=24),
                    )
                    db.add(insight)
                    saved.append(insight)
                except Exception as e:
                    logger.warning(f"Failed to save insight: {e}")

        return saved