# app/schemas/receipt.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, date
import uuid

from app.schemas.document import DocumentType, ProcessingStatus, DocumentBase


class LineItemSchema(BaseModel):
    description: str
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    amount: Decimal
    tax_amount: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


# ── Create ─────────────────────────────────────────────────────────────────────

class ReceiptCreate(BaseModel):
    """
    Sent by the client at upload time.
    Only fields the user can supply upfront — AI fills the rest.
    """
    document_type: DocumentType = Field(default=DocumentType.RECEIPT)
    notes: Optional[str] = None


# ── Update ─────────────────────────────────────────────────────────────────────

class ReceiptUpdate(BaseModel):
    """
    Manual correction after AI extraction.
    Every field is optional — PATCH semantics.
    """
    vendor_name: Optional[str] = None
    vendor_tin: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_phone: Optional[str] = None
    document_date: Optional[date] = None
    document_number: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None

    subtotal: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    is_vatable: Optional[bool] = None

    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)


# ── Response ───────────────────────────────────────────────────────────────────

class ReceiptResponse(DocumentBase):
    """
    Full receipt response — joins Document + Receipt rows.
    DocumentBase carries: id, business_id, document_type, file info,
    processing status, review flags, timestamps.
    """
    # Identity
    customer_id: Optional[uuid.UUID] = None
    vendor_id: Optional[uuid.UUID] = None

    # Document
    document_number: Optional[str] = None
    document_date: Optional[date] = None

    # Vendor
    vendor_name: Optional[str] = None
    vendor_tin: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_phone: Optional[str] = None

    # Line items
    line_items: Optional[List[Dict[str, Any]]] = None

    # Financial
    subtotal: Decimal = Decimal("0")
    vat_amount: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    vat_rate: Decimal = Decimal("7.5")
    is_vatable: bool = True

    # Payment
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None

    # Categorisation
    category: Optional[str] = None
    tags: Optional[List[str]] = None

    # OCR / AI
    ocr_confidence: Optional[Decimal] = None
    ai_extracted_data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


# ── List ───────────────────────────────────────────────────────────────────────

class ReceiptListResponse(BaseModel):
    receipts: List[ReceiptResponse]
    total: int
    page: int
    page_size: int
    total_pages: int