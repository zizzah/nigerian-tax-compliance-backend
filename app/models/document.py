"""
Document Model - Stores uploaded receipts, invoices, and other tax documents
Location: app/models/document.py

Uses Groq AI for fast, cost-effective document extraction
"""
from sqlalchemy import Column, String, Enum, DateTime, Numeric, Text, Boolean, Date, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime
from app.core.base import Base
import enum


class DocumentType(str, enum.Enum):
    """Document types"""
    RECEIPT = "RECEIPT"           # Purchase receipt
    INVOICE = "INVOICE"           # Sales invoice
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_DOCUMENT = "TAX_DOCUMENT"
    OTHER = "OTHER"


class ProcessingStatus(str, enum.Enum):
    """Document processing status"""
    PENDING = "PENDING"           # Uploaded, not processed
    PROCESSING = "PROCESSING"     # Being processed by AI
    COMPLETED = "COMPLETED"       # Successfully processed
    FAILED = "FAILED"            # Processing failed
    REVIEW_NEEDED = "REVIEW_NEEDED"  # Low confidence, needs human review


class Document(Base):
    """
    Document model for receipts, invoices, and other tax documents
    
    AI Processing powered by Groq (llama-3.3-70b-versatile)
    """
    __tablename__ = "documents"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relationships
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)  # For sales documents
    vendor_id = Column(UUID(as_uuid=True), nullable=True)    # For purchase documents
    
    # Document Info
    document_type = Column(Enum(DocumentType), nullable=False, index=True)
    document_number = Column(String(100), nullable=True)  # Receipt/Invoice number
    document_date = Column(Date, nullable=True, index=True)
    
    # File Info
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    file_type = Column(String(50), nullable=False)  # image/jpeg, application/pdf, etc.
    
    # Processing Status
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False, index=True)
    confidence_score = Column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(Text, nullable=True)
    processing_duration_seconds = Column(Numeric(6, 2), nullable=True)  # Track performance
    
    # Extracted Financial Data
    vendor_name = Column(String(255), nullable=True)
    vendor_tin = Column(String(20), nullable=True)
    vendor_address = Column(Text, nullable=True)
    vendor_phone = Column(String(20), nullable=True)
    
    # Line items stored as JSONB for flexibility
    line_items = Column(JSONB, nullable=True)  
    # Example: [{"description": "Laptop", "quantity": 1, "unit_price": 450000, "amount": 450000}]
    
    # Financial Totals
    subtotal = Column(Numeric(15, 2), default=0)
    vat_amount = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), default=0)
    
    # Tax Info
    vat_rate = Column(Numeric(5, 2), default=7.5)  # Nigerian VAT rate
    is_vatable = Column(Boolean, default=True)
    
    # Payment Info
    payment_method = Column(String(50), nullable=True)  # Cash, Card, Transfer, etc.
    payment_reference = Column(String(100), nullable=True)
    
    # Categorization (for expense tracking)
    category = Column(String(100), nullable=True, index=True)  # Office Supplies, Utilities, etc.
    tags = Column(JSONB, nullable=True)  # ["business_expense", "tax_deductible"]
    
    # OCR Raw Data (for debugging/review)
    ocr_raw_text = Column(Text, nullable=True)  # Raw text from Tesseract
    ocr_confidence = Column(Numeric(3, 2), nullable=True)
    
    # AI Extracted Data (full JSON response)
    ai_extracted_data = Column(JSONB, nullable=True)  # Full Groq response
    ai_model_used = Column(String(50), nullable=True, default="llama-3.3-70b-versatile")
    
    # Review & Notes
    requires_review = Column(Boolean, default=False, index=True)
    review_notes = Column(Text, nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Document {self.document_type} - {self.original_filename}>"
    
    @property
    def outstanding_amount(self):
        """Calculate outstanding amount (for tracking unpaid receipts)"""
        return self.total_amount
