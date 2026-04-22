"""
Reminder Pydantic Schemas
Location: app/schemas/reminder.py
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
import uuid


# ── Reminder Rule Schemas ─────────────────────────────────────────────────────

class ReminderRuleCreate(BaseModel):
    name:                  str  = Field(..., min_length=1, max_length=100,
                                        description="e.g. '7-day overdue chase'")
    days_overdue:          int  = Field(..., ge=1, le=365,
                                        description="Send when invoice is this many days past due date")
    cooldown_days:         int  = Field(7, ge=1, le=365,
                                        description="Don't re-send this reminder for this many days")
    is_active:             bool = Field(True)
    custom_message:        Optional[str] = Field(None, max_length=500)
    send_copy_to_business: bool = Field(False,
                                        description="CC the business email on every reminder")


class ReminderRuleUpdate(BaseModel):
    name:                  Optional[str]  = Field(None, min_length=1, max_length=100)
    days_overdue:          Optional[int]  = Field(None, ge=1, le=365)
    cooldown_days:         Optional[int]  = Field(None, ge=1, le=365)
    is_active:             Optional[bool] = None
    custom_message:        Optional[str]  = Field(None, max_length=500)
    send_copy_to_business: Optional[bool] = None


class ReminderRuleResponse(BaseModel):
    id:                    uuid.UUID
    business_id:           uuid.UUID
    name:                  str
    days_overdue:          int
    cooldown_days:         int
    is_active:             bool
    custom_message:        Optional[str]
    send_copy_to_business: bool
    created_at:            datetime
    updated_at:            datetime

    class Config:
        from_attributes = True


# ── Reminder Log Schemas ──────────────────────────────────────────────────────

class ReminderLogResponse(BaseModel):
    id:              uuid.UUID
    invoice_id:      uuid.UUID
    invoice_number:  str
    customer_name:   str
    recipient_email: str
    sent_at:         datetime
    days_overdue:    int
    rule_name:       str
    success:         bool
    error_message:   Optional[str]

    class Config:
        from_attributes = True


class ReminderLogListResponse(BaseModel):
    logs:        List[ReminderLogResponse]
    total:       int
    page:        int
    page_size:   int
    total_pages: int


# ── Trigger Result Schema ─────────────────────────────────────────────────────

class ReminderTriggerResult(BaseModel):
    sent:    int
    skipped: int
    errors:  int
    details: List[dict]


# ── Preview Schema ────────────────────────────────────────────────────────────

class ReminderPreviewInvoice(BaseModel):
    invoice_number: str
    customer_name:  str
    customer_email: Optional[str]
    days_overdue:   int
    outstanding:    str
    rule:           str
    has_email:      bool


class ReminderPreviewResponse(BaseModel):
    invoices: List[ReminderPreviewInvoice]
    count:    int
    message:  Optional[str] = None