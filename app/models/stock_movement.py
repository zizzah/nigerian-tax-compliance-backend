# app/models/stock_movement.py
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime

from typing import Optional
from sqlalchemy import ForeignKey, Numeric, Text, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.base import Base


class StockMovementType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    movement_type: Mapped[StockMovementType] = mapped_column(
        SAEnum(StockMovementType, name="stockmovementtype", create_type=False),
        nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc)
    )

    business: Mapped["Business"] = relationship("Business") # type: ignore
    product: Mapped["Product"] = relationship("Product") # type: ignore
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice") # type: ignore
