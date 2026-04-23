"""
Payment Reminders Endpoint (ASYNC + OPTIMIZED + PRODUCTION-GRADE)
"""

from time import timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime, timedelta
import uuid
import logging
import asyncio

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.core.email import send_email_smtp

from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment_link import PaymentLink
from app.models.customer import Customer
from app.models.reminder import ReminderRule, ReminderLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reminders", tags=["Reminders"])


# ── BACKGROUND EMAIL ─────────────────────────────────────

async def send_email_async(to_email, subject, html_body, cc_email=None):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            send_email_smtp,
            to_email,
            subject,
            html_body,
            cc_email
        )
        return True, None
    except Exception as e:
        return False, str(e)


# ── HELPERS ─────────────────────────────────────────────

async def _get_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalar_one_or_none()

    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")

    return biz


def _fmt_ngn(amount) -> str:
    try:
        return f"₦{float(amount):,.0f}"
    except:
        return "₦0"


def _days_overdue(invoice: Invoice) -> int:
    if not invoice.due_date: # type: ignore
        return 0
    return max(0, (date.today() - invoice.due_date).days)


# ⚠️ KEEP YOUR ORIGINAL IMPLEMENTATION HERE
def _build_reminder_email(invoice, customer, business, rule, days_overdue, pay_url=None):
    ...
    

# ── SCHEMAS (UNCHANGED) ─────────────────────────────────

class ReminderRuleCreate(BaseModel):
    name: str
    days_overdue: int
    is_active: bool = True
    custom_message: Optional[str] = None
    send_copy_to_business: bool = False


class ReminderRuleUpdate(BaseModel):
    name: Optional[str] = None
    days_overdue: Optional[int] = None
    is_active: Optional[bool] = None
    custom_message: Optional[str] = None
    send_copy_to_business: Optional[bool] = None


# ── RULES ───────────────────────────────────────────────

@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    result = await db.execute(
        select(ReminderRule)
        .where(ReminderRule.business_id == business.id)
        .order_by(ReminderRule.days_overdue)
    )
    return result.scalars().all()


@router.post("/rules", status_code=201)
async def create_rule(data: ReminderRuleCreate,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    count = (await db.execute(
        select(func.count()).select_from(ReminderRule)
        .where(ReminderRule.business_id == business.id)
    )).scalar_one()

    if count >= 10:
        raise HTTPException(status_code=400, detail="Max 10 rules")

    rule = ReminderRule(
        id=uuid.uuid4(),
        business_id=business.id,
        **data.model_dump()
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: uuid.UUID,
                      data: ReminderRuleUpdate,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    result = await db.execute(
        select(ReminderRule).where(
            ReminderRule.id == rule_id,
            ReminderRule.business_id == business.id,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)

    rule.updated_at = datetime.now(timezone.utc) # type: ignore

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    result = await db.execute(
        select(ReminderRule).where(
            ReminderRule.id == rule_id,
            ReminderRule.business_id == business.id,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()


# ── PREVIEW ─────────────────────────────────────────────

@router.get("/preview")
async def preview_reminders(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    rules = (await db.execute(
        select(ReminderRule).where(
            ReminderRule.business_id == business.id,
            ReminderRule.is_active == True
        )
    )).scalars().all()

    invoices = (await db.execute(
        select(Invoice).where(
            Invoice.business_id == business.id,
            Invoice.due_date < date.today(),
        )
    )).scalars().all()

    customer_ids = {i.customer_id for i in invoices}
    customers = (await db.execute(
        select(Customer).where(Customer.id.in_(customer_ids))
    )).scalars().all()

    customer_map = {c.id: c for c in customers}

    results = []

    for inv in invoices:
        days = _days_overdue(inv)
        matched = [r for r in rules if days >= r.days_overdue] # type: ignore
        if not matched:
            continue

        rule = max(matched, key=lambda r: r.days_overdue)
        customer = customer_map.get(inv.customer_id)

        results.append({
            "invoice_number": inv.invoice_number,
            "customer_name": customer.name if customer else "—",
            "days_overdue": days,
            "rule": rule.name,
        })

    return {"invoices": results, "count": len(results)}


# ── TRIGGER (FINAL FORM) ─────────────────────────────────

@router.post("/trigger")
async def trigger_reminders(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    rules = (await db.execute(
        select(ReminderRule).where(
            ReminderRule.business_id == business.id,
            ReminderRule.is_active == True
        )
    )).scalars().all()

    rule_map = {r.days_overdue: r for r in rules}

    invoices = (await db.execute(
        select(Invoice).where(
            Invoice.business_id == business.id,
            Invoice.due_date < date.today(),
        )
    )).scalars().all()

    customer_ids = {i.customer_id for i in invoices}
    customers = (await db.execute(
        select(Customer).where(Customer.id.in_(customer_ids))
    )).scalars().all()

    customer_map = {c.id: c for c in customers}

    sent = skipped = errors = 0

    async with db.begin():
        for inv in invoices:
            days = _days_overdue(inv)
            rule = rule_map.get(days) # type: ignore
            if not rule:
                continue

            customer = customer_map.get(inv.customer_id)
            if not customer or not customer.email: # type: ignore
                skipped += 1
                continue

            idem_key = f"{inv.id}:{rule.id}:{date.today()}"

            exists = await db.execute(
                select(ReminderLog).where(
                    ReminderLog.idempotency_key == idem_key # type: ignore
                )
            )
            if exists.scalar_one_or_none():
                skipped += 1
                continue

            subject, html = _build_reminder_email(
                inv, customer, business, rule, days
            ) # type: ignore

            log = ReminderLog(
                id=uuid.uuid4(),
                invoice_id=inv.id,
                business_id=business.id,
                rule_id=rule.id,
                idempotency_key=idem_key,
                status="pending",
                recipient_email=customer.email,
                sent_date=date.today(),
            )

            db.add(log)
            await db.flush()

            success, err = await send_email_async(
                customer.email, subject, html
            )

            if success:
                log.status = "sent" # type: ignore
                sent += 1
            else:
                log.status = "failed" # type: ignore
                log.error_message = err # type: ignore
                errors += 1

    return {"sent": sent, "skipped": skipped, "errors": errors}


# ── LOGS ───────────────────────────────────────────────

@router.get("/logs")
async def get_logs(page: int = Query(1),
                   page_size: int = Query(20),
                   db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    business = await _get_business(db, current_user)

    total = (await db.execute(
        select(func.count()).select_from(ReminderLog)
        .where(ReminderLog.business_id == business.id)
    )).scalar_one()

    logs = (await db.execute(
        select(ReminderLog)
        .where(ReminderLog.business_id == business.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {"logs": logs, "total": total}