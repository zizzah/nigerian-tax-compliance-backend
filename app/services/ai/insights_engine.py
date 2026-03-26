"""
AI Insights Engine
Location: app/services/ai/insights_engine.py

Analyzes business financial data and generates proactive insights using Groq.
Called on dashboard load. Falls back to rule-based insights if Groq fails.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

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

    def generate_insights(self, db: Session, business: Business) -> list[AIInsight]:
        """
        Main entry point. Gathers financial metrics, sends to Groq,
        parses response, saves insights to DB, returns list.
        """
        try:
            metrics = self._gather_metrics(db, business)
            raw_insights = self._call_groq(metrics, business)
            saved = self._save_insights(db, business, raw_insights, metrics)
            return saved
        except Exception as e:
            logger.error(f"InsightsEngine failed for business {business.id}: {e}", exc_info=True)
            return []

    def _gather_metrics(self, db: Session, business: Business) -> dict[str, Any]:
        """Gather all financial metrics needed for analysis."""
        today = date.today()
        bid = business.id

        # --- Invoice metrics ---
        invoices_30d = db.query(Invoice).filter(
            Invoice.business_id == bid,
            Invoice.issue_date >= today - timedelta(days=30),
            Invoice.status != InvoiceStatus.CANCELLED, # type: ignore
        ).all()

        overdue = db.query(Invoice).filter(
            Invoice.business_id == bid,
            Invoice.status.in_([InvoiceStatus.OVERDUE, InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), # type: ignore
            Invoice.due_date.isnot(None),
            Invoice.due_date < today,
        ).all()

        # --- Payment timing per customer (last 180 days) ---
        paid_invoices = db.query(Invoice).filter(
            Invoice.business_id == bid,
            Invoice.status == InvoiceStatus.PAID, # type: ignore
            Invoice.paid_at.isnot(None), # type: ignore
            Invoice.paid_at >= datetime.now(timezone.utc) - timedelta(days=180), # type: ignore
        ).all()

        customer_payment_days: dict[str, list[int]] = {}
        for inv in paid_invoices:
            if inv.paid_at and inv.issue_date: # type: ignore
                days = (inv.paid_at.date() - inv.issue_date).days
                cid = str(inv.customer_id)
                customer_payment_days.setdefault(cid, []).append(days)

        # --- Revenue: last 30d vs prev 30d ---
        revenue_30d = float(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.business_id == bid,
            Payment.payment_date >= today - timedelta(days=30),
        ).scalar() or 0)

        revenue_prev_30d = float(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.business_id == bid,
            Payment.payment_date >= today - timedelta(days=60),
            Payment.payment_date < today - timedelta(days=30),
        ).scalar() or 0)

        # --- YTD expenses ---
        ytd_expenses = float(db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.business_id == bid,
            extract('year', Expense.expense_date) == today.year,
        ).scalar() or 0)

        # --- Top customers (90d) ---
        top_customers = db.query(
            Customer.name,
            func.sum(Payment.amount).label('total'),
        ).join(Payment, Payment.customer_id == Customer.id).filter(
            Payment.business_id == bid,
            Payment.payment_date >= today - timedelta(days=90),
        ).group_by(Customer.id, Customer.name).order_by(
            func.sum(Payment.amount).desc()
        ).limit(5).all()

        # --- Overall avg payment days ---
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
                    "days_overdue": (today - inv.due_date).days if inv.due_date else 0, # type: ignore
                    "customer_id": str(inv.customer_id),
                }
                for inv in overdue[:10]
            ],
            "revenue_30d": revenue_30d,
            "revenue_prev_30d": revenue_prev_30d,
            "revenue_change_pct": round(
                ((revenue_30d - revenue_prev_30d) / revenue_prev_30d * 100) if revenue_prev_30d > 0 else 0, 1
            ),
            "avg_payment_days": overall_avg_days,
            "customer_payment_days": {
                cid: round(sum(v) / len(v), 1) for cid, v in customer_payment_days.items()
            },
            "ytd_expenses": ytd_expenses,
            "top_customers": [{"name": r.name, "revenue_90d": float(r.total)} for r in top_customers],
            "invoices_30d_count": len(invoices_30d),
        }

    def _call_groq(self, metrics: dict, business: Business) -> list[dict]:
        """Send metrics to Groq and get back structured insights."""
        prompt = f"""You are a financial intelligence system for Nigerian SMEs.
Analyze this business's financial metrics and generate 3-6 specific, actionable insights.

METRICS:
{json.dumps(metrics, indent=2)}

Generate insights as a JSON array. Each insight must have:
{{
  "insight_type": "cash_flow" | "overdue_risk" | "customer_behavior" | "revenue_trend" | "anomaly" | "positive",
  "severity": "info" | "warning" | "critical" | "positive",
  "title": "Short punchy title (max 60 chars)",
  "body": "2-3 sentences with specific numbers from the data. Be direct and actionable.",
  "action_label": "Button text (max 30 chars, or null)",
  "action_url": "/dashboard/path or null"
}}

Rules:
- Use actual numbers from the metrics (₦ amounts, percentages, days)
- critical = requires immediate action (e.g. >30 days overdue debt)
- warning = needs attention soon
- positive = celebrate good news
- info = useful context
- ONLY return the JSON array, nothing else
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = response.choices[0].message.content or "[]"
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Groq insights call failed: {e}")
            return self._generate_rule_based_insights(metrics)

    def _generate_rule_based_insights(self, metrics: dict) -> list[dict]:
        """Fallback rule-based insights if Groq fails."""
        insights = []
        if metrics["overdue_amount"] > 0:
            insights.append({
                "insight_type": "overdue_risk",
                "severity": "critical" if metrics["overdue_amount"] > 500000 else "warning",
                "title": f"₦{metrics['overdue_amount']:,.0f} in overdue invoices",
                "body": (
                    f"You have {metrics['overdue_count']} overdue invoices totalling "
                    f"₦{metrics['overdue_amount']:,.0f}. Send reminders to recover this revenue."
                ),
                "action_label": "View Overdue",
                "action_url": "/invoices?status=OVERDUE",
            })
        if metrics["revenue_change_pct"] < -20:
            insights.append({
                "insight_type": "revenue_trend",
                "severity": "warning",
                "title": f"Revenue down {abs(metrics['revenue_change_pct'])}% this month",
                "body": (
                    f"Revenue this month (₦{metrics['revenue_30d']:,.0f}) is "
                    f"{abs(metrics['revenue_change_pct'])}% lower than last month "
                    f"(₦{metrics['revenue_prev_30d']:,.0f})."
                ),
                "action_label": "View Analytics",
                "action_url": "/analytics",
            })
        if metrics["revenue_change_pct"] > 20:
            insights.append({
                "insight_type": "positive",
                "severity": "positive",
                "title": f"Revenue up {metrics['revenue_change_pct']}% this month! 🎉",
                "body": (
                    f"Great performance! This month's revenue (₦{metrics['revenue_30d']:,.0f}) "
                    f"is {metrics['revenue_change_pct']}% higher than last month."
                ),
                "action_label": None,
                "action_url": None,
            })
        return insights

    def _save_insights(
        self, db: Session, business: Business, raw_insights: list[dict], metrics: dict
    ) -> list[AIInsight]:
        """
        Delete today's existing insights for this business and save fresh ones.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        db.query(AIInsight).filter(
            AIInsight.business_id == business.id,
            AIInsight.created_at >= today_start,
            AIInsight.is_dismissed == False,
        ).delete(synchronize_session=False)

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
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                )
                db.add(insight)
                saved.append(insight)
            except Exception as e:
                logger.warning(f"Failed to save insight: {e}")
        db.commit()
        return saved