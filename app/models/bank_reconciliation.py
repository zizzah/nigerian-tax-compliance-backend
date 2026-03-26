"""
BankReconciliation Model
Location: app/models/bank_reconciliation.py

Stores the result of each bank statement reconciliation run.
Each upload creates one BankReconciliation record that tracks:
- The uploaded file metadata
- All extracted transactions (raw_transactions JSONB)
- The AI match results (match_results JSONB)
- Summary counters and status
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class BankReconciliation(Base):
    __tablename__ = "bank_reconciliations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owning business
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Uploaded file info
    filename    = Column(String(255), nullable=False)
    bank_name   = Column(String(100), nullable=True)

    # Statement period (parsed from the document if possible)
    period_from = Column(Date, nullable=True)
    period_to   = Column(Date, nullable=True)

    # Summary counters
    total_credits    = Column(Numeric(18, 2), default=0, nullable=False)
    matched_count    = Column(Integer,        default=0, nullable=False)
    unmatched_count  = Column(Integer,        default=0, nullable=False)

    # Lifecycle status: processing | completed | failed
    status = Column(String(30), default="processing", nullable=False, index=True)

    # Full JSON payloads
    raw_transactions = Column(JSONB, nullable=True)   # list of extracted credit txns
    match_results    = Column(JSONB, nullable=True)   # list of match result dicts

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    business = relationship("Business")

    def __repr__(self) -> str:
        return (
            f"<BankReconciliation {self.filename} "
            f"matched={self.matched_count}/{self.matched_count + self.unmatched_count} "
            f"status={self.status}>"
        )