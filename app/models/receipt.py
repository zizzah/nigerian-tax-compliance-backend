# app/models/receipt.py
"""
Receipt Model
Location: app/models/receipt.py
"""
from sqlalchemy import Column, String, Enum, DateTime, Numeric, Text, Boolean, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, backref
import uuid
from datetime import datetime, timezone
from app.core.base import Base
from app.models.document import DocumentType


class Receipt(Base):
    __tablename__ = "receipts"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)
    vendor_id   = Column(UUID(as_uuid=True), nullable=True)

    # ── Document Info ─────────────────────────────────────────────────────────
    document_type   = Column(Enum(DocumentType), nullable=False, index=True)  # RECEIPT or INVOICE
    document_number = Column(String(100), nullable=True)
    document_date   = Column(Date,        nullable=True, index=True)

    # ── Vendor ────────────────────────────────────────────────────────────────
    vendor_name    = Column(String(255), nullable=True)
    vendor_tin     = Column(String(50),  nullable=True)
    vendor_address = Column(Text,        nullable=True)
    vendor_phone   = Column(String(50),  nullable=True)

    # ── Line Items ────────────────────────────────────────────────────────────
    line_items = Column(JSONB, nullable=True)
    # [{"description": "Laptop", "quantity": 1, "unit_price": 450000, "amount": 450000}]

    # ── Financial ─────────────────────────────────────────────────────────────
    subtotal     = Column(Numeric(15, 2), default=0)
    vat_amount   = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), default=0)
    vat_rate     = Column(Numeric(5, 2),  default=7.5)
    is_vatable   = Column(Boolean,        default=True)

    # ── Payment ───────────────────────────────────────────────────────────────
    payment_method    = Column(String(50),  nullable=True)
    payment_reference = Column(String(100), nullable=True)

    # ── Categorisation ────────────────────────────────────────────────────────
    category = Column(String(100), nullable=True, index=True)
    tags     = Column(JSONB,       nullable=True)

    # ── OCR / AI ──────────────────────────────────────────────────────────────
    ocr_raw_text      = Column(Text,          nullable=True)
    ocr_confidence    = Column(Numeric(3, 2), nullable=True)
    ai_extracted_data = Column(JSONB,         nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── Relationships ─────────────────────────────────────────────────────────
    document = relationship("Document", backref=backref("receipt", uselist=False))

    def __repr__(self) -> str:
        return f"<Receipt {self.document_type} {self.id} - {self.vendor_name}>"