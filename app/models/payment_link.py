"""
PaymentLink Model
Location: app/models/payment_link.py

Stores public payment tokens for Paystack invoice payment pages.
One link per invoice — deactivated once the invoice is paid.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, Boolean, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.base import Base


class PaymentLink(Base):
    __tablename__ = "payment_links"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Public token embedded in the payment URL
    token       = Column(String(100), nullable=False, unique=True, index=True)

    # Paystack transaction reference (set when customer initiates payment)
    paystack_ref = Column(String(100), nullable=True)

    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    invoice  = relationship("Invoice",  back_populates="payment_link")
    business = relationship("Business", back_populates="payment_links")

    def __repr__(self) -> str:
        return f"<PaymentLink token={self.token} active={self.is_active}>"
