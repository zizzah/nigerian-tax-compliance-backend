"""
Bank Reconciliation Pydantic Schemas
Location: app/schemas/bank_reconciliation.py

Used by:
  POST /reconciliation/upload  → BankReconciliationUploadResponse
  POST /reconciliation/apply   → BankReconciliationApplyResponse
  GET  /reconciliation/        → BankReconciliationListResponse
  GET  /reconciliation/{id}    → BankReconciliationResponse
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class TransactionSchema(BaseModel):
    """A single credit transaction extracted from the bank statement."""
    date: Optional[str] = None          # ISO date string YYYY-MM-DD
    description: str = ""
    amount: float = 0.0
    reference: Optional[str] = None
    type: str = "credit"


class MatchResultSchema(BaseModel):
    """Result of matching one transaction to an outstanding invoice."""
    transaction: TransactionSchema
    matched: bool
    confidence: int = Field(0, ge=0, le=100, description="Match confidence 0–100")
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    customer_name: Optional[str] = None
    invoice_amount: Optional[float] = None


# ── Request schemas ───────────────────────────────────────────────────────────

class ApplyMatchRequest(BaseModel):
    """
    Body for POST /reconciliation/apply.
    The caller sends back only the matches they want to apply
    (i.e. the subset of MatchResultSchema objects where matched=True
    and the user has ticked them in the review UI).
    """
    matches: list[dict[str, Any]] = Field(
        ...,
        description="List of match result dicts (matched=True) returned by /upload",
    )
    reconciliation_id: Optional[str] = Field(
        None,
        description="Optional: ID of the BankReconciliation record to mark as completed",
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class AppliedMatchSchema(BaseModel):
    """Summary of one successfully applied match."""
    invoice_number: str
    amount_applied: float
    new_status: str   # e.g. PAID, PARTIALLY_PAID


class BankReconciliationUploadResponse(BaseModel):
    """
    Returned immediately after a statement is uploaded and processed.
    The frontend uses `matches` to render the review table.
    """
    reconciliation_id: str
    filename: str
    bank_name: str
    total_transactions: int
    matched_count: int
    unmatched_count: int
    total_credit_amount: float
    status: str
    matches: list[dict[str, Any]]   # list of MatchResultSchema dicts

    class Config:
        from_attributes = True


class BankReconciliationApplyResponse(BaseModel):
    """Returned after confirmed matches are applied to invoices."""
    applied_count: int
    error_count: int
    applied: list[AppliedMatchSchema]
    errors: list[str]

    class Config:
        from_attributes = True


class BankReconciliationResponse(BaseModel):
    """Full representation of a saved BankReconciliation record."""
    id: uuid.UUID
    business_id: uuid.UUID
    filename: str
    bank_name: Optional[str]
    period_from: Optional[date]
    period_to: Optional[date]
    total_credits: Decimal
    matched_count: int
    unmatched_count: int
    status: str
    raw_transactions: Optional[list[dict[str, Any]]]
    match_results: Optional[list[dict[str, Any]]]
    created_at: datetime

    class Config:
        from_attributes = True


class BankReconciliationListResponse(BaseModel):
    """Paginated list of past reconciliation runs."""
    reconciliations: list[BankReconciliationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int