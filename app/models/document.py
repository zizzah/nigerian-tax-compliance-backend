# app/models/document.py
"""
Document Model - Base upload record
Location: app/models/document.py
"""
from sqlalchemy import Column, String, Enum, DateTime, Numeric, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from app.core.base import Base
import enum


class DocumentType(str, enum.Enum):
    RECEIPT        = "RECEIPT"
    INVOICE        = "INVOICE"
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_DOCUMENT   = "TAX_DOCUMENT"
    OTHER          = "OTHER"


class ProcessingStatus(str, enum.Enum):
    PENDING       = "PENDING"
    PROCESSING    = "PROCESSING"
    COMPLETED     = "COMPLETED"
    FAILED        = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class Document(Base):
    __tablename__ = "documents"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    document_type = Column(Enum(DocumentType), nullable=False, index=True)

    # ── File metadata (no path — file is not stored) ──────────────────────────
    original_filename = Column(String(255), nullable=False)
    file_size         = Column(Integer,     nullable=False)
    file_type         = Column(String(50),  nullable=False)  # mime type

    # ── Processing ────────────────────────────────────────────────────────────
    status                      = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False, index=True)
    confidence_score            = Column(Numeric(3, 2),          nullable=True)
    processing_started_at       = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at     = Column(DateTime(timezone=True), nullable=True)
    processing_error            = Column(Text,                    nullable=True)
    processing_duration_seconds = Column(Numeric(6, 2),           nullable=True)
    ai_model_used               = Column(String(100),             nullable=True)

    # ── Review ────────────────────────────────────────────────────────────────
    requires_review     = Column(Boolean,                 nullable=False, default=False, index=True)
    review_notes        = Column(Text,                    nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True),      nullable=True)
    reviewed_at         = Column(DateTime(timezone=True),  nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    notes       = Column(Text,    nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Document {self.document_type} {self.id} - {self.original_filename}>"