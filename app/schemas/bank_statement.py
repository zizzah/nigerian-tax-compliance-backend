# app/schemas/bank_statement.py

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime, date
import uuid

from app.schemas.document import DocumentType, ProcessingStatus, DocumentBase


# ── Nested ─────────────────────────────────────────────────────────────────────

class TransactionSchema(BaseModel):
    """Single credit or debit transaction row."""
    date: date
    description: str=""
    amount: Decimal
    value_date: Optional[date] = None # type: ignore
    balance: Optional[Decimal] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Transaction amount must be positive")
        return v

    model_config = ConfigDict(from_attributes=True)


# ── Create ─────────────────────────────────────────────────────────────────────

class BankStatementCreate(BaseModel):
    """
    Sent by the client at upload time.
    The user can optionally tell us which bank — AI will confirm or correct.
    """
    document_type: DocumentType = Field(default=DocumentType.BANK_STATEMENT)
    bank_name: Optional[str] = None   # hint only — AI extraction is authoritative
    notes: Optional[str] = None


# ── Update ─────────────────────────────────────────────────────────────────────

class BankStatementUpdate(BaseModel):
    """
    Manual correction after AI extraction.
    Every field is optional — PATCH semantics.
    """
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None

    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_inflow: Optional[Decimal] = None
    total_outflow: Optional[Decimal] = None

    inflow_transactions: Optional[List[TransactionSchema]] = None
    outflow_transactions: Optional[List[TransactionSchema]] = None

    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── Response ───────────────────────────────────────────────────────────────────

class BankStatementResponse(DocumentBase):
    """
    Full bank statement response — joins Document + BankStatement rows.
    DocumentBase carries: id, business_id, document_type, file info,
    processing status, review flags, timestamps.
    """
    # Account
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None

    # Period
    period_from: Optional[date] = None
    period_to: Optional[date] = None

    # Balances
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_inflow: Optional[Decimal] = None
    total_outflow: Optional[Decimal] = None

    # Transactions
    inflow_transactions: Optional[List[TransactionSchema]] = None
    outflow_transactions: Optional[List[TransactionSchema]] = None

    model_config = ConfigDict(from_attributes=True)


# ── List ───────────────────────────────────────────────────────────────────────

class BankStatementListResponse(BaseModel):
    statements: List[BankStatementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int