"""
Business Model (Updated for Week 3)
Location: app/models/business.py
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Enum # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import relationship # type: ignore
import uuid
from datetime import datetime, timezone
import enum
from app.core.base import Base


class SubscriptionTier(str, enum.Enum):
    """Subscription tier enumeration"""
    FREE = "FREE"
    BASIC = "BASIC"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class Business(Base):
    """
    Business Model

    Represents a business profile for a user
    """
    __tablename__ = "businesses"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Business Information
    business_name = Column(String(255), nullable=False)
    business_type = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)

    # Tax Information
    tin = Column(String(20), unique=True, nullable=True)
    vat_registered = Column(Boolean, default=False, nullable=False)
    vat_number = Column(String(20), nullable=True)
    rc_number = Column(String(20), nullable=True)

    # Contact Information
    address = Column(String, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    country = Column(String(50), default="Nigeria", nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)

    # Branding
    logo_url = Column(String, nullable=True)
    primary_color = Column(String(7), default="#3B82F6", nullable=False)
    secondary_color = Column(String(7), default="#10B981", nullable=False)

    # Paystack Payment Integration (per-business keys for SaaS)
    paystack_public_key = Column(String(200), nullable=True)
    paystack_secret_key = Column(String(200), nullable=True)

    # Invoice Settings
    invoice_prefix = Column(String(10), default="INV", nullable=False)
    invoice_counter = Column(Integer, default=1, nullable=False)

    # Subscription
    subscription_tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    monthly_invoice_quota = Column(Integer, default=10, nullable=False)
    monthly_document_quota = Column(Integer, default=20, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="business")
    customers = relationship("Customer", back_populates="business", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="business", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="business", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="business", cascade="all, delete-orphan")
    payment_links = relationship("PaymentLink", back_populates="business", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="business", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Business {self.business_name}>"

    def get_next_invoice_number(self) -> str:
        """Generate the next invoice number"""
        return f"{self.invoice_prefix}-{self.invoice_counter:05d}"

    def increment_invoice_counter(self):
        """Increment the invoice counter"""
        self.invoice_counter += 1
