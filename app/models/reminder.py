"""
Reminder Models
Location: app/models/reminder.py

ReminderRule  — business-defined rules (e.g. "chase at 7 days overdue")
ReminderLog   — history of every reminder email sent
"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Boolean, Text,
    DateTime, Date, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ReminderRule(Base):
    """
    A business's reminder rule.

    Example: name="7-day chase", days_overdue=7, cooldown_days=7
    When triggered, sends an email to every customer whose invoice is
    exactly `days_overdue` days past the due date (or more, if the
    endpoint uses >=).
    """
    __tablename__ = "reminder_rules"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name                  = Column(String(100), nullable=False)
    days_overdue          = Column(Integer,     nullable=False)          # trigger threshold
    cooldown_days         = Column(Integer,     nullable=False, default=7)
    is_active             = Column(Boolean,     nullable=False, default=True)
    custom_message        = Column(String(500), nullable=True)
    send_copy_to_business = Column(Boolean,     nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    business = relationship("Business")
    logs     = relationship("ReminderLog", back_populates="rule",
                            cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ReminderRule '{self.name}' {self.days_overdue}d>"


class ReminderLog(Base):
    """
    Audit record for every reminder email sent.
    Used to enforce the cooldown_days deduplication.
    """
    __tablename__ = "reminder_logs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id      = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id     = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id         = Column(
        UUID(as_uuid=True),
        ForeignKey("reminder_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalised for fast display without joins
    rule_name       = Column(String(100), nullable=False)
    invoice_number  = Column(String(50),  nullable=False)
    customer_name   = Column(String(255), nullable=False)
    recipient_email = Column(String(255), nullable=False)

    sent_date       = Column(Date,     nullable=False, default=date.today, index=True)
    sent_at         = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    days_overdue    = Column(Integer,  nullable=False)
    success         = Column(Boolean,  nullable=False, default=False)
    error_message   = Column(Text,     nullable=True)

    # Relationships
    rule    = relationship("ReminderRule", back_populates="logs")
    invoice = relationship("Invoice")

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗" # type: ignore
        return f"<ReminderLog {status} inv={self.invoice_number} to={self.recipient_email}>"