"""
Document Model
Location: app/models/document.py
"""
from sqlalchemy import Column, String, Enum, DateTime, Numeric, Text, Boolean, Date, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime, timezone
from app.core.base import Base
import enum


class DocumentType(str, enum.Enum):
    RECEIPT       = "RECEIPT"
    INVOICE       = "INVOICE"
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_DOCUMENT  = "TAX_DOCUMENT"
    OTHER         = "OTHER"


class ProcessingStatus(str, enum.Enum):
    PENDING       = "PENDING"
    PROCESSING    = "PROCESSING"
    COMPLETED     = "COMPLETED"
    FAILED        = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class Document(Base):
    __tablename__ = "documents"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Relationships ─────────────────────────────────────────────────────────
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)
    vendor_id   = Column(UUID(as_uuid=True), nullable=True)

    # ── Document Info ─────────────────────────────────────────────────────────
    document_type   = Column(Enum(DocumentType), nullable=False, index=True)
    document_number = Column(String(100), nullable=True)
    document_date   = Column(Date, nullable=True, index=True)

    # ── File Info ─────────────────────────────────────────────────────────────
    original_filename = Column(String(255), nullable=False)
    file_path         = Column(String(500),  nullable=False)   # Cloudinary HTTPS URL
    cloudinary_public_id = Column(String(500), nullable=True)  # for deletion — NOT review_notes
    file_size         = Column(Integer, nullable=False)
    file_type         = Column(String(50),  nullable=False)

    # ── Processing ────────────────────────────────────────────────────────────
    status                      = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False, index=True)
    confidence_score            = Column(Numeric(3, 2), nullable=True)
    processing_started_at       = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at     = Column(DateTime(timezone=True), nullable=True)
    processing_error            = Column(Text, nullable=True)
    processing_duration_seconds = Column(Numeric(6, 2), nullable=True)

    # ── Receipt / Invoice fields ──────────────────────────────────────────────
    vendor_name    = Column(String(255), nullable=True)
    vendor_tin     = Column(String(50),  nullable=True)
    vendor_address = Column(Text,        nullable=True)
    vendor_phone   = Column(String(50),  nullable=True)

    line_items = Column(JSONB, nullable=True)
    # [{"description": "Laptop", "quantity": 1, "unit_price": 450000, "amount": 450000}]

    subtotal     = Column(Numeric(15, 2), default=0)
    vat_amount   = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), default=0)
    vat_rate     = Column(Numeric(5, 2),  default=7.5)
    is_vatable   = Column(Boolean, default=True)

    payment_method    = Column(String(50),  nullable=True)
    payment_reference = Column(String(100), nullable=True)

    category = Column(String(100), nullable=True, index=True)
    tags     = Column(JSONB, nullable=True)

    # ── OCR (receipts/invoices only) ──────────────────────────────────────────
    ocr_raw_text   = Column(Text,          nullable=True)
    ocr_confidence = Column(Numeric(3, 2), nullable=True)

    # ── AI ────────────────────────────────────────────────────────────────────
    ai_extracted_data = Column(JSONB,        nullable=True)
    ai_model_used     = Column(String(100),  nullable=True)  # increased from 50

    # ── Bank Statement fields (only populated for BANK_STATEMENT type) ────────
    opening_balance      = Column(Numeric(15, 2), nullable=True)
    closing_balance      = Column(Numeric(15, 2), nullable=True)
    total_inflow         = Column(Numeric(15, 2), nullable=True)
    total_outflow        = Column(Numeric(15, 2), nullable=True)
    inflow_transactions  = Column(JSONB, nullable=True)
    # [{"date": "2026-03-24", "description": "...", "amount": 1.00, "balance": 2143.80}]
    outflow_transactions = Column(JSONB, nullable=True)
    # [{"date": "2026-03-22", "description": "...", "amount": 3000.00, "balance": 2157.55}]

    # ── Review & Notes ────────────────────────────────────────────────────────
    requires_review     = Column(Boolean,                nullable=False, default=False, index=True)
    review_notes        = Column(Text,                   nullable=True)   # human review notes ONLY
    reviewed_by_user_id = Column(UUID(as_uuid=True),     nullable=True)
    reviewed_at         = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    notes       = Column(Text,    nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    # FIX: datetime.utcnow is deprecated — use lambda with timezone-aware UTC
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Document {self.document_type} {self.id} - {self.original_filename}>"

    @property
    def is_bank_statement(self) -> bool:
        return self.document_type == DocumentType.BANK_STATEMENT # type: ignore

    @property
    def net_cashflow(self):
        """For bank statements: inflow minus outflow."""
        if not self.is_bank_statement:
            return None
        inflow  = float(self.total_inflow  or 0) # type: ignore
        outflow = float(self.total_outflow or 0) # type: ignore
        return round(inflow - outflow, 2)