"""
Payment Reminders Endpoint
Location: app/api/v1/endpoints/reminders.py

Provides:
  GET    /reminders/rules              — list this business's reminder rules
  POST   /reminders/rules              — create a rule
  PUT    /reminders/rules/{rule_id}    — update a rule
  DELETE /reminders/rules/{rule_id}    — delete a rule
  POST   /reminders/trigger            — run due reminders NOW (call from cron or manually)
  GET    /reminders/logs               — paginated history of sent reminders
  GET    /reminders/preview            — which invoices WOULD be chased right now
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import and_  # type: ignore
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime, timedelta
import uuid
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.core.email import send_email_smtp
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment_link import PaymentLink
from app.models.customer import Customer
from app.models.reminder import ReminderRule, ReminderLog  # new models below

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reminders", tags=["Reminders"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_business(db: Session, user: User) -> Business:
    from app.models.business import Business as Biz
    biz = db.query(Biz).filter(Biz.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz  # type: ignore


def _fmt_ngn(amount) -> str:
    try:
        return f"₦{float(amount):,.0f}"
    except (TypeError, ValueError):
        return "₦0"


def _days_overdue(invoice: Invoice) -> int:
    if not invoice.due_date: # type: ignore
        return 0
    delta = date.today() - invoice.due_date
    return max(0, delta.days)


def _build_reminder_email(
    invoice: Invoice,
    customer: Customer,
    business: Business,
    rule: "ReminderRule",
    days_overdue: int,
    pay_url: Optional[str] = None,
) -> tuple[str, str]:
    """Returns (subject, html_body)"""
    primary   = str(getattr(business, 'primary_color',   None) or '#c8952a')
    biz_name  = str(business.business_name or 'Your Supplier')
    cus_name  = str(customer.name or 'Valued Customer')
    inv_num   = str(invoice.invoice_number or '')
    amount    = _fmt_ngn(invoice.outstanding_amount) 
    due_str   = invoice.due_date.strftime('%d %B %Y') if invoice.due_date else '—' # type: ignore

    urgency_label = (
        "Friendly Reminder" if days_overdue <= 7
        else "Payment Overdue" if days_overdue <= 30
        else "URGENT: Payment Required"
    )

    custom_msg_block = ""
    if rule.custom_message: # type: ignore
        custom_msg_block = f"""
        <p style="margin:0 0 16px;font-size:14px;color:#2c2a24;line-height:1.6;
                  font-style:italic;border-left:3px solid {primary};padding-left:12px;">
          {rule.custom_message}
        </p>"""

    subject = f"{urgency_label}: Invoice {inv_num} — {amount} overdue"

    pay_button_block = ""
    if pay_url:
        pay_button_block = f"""
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
            <tr><td align="center">
              <a href="{pay_url}"
                 style="display:inline-block;padding:14px 36px;background:{primary};
                        color:#fff;font-size:15px;font-weight:700;text-decoration:none;
                        border-radius:8px;letter-spacing:0.3px;">
                Pay {amount} Now
              </a>
            </td></tr>
          </table>
          <p style="margin:8px 0 0;font-size:11px;color:#9e9990;text-align:center;">
            Or copy this link: {pay_url}
          </p>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><title>{subject}</title></head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f0;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;background:#fff;border-radius:12px;
                    overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#0f0e0b;padding:24px 32px;">
            <span style="font-family:Georgia,serif;font-size:20px;font-weight:700;
                         color:{primary};">{biz_name}</span>
            <span style="float:right;font-size:11px;color:#9e9990;
                         text-transform:uppercase;letter-spacing:1px;line-height:30px;">
              Payment Reminder
            </span>
          </td>
        </tr>

        <!-- Urgency banner -->
        <tr>
          <td style="background:{primary};padding:12px 32px;text-align:center;">
            <span style="font-size:13px;font-weight:700;color:#fff;
                         text-transform:uppercase;letter-spacing:1px;">
              {urgency_label} · {days_overdue} day{'s' if days_overdue != 1 else ''} overdue
            </span>
          </td>
        </tr>

        <!-- Body -->
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:20px;color:#0f0e0b;">
            Dear {cus_name},
          </h2>
          <p style="margin:0 0 20px;font-size:14px;color:#6b6560;">
            This is a reminder that the following invoice remains unpaid.
          </p>

          {custom_msg_block}

          <!-- Invoice summary -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#faf9f6;border:1px solid #ede9de;
                        border-radius:10px;margin-bottom:24px;">
            <tr><td style="padding:20px 24px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-size:11px;color:#9e9990;padding-bottom:4px;
                             text-transform:uppercase;letter-spacing:0.5px;">Invoice #</td>
                  <td style="font-size:11px;color:#9e9990;padding-bottom:4px;
                             text-align:right;text-transform:uppercase;letter-spacing:0.5px;">Due Date</td>
                </tr>
                <tr>
                  <td style="font-size:15px;font-weight:600;color:#0f0e0b;
                             padding-bottom:16px;">{inv_num}</td>
                  <td style="font-size:14px;color:#b83232;font-weight:600;
                             padding-bottom:16px;text-align:right;">{due_str}</td>
                </tr>
                <tr>
                  <td colspan="2" style="border-top:1px solid #ede9de;padding-top:16px;">
                    <table width="100%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="font-size:13px;color:#9e9990;">Amount Outstanding</td>
                        <td style="font-size:22px;font-weight:700;color:{primary};
                                   text-align:right;">{amount}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td></tr>
          </table>

          <p style="margin:0 0 24px;font-size:13px;color:#6b6560;">
            Please arrange payment at your earliest convenience. If you have already
            made payment, kindly disregard this reminder.
          </p>

          {pay_button_block}
        </td></tr>

        <!-- Footer -->
        <tr>
          <td style="background:#faf9f6;padding:16px 32px;border-top:1px solid #ede9de;
                     text-align:center;font-size:11px;color:#9e9990;">
            Sent by {biz_name} via TaxFlow NG
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReminderRuleCreate(BaseModel):
    name:           str   = Field(..., min_length=1, max_length=100,
                                  description="e.g. '7-day overdue chase'")
    days_overdue:   int   = Field(..., ge=1, le=365,
                                  description="Send when invoice is this many days past due")
    is_active:      bool  = Field(True)
    custom_message: Optional[str] = Field(None, max_length=500)
    send_copy_to_business: bool = Field(False,
                                        description="Also CC the business email")


class ReminderRuleUpdate(BaseModel):
    name:           Optional[str]  = Field(None, min_length=1, max_length=100)
    days_overdue:   Optional[int]  = Field(None, ge=1, le=365)
    is_active:      Optional[bool] = None
    custom_message: Optional[str]  = Field(None, max_length=500)
    send_copy_to_business: Optional[bool] = None


class ReminderRuleResponse(BaseModel):
    id:             uuid.UUID
    business_id:    uuid.UUID
    name:           str
    days_overdue:   int
    is_active:      bool
    custom_message: Optional[str]
    send_copy_to_business: bool
    created_at:     datetime
    updated_at:     datetime

    class Config:
        from_attributes = True


class ReminderLogResponse(BaseModel):
    id:             uuid.UUID
    invoice_id:     uuid.UUID
    invoice_number: str
    customer_name:  str
    recipient_email: str
    sent_at:        datetime
    days_overdue:   int
    rule_name:      str
    success:        bool
    error_message:  Optional[str]

    class Config:
        from_attributes = True


class TriggerResult(BaseModel):
    sent:    int
    skipped: int
    errors:  int
    details: List[dict]


# ── GET /reminders/rules ──────────────────────────────────────────────────────

@router.get("/rules", response_model=List[ReminderRuleResponse])
def list_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business(db, current_user)
    rules = (
        db.query(ReminderRule)
        .filter(ReminderRule.business_id == business.id)
        .order_by(ReminderRule.days_overdue)
        .all()
    )
    return rules


# ── POST /reminders/rules ─────────────────────────────────────────────────────

@router.post("/rules", response_model=ReminderRuleResponse,
             status_code=status.HTTP_201_CREATED)
def create_rule(
    data: ReminderRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business(db, current_user)

    # Max 10 rules per business
    count = db.query(ReminderRule).filter(
        ReminderRule.business_id == business.id
    ).count()
    if count >= 10:
        raise HTTPException(status_code=400,
            detail="Maximum 10 reminder rules per business")

    rule = ReminderRule(
        id=uuid.uuid4(),
        business_id=business.id,
        name=data.name,
        days_overdue=data.days_overdue,
        is_active=data.is_active,
        custom_message=data.custom_message,
        send_copy_to_business=data.send_copy_to_business,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ── PUT /reminders/rules/{rule_id} ────────────────────────────────────────────

@router.put("/rules/{rule_id}", response_model=ReminderRuleResponse)
def update_rule(
    rule_id: uuid.UUID,
    data: ReminderRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business(db, current_user)
    rule = db.query(ReminderRule).filter(
        ReminderRule.id == rule_id,
        ReminderRule.business_id == business.id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, val)
    setattr(rule, 'updated_at', datetime.utcnow())
    db.commit()
    db.refresh(rule)
    return rule


# ── DELETE /reminders/rules/{rule_id} ─────────────────────────────────────────

@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business(db, current_user)
    rule = db.query(ReminderRule).filter(
        ReminderRule.id == rule_id,
        ReminderRule.business_id == business.id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


# ── GET /reminders/preview ────────────────────────────────────────────────────

@router.get("/preview")
def preview_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns invoices that WOULD receive a reminder if trigger is run now."""
    business = _get_business(db, current_user)
    rules = (
        db.query(ReminderRule)
        .filter(ReminderRule.business_id == business.id,
                ReminderRule.is_active == True)  # noqa: E712
        .order_by(ReminderRule.days_overdue)
        .all()
    )
    if not rules:
        return {"invoices": [], "message": "No active reminder rules configured"}

    unpaid = (
        db.query(Invoice)
        .filter(
            Invoice.business_id == business.id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE, # type: ignore
                                 InvoiceStatus.PARTIALLY_PAID]),
            Invoice.due_date < date.today(),
        )
        .all()
    )

    results = []
    for inv in unpaid:
        days = _days_overdue(inv)
        # Match any rule where the invoice is at least that many days overdue
        matched = [r for r in rules if days >= r.days_overdue] # type: ignore
        if not matched:
            continue
        # Use the most specific (highest days_overdue) matching rule
        rule = max(matched, key=lambda r: r.days_overdue)
        customer = db.query(Customer).filter(
            Customer.id == inv.customer_id
        ).first()
        # Check cooldown
        cooldown = int(rule.cooldown_days or 7) # type: ignore
        cooldown_since = date.today() - timedelta(days=cooldown - 1)
        already_sent = db.query(ReminderLog).filter(
            ReminderLog.invoice_id == inv.id,
            ReminderLog.rule_id    == rule.id,
            ReminderLog.sent_date  >= cooldown_since,
            ReminderLog.success    == True,
        ).first()
        results.append({
            "invoice_number": inv.invoice_number,
            "customer_name":  customer.name if customer else "—",
            "customer_email": customer.email if customer else None,
            "days_overdue":   days,
            "outstanding":    str(inv.outstanding_amount),
            "rule":           f"{rule.name} (cooldown: {cooldown}d)",
            "has_email":      bool(customer and customer.email),
            "on_cooldown":    bool(already_sent),
        })

    return {"invoices": results, "count": len(results)}


# ── POST /reminders/trigger ───────────────────────────────────────────────────

@router.post("/trigger", response_model=TriggerResult)
def trigger_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run all active reminder rules for this business right now.
    Call this endpoint from a daily cron job, or manually from the UI.
    Each invoice only gets ONE reminder per day (deduped via ReminderLog).
    """
    business = _get_business(db, current_user)

    rules = (
        db.query(ReminderRule)
        .filter(ReminderRule.business_id == business.id,
                ReminderRule.is_active == True)  # noqa: E712
        .all()
    )
    if not rules:
        return TriggerResult(sent=0, skipped=0, errors=0,
                             details=[{"info": "No active rules"}])

    # days_overdue → rule map (highest priority = most overdue)
    rule_map: dict[int, ReminderRule] = {r.days_overdue: r for r in rules} # type: ignore

    unpaid = (
        db.query(Invoice)
        .filter(
            Invoice.business_id == business.id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE, # type: ignore
                                 InvoiceStatus.PARTIALLY_PAID]),
            Invoice.due_date < date.today(),
        )
        .all()
    )

    sent = skipped = errors = 0
    details = []
    today = date.today()

    for inv in unpaid:
        days = _days_overdue(inv)
        rule = rule_map.get(days)
        if not rule:
            continue

        customer = db.query(Customer).filter(
            Customer.id == inv.customer_id
        ).first()

        if not customer or not customer.email: # type: ignore
            skipped += 1
            details.append({
                "invoice": str(inv.invoice_number),
                "status":  "skipped",
                "reason":  "No customer email",
            })
            continue

        # Cooldown dedup: don't re-send if already sent within cooldown_days
        cooldown = int(rule.cooldown_days or 7) # type: ignore
        cooldown_since = today - timedelta(days=cooldown - 1)
        already_sent = db.query(ReminderLog).filter(
            ReminderLog.invoice_id == inv.id,
            ReminderLog.rule_id    == rule.id,
            ReminderLog.sent_date  >= cooldown_since,
            ReminderLog.success    == True,
        ).first()

        if already_sent:
            skipped += 1
            details.append({
                "invoice": str(inv.invoice_number),
                "status":  "skipped",
                "reason":  f"Already sent within cooldown ({cooldown}d)",
            })
            continue

        # Build and send email
        # Look up payment link for this invoice (if any)
        pay_link_row = db.query(PaymentLink).filter(
            PaymentLink.invoice_id == inv.id,
            PaymentLink.is_active  == True,   # noqa: E712
        ).first()
        frontend_url = getattr(settings, 'FRONTEND_URL', '')
        pay_url = f"{frontend_url}/pay/{pay_link_row.token}" if pay_link_row and frontend_url else None

        subject, html = _build_reminder_email(inv, customer, business, rule, days, pay_url=pay_url)
        cc = str(business.email) if rule.send_copy_to_business and business.email else None # type: ignore

        log = ReminderLog(
            id=uuid.uuid4(),
            invoice_id=inv.id,
            business_id=business.id,
            rule_id=rule.id,
            rule_name=str(rule.name),
            invoice_number=str(inv.invoice_number),
            customer_name=str(customer.name),
            recipient_email=str(customer.email),
            sent_date=today,
            sent_at=datetime.utcnow(),
            days_overdue=days,
            success=False,
            error_message=None,
        )

        try:
            send_email_smtp(
                to_email=str(customer.email),
                subject=subject,
                html_body=html,
                cc_email=cc,
            )
            setattr(log, 'success', True)
            sent += 1
            details.append({
                "invoice":  str(inv.invoice_number),
                "customer": str(customer.name),
                "email":    str(customer.email),
                "status":   "sent",
                "rule":     str(rule.name),
            })
            logger.info(f"Reminder sent: {inv.invoice_number} → {customer.email}")
        except Exception as e:
            setattr(log, 'error_message', str(e))
            errors += 1
            details.append({
                "invoice": str(inv.invoice_number),
                "status":  "error",
                "reason":  str(e),
            })
            logger.error(f"Reminder failed: {inv.invoice_number} → {e}")

        db.add(log)

    db.commit()
    return TriggerResult(sent=sent, skipped=skipped, errors=errors, details=details)


# ── GET /reminders/logs ───────────────────────────────────────────────────────

@router.get("/logs")
def get_reminder_logs(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business(db, current_user)
    q = (
        db.query(ReminderLog)
        .filter(ReminderLog.business_id == business.id)
        .order_by(ReminderLog.sent_at.desc())
    )
    total = q.count()
    logs  = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "logs":       logs,
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "total_pages": max(1, -(-total // page_size)),
    }