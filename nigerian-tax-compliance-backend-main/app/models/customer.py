"""
Customer Model (Updated for Week 3)
Location: app/models/customer.py
"""
from sqlalchemy import Column, String, Integer, Date, Numeric, DateTime, ForeignKey, Boolean, Text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import relationship, column_property # type: ignore
from app.models.invoice import Invoice, InvoiceStatus
from sqlalchemy import case, func, select, cast
from sqlalchemy.types import Date

import uuid
from datetime import datetime, timezone
from app.core.database import Base
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore



class Customer(Base):
    """
    Customer Model
    
    Represents a customer/client of a business
    """
    __tablename__ = "customers"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Basic Information
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Address
    address = Column(String, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    country = Column(String(50), default="Nigeria", nullable=False)
    
    # Tax Information
    tin = Column(String(20), nullable=True)
    
    # Analytics (Auto-calculated)
    total_invoices_count = Column(Integer, default=0, nullable=False)
    total_invoiced_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_paid_amount = Column(Numeric(15, 2), default=0, nullable=False)
    average_payment_days = Column(Integer, nullable=True)
    last_invoice_date = Column(Date, nullable=True)
    
    # Settings
    customer_type = Column(String(50), default="Individual", nullable=False)
    credit_limit = Column(Numeric(15, 2), nullable=True)
    payment_terms_days = Column(Integer, default=30, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps - FIXED: Use timezone-aware datetime
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    business = relationship("Business", back_populates="customers")
    invoices = relationship("Invoice", back_populates="customer", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="customer", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Customer {self.name}>"
    
    @property
    def outstanding_amount(self) -> float:
        """Calculate outstanding amount (invoiced - paid)"""
        return float(self.total_invoiced_amount - self.total_paid_amount) # type: ignore
    
    async def update_analytics(self, db: AsyncSession) -> None:
        """Update customer analytics from invoices using aggregated SQL"""
       
        stmt = select(
            func.count().label("total_invoices_count"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("total_invoiced_amount"),
            func.coalesce(func.sum(Invoice.paid_amount), 0).label("total_paid_amount"),
            func.max(Invoice.issue_date).label("last_invoice_date"),
            func.avg(
                case(
                    (
                        Invoice.status == InvoiceStatus.PAID,
                        func.extract("epoch", Invoice.paid_at) - # type: ignore
                        func.extract("epoch", func.cast(Invoice.issue_date, DateTime))
                    )
                )
            ).label("avg_payment_seconds"),
        ).where(
            Invoice.customer_id == self.id,
            Invoice.status != InvoiceStatus.CANCELLED # type: ignore
        )

        row = (await db.execute(stmt)).one()

        self.total_invoices_count  = row.total_invoices_count
        self.total_invoiced_amount = row.total_invoiced_amount
        self.total_paid_amount     = row.total_paid_amount
        self.last_invoice_date     = row.last_invoice_date
        self.average_payment_days  = (
            int(row.avg_payment_seconds / 86400)
            if row.avg_payment_seconds is not None else None
        )