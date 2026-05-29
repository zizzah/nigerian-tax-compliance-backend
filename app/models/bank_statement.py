# app/models/bank_statement.py
"""
Bank Statement Model
Location: app/models/bank_statement.py
"""
from sqlalchemy import Column, String, DateTime, Numeric, Text, Boolean, Date, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, backref
import uuid
from datetime import datetime, timezone
from app.core.base import Base


class BankStatement(Base):
    __tablename__ = "bank_statements"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # ── Account Info ──────────────────────────────────────────────────────────
    account_name   = Column(String(255), nullable=True)
    account_number = Column(String(100), nullable=True)
    bank_name      = Column(String(100), nullable=True)

    # ── Period ────────────────────────────────────────────────────────────────
    period_from = Column(Date, nullable=True, index=True)
    period_to   = Column(Date, nullable=True, index=True)

    # ── Balances ──────────────────────────────────────────────────────────────
    opening_balance = Column(Numeric(15, 2), nullable=True)
    closing_balance = Column(Numeric(15, 2), nullable=True)
    total_inflow    = Column(Numeric(15, 2), nullable=True)
    total_outflow   = Column(Numeric(15, 2), nullable=True)

    # ── Transactions ──────────────────────────────────────────────────────────
    inflow_transactions  = Column(JSONB, nullable=True)
    # [{"date": "2026-03-24", "description": "...", "amount": 1.00, "balance": 2143.80}]
    outflow_transactions = Column(JSONB, nullable=True)
    # [{"date": "2026-03-22", "description": "...", "amount": 3000.00, "balance": 2157.55}]

    # ── AI ────────────────────────────────────────────────────────────────────
    ai_extracted_data = Column(JSONB, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── Relationships ─────────────────────────────────────────────────────────
    document = relationship("Document", backref=backref("bank_statement", uselist=False))

    # ── Computed ──────────────────────────────────────────────────────────────
    @property
    def net_cashflow(self) -> float | None:
        if self.total_inflow is None and self.total_outflow is None:
            return None
        return round(float(self.total_inflow or 0) - float(self.total_outflow or 0), 2) # type: ignore

    def __repr__(self) -> str:
        return f"<BankStatement {self.id} - {self.bank_name} {self.period_from} to {self.period_to}>"