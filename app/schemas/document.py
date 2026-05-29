# app/schemas/document.py
"""
Document Pydantic Schemas - shared base only
Location: app/schemas/document.py
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from decimal import Decimal
from datetime import datetime
import uuid
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    RECEIPT        = "RECEIPT"
    INVOICE        = "INVOICE"
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_DOCUMENT   = "TAX_DOCUMENT"
    OTHER          = "OTHER"


class ProcessingStatus(str, Enum):
    PENDING       = "PENDING"
    PROCESSING    = "PROCESSING"
    COMPLETED     = "COMPLETED"
    FAILED        = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


# ── Shared base ────────────────────────────────────────────────────────────────

class DocumentBase(BaseModel):
    """
    Fields present on every document response regardless of type.
    Never return this directly from an endpoint.
    """
    id:          uuid.UUID
    business_id: uuid.UUID

    document_type: DocumentType

    # File metadata — no path, file is not stored
    original_filename: str
    file_size:         int
    file_type:         str

    # Processing
    status:                      ProcessingStatus
    confidence_score:            Optional[Decimal] = None
    processing_error:            Optional[str]     = None
    processing_duration_seconds: Optional[Decimal] = None
    processing_completed_at:     Optional[datetime] = None
    ai_model_used:               Optional[str]      = None

    # Review
    requires_review:     bool
    review_notes:        Optional[str]       = None
    reviewed_by_user_id: Optional[uuid.UUID] = None
    reviewed_at:         Optional[datetime]  = None

    # Metadata
    notes:       Optional[str] = None
    is_archived: bool          = False

    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Upload response ────────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    """
    Returned immediately after upload, before AI processing completes.
    Client polls document_id for status.
    """
    document_id:                  uuid.UUID
    status:                       ProcessingStatus
    task_id:                      Optional[str] = None
    message:                      str
    estimated_completion_seconds: int = 15


# ── Statistics ─────────────────────────────────────────────────────────────────

class DocumentStatistics(BaseModel):
    total_documents:    int
    pending_processing: int
    completed:          int
    failed:             int
    requires_review:    int

    total_amount_processed:   Decimal
    average_confidence_score: Optional[float] = None
    average_processing_time:  Optional[float] = None  # seconds

    by_type:   dict[str, int]
    by_status: dict[str, int]