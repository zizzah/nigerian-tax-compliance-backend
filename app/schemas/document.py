"""
Document Pydantic Schemas
Location: app/schemas/document.py
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, date
import uuid
from enum import Enum


class DocumentType(str, Enum):
    RECEIPT = "RECEIPT"
    INVOICE = "INVOICE"
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_DOCUMENT = "TAX_DOCUMENT"
    OTHER = "OTHER"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class LineItemSchema(BaseModel):
    """Schema for document line items"""
    description: str
    quantity: Decimal = Field(default=Decimal(1))
    unit_price: Decimal
    amount: Decimal
    tax_amount: Optional[Decimal] = None
    
    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    """Response after document upload"""
    document_id: uuid.UUID
    status: ProcessingStatus
    task_id: Optional[str] = None
    message: str
    estimated_completion_seconds: int = Field(default=15)  # Groq is very fast!


class DocumentCreate(BaseModel):
    """Schema for creating document (upload)"""
    document_type: DocumentType = Field(default=DocumentType.RECEIPT)
    notes: Optional[str] = None


class DocumentUpdate(BaseModel):
    """Schema for updating document"""
    document_type: Optional[DocumentType] = None
    vendor_name: Optional[str] = None
    document_date: Optional[date] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # Allow manual correction of extracted data
    subtotal: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    line_items: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Schema for document response"""
    id: uuid.UUID
    business_id: uuid.UUID
    
    # Document Info
    document_type: DocumentType
    document_number: Optional[str]
    document_date: Optional[date]
    
    # File Info
    original_filename: str
    file_path: str
    file_size: int
    file_type: str
    
    # Processing Status
    status: ProcessingStatus
    confidence_score: Optional[Decimal]
    processing_error: Optional[str]
    processing_duration_seconds: Optional[Decimal]
    
    # Extracted Data
    vendor_name: Optional[str]
    vendor_tin: Optional[str]
    vendor_address: Optional[str]
    vendor_phone: Optional[str]
    line_items: Optional[List[Dict[str, Any]]]
    
    # Financial
    subtotal: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    vat_rate: Decimal
    
    # Categorization
    category: Optional[str]
    tags: Optional[List[str]]
    payment_method: Optional[str]
    payment_reference: Optional[str]
    
    # Review
    requires_review: bool
    review_notes: Optional[str]
    
    # AI Info
    ai_model_used: Optional[str]
    ocr_confidence: Optional[Decimal]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    processing_completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated document list"""
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentStatistics(BaseModel):
    """Document processing statistics"""
    total_documents: int
    pending_processing: int
    completed: int
    failed: int
    requires_review: int
    
    total_amount_processed: Decimal
    average_confidence_score: Optional[float]
    average_processing_time: Optional[float]  # in seconds
    
    by_type: Dict[str, int]
    by_category: Dict[str, int]
    by_status: Dict[str, int]


class DocumentBatchUploadResponse(BaseModel):
    """Response for batch upload"""
    uploaded_count: int
    document_ids: List[uuid.UUID]
    task_ids: List[str]
    message: str



class TransactionSchema(BaseModel):
    """Single bank transaction (inflow or outflow)"""
    date: str                        # "2026-03-22"
    description: str
    amount: Decimal
    value_date: Optional[str] = None
    balance: Optional[Decimal] = None
 
    class Config:
        from_attributes = True
 
 
class BankStatementResponse(BaseModel):
    """
    Response schema for bank statement documents.
    Extends DocumentResponse with bank-specific fields.
    """
    id: str
    business_id: str
    document_type: str
    original_filename: str
    file_path: str
    status: str
 
    # Account info (extracted from statement header)
    account_name: Optional[str] = None      # stored in vendor_name
    account_number: Optional[str] = None    # stored in document_number
    bank_name: Optional[str] = None         # stored in vendor_name prefix
 
    # Period
    period_from: Optional[date] = None      # stored in document_date
    period_to: Optional[date] = None
 
    # Balances
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_inflow: Optional[Decimal] = None
    total_outflow: Optional[Decimal] = None
 
    # Transactions
    inflow_transactions:  Optional[List[TransactionSchema]] = None
    outflow_transactions: Optional[List[TransactionSchema]] = None
 
    # Processing
    confidence_score: Optional[Decimal] = None
    processing_error: Optional[str] = None
    ai_model_used: Optional[str] = None
 
    class Config:
        from_attributes = True
 












