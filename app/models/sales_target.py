"""
SalesTarget Model
Location: app/models/sales_target.py

Stores annual + monthly + quarterly revenue targets per business.
The helper split_annual_target() distributes an annual figure across
12 months using a simple seasonal weighting for Nigeria.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.base import Base


# ---------------------------------------------------------------------------
# Seasonal split weights (sum = 1.0)
# Tuned for a typical Nigerian SME: slower Jan-Mar, busier Q4
# ---------------------------------------------------------------------------
_MONTHLY_WEIGHTS = {
    "jan": 0.06,
    "feb": 0.07,
    "mar": 0.08,
    "apr": 0.08,
    "may": 0.08,
    "jun": 0.09,
    "jul": 0.08,
    "aug": 0.08,
    "sep": 0.09,
    "oct": 0.09,
    "nov": 0.10,
    "dec": 0.10,
}


def split_annual_target(annual: float) -> dict:
    """
    Distribute an annual revenue target across 12 months.

    Returns a dict with keys jan…dec (monthly amounts, 2 dp).
    The sum always equals annual (last month absorbs rounding).
    """
    splits: dict[str, float] = {}
    total_so_far = 0.0
    months = list(_MONTHLY_WEIGHTS.keys())

    for i, month in enumerate(months):
        if i == len(months) - 1:
            # Last month absorbs rounding residue
            splits[month] = round(annual - total_so_far, 2)
        else:
            amount = round(annual * _MONTHLY_WEIGHTS[month], 2)
            splits[month] = amount
            total_so_far += amount

    return splits


class SalesTarget(Base):
    """
    Annual revenue target broken down into monthly and quarterly buckets.

    Uniqueness: one row per (business_id, year).
    """
    __tablename__ = "sales_targets"
    __table_args__ = (
        UniqueConstraint("business_id", "year", name="uq_sales_target_biz_year"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year         = Column(Integer, nullable=False)
    annual_target = Column(Numeric(18, 2), nullable=False)

    # Monthly targets (jan … dec)
    jan_target = Column(Numeric(18, 2), nullable=False, default=0)
    feb_target = Column(Numeric(18, 2), nullable=False, default=0)
    mar_target = Column(Numeric(18, 2), nullable=False, default=0)
    apr_target = Column(Numeric(18, 2), nullable=False, default=0)
    may_target = Column(Numeric(18, 2), nullable=False, default=0)
    jun_target = Column(Numeric(18, 2), nullable=False, default=0)
    jul_target = Column(Numeric(18, 2), nullable=False, default=0)
    aug_target = Column(Numeric(18, 2), nullable=False, default=0)
    sep_target = Column(Numeric(18, 2), nullable=False, default=0)
    oct_target = Column(Numeric(18, 2), nullable=False, default=0)
    nov_target = Column(Numeric(18, 2), nullable=False, default=0)
    dec_target = Column(Numeric(18, 2), nullable=False, default=0)

    # Quarterly totals (derived from monthly, stored for fast queries)
    q1_target = Column(Numeric(18, 2), nullable=False, default=0)
    q2_target = Column(Numeric(18, 2), nullable=False, default=0)
    q3_target = Column(Numeric(18, 2), nullable=False, default=0)
    q4_target = Column(Numeric(18, 2), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationship
    business = relationship("Business")

    def __repr__(self) -> str:
        return f"<SalesTarget {self.year} ₦{float(self.annual_target):,.0f}>" # type: ignore
