"""
Bank Statement Reconciliation Endpoints
Location: app/api/v1/endpoints/reconciliation.py

Endpoints:
  POST /reconciliation/upload      — upload statement, AI-match transactions, persist record
  POST /reconciliation/apply       — apply confirmed matches (mark invoices paid)
  GET  /reconciliation/            — list past reconciliation runs
  GET  /reconciliation/{id}        — get a single reconciliation run with full detail

Register in app/main.py:
  from app.api.v1.endpoints import reconciliation
  app.include_router(reconciliation.router, prefix=settings.API_V1_PREFIX)
"""
import math
import uuid
import logging
import tempfile
import os
from datetime import date as date_type, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.bank_reconciliation import BankReconciliation
from app.schemas.bank_reconciliation import (
    ApplyMatchRequest,
    BankReconciliationUploadResponse,
    BankReconciliationApplyResponse,
    BankReconciliationResponse,
    BankReconciliationListResponse,
    AppliedMatchSchema,
)
from app.services.ai.bank_reconciler import BankReconciler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["Bank Reconciliation"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF. Falls back to raw UTF-8 decode."""
    try:
        import fitz  # PyMuPDF — add pymupdf>=1.24.0 to requirements.txt
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        doc = fitz.open(tmp_path)
        text = "\n".join(page.get_text() for page in doc) # type: ignore
        doc.close()
        os.unlink(tmp_path)
        return text
    except ImportError:
        logger.warning("PyMuPDF not installed — falling back to raw text decode for PDF")
        return file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return file_bytes.decode("utf-8", errors="replace")


# ── POST /reconciliation/upload ───────────────────────────────────────────────

@router.post("/upload", response_model=BankReconciliationUploadResponse, status_code=201)
async def upload_bank_statement(
    file: UploadFile = File(...),
    bank_name: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a bank statement (CSV, TXT, or PDF) for AI reconciliation.

    Steps:
    1. Extract text from the uploaded file.
    2. Use Groq to parse all CREDIT transactions.
    3. Match each transaction to outstanding invoices (amount + name heuristics).
    4. Persist a BankReconciliation record (status=completed).
    5. Return the full match list for user review.

    After reviewing the matches the frontend calls POST /reconciliation/apply.
    """
    biz = _get_business(db, current_user)
    content = await file.read()
    filename = file.filename or "statement"

    # ── Extract text ──────────────────────────────────────────────────────────
    if filename.lower().endswith(".pdf") or file.content_type == "application/pdf":
        text = _extract_pdf_text(content)
    else:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract any text from the uploaded file.",
        )

    # ── AI processing ─────────────────────────────────────────────────────────
    reconciler = BankReconciler()
    transactions = reconciler.parse_statement_text(text, bank_name)

    if not transactions:
        raise HTTPException(
            status_code=422,
            detail=(
                "No credit transactions found in the statement. "
                "Ensure this is a bank statement with incoming payments."
            ),
        )

    matches = reconciler.match_transactions(transactions, str(biz.id), db)

    matched   = [m for m in matches if m["matched"]]
    unmatched = [m for m in matches if not m["matched"]]
    total_credits = round(sum(float(m["transaction"].get("amount", 0)) for m in matches), 2)

    # ── Persist BankReconciliation record ─────────────────────────────────────
    recon = BankReconciliation(
        id=uuid.uuid4(),
        business_id=biz.id,
        filename=filename,
        bank_name=bank_name or None,
        total_credits=total_credits,
        matched_count=len(matched),
        unmatched_count=len(unmatched),
        status="completed",
        raw_transactions=transactions,
        match_results=matches,
    )
    db.add(recon)
    db.commit()
    db.refresh(recon)

    return BankReconciliationUploadResponse(
        reconciliation_id=str(recon.id),
        filename=filename,
        bank_name=bank_name or "Unknown",
        total_transactions=len(transactions),
        matched_count=len(matched),
        unmatched_count=len(unmatched),
        total_credit_amount=total_credits,
        status="completed",
        matches=matches,
    )


# ── POST /reconciliation/apply ────────────────────────────────────────────────

@router.post("/apply", response_model=BankReconciliationApplyResponse)
def apply_reconciliation(
    request: ApplyMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Apply user-confirmed reconciliation matches.

    For each confirmed match:
    - Creates a Payment record (method = BANK_TRANSFER)
    - Updates invoice paid_amount / outstanding_amount
    - Marks the invoice PAID if fully settled

    Optionally updates the parent BankReconciliation record status.
    """
    biz = _get_business(db, current_user)
    applied = []
    errors: list[str] = []

    for match in request.matches:
        if not match.get("matched") or not match.get("invoice_id"):
            continue

        try:
            inv = db.query(Invoice).filter(
                Invoice.id == uuid.UUID(match["invoice_id"]),
                Invoice.business_id == biz.id,
            ).first()

            if not inv:
                errors.append(f"Invoice {match['invoice_id']} not found")
                continue

            txn = match["transaction"]
            txn_date_str = txn.get("date", date_type.today().isoformat())
            try:
                txn_date = date_type.fromisoformat(txn_date_str)
            except (ValueError, TypeError):
                txn_date = date_type.today()

            amount = float(txn.get("amount", 0))

            payment = Payment(
                id=uuid.uuid4(),
                invoice_id=inv.id,
                business_id=biz.id,
                customer_id=inv.customer_id,
                amount=amount,
                payment_method="BANK_TRANSFER",
                payment_date=txn_date,
                reference_number=(txn.get("reference") or txn.get("description", ""))[:100],
                notes=f"Auto-matched from bank statement: {txn.get('description', '')}",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(payment)

            new_paid = float(inv.paid_amount or 0) + amount # type: ignore
            inv.paid_amount = new_paid # type: ignore
            inv.outstanding_amount = max(0, float(inv.total_amount or 0) - new_paid) # type: ignore
            inv.update_status()

            applied.append(AppliedMatchSchema(
                invoice_number=str(inv.invoice_number),
                amount_applied=amount,
                new_status=(
                    inv.status.value if hasattr(inv.status, "value") else str(inv.status)
                ),
            ))

        except Exception as e:
            logger.error(f"Failed to apply match for invoice {match.get('invoice_id')}: {e}")
            errors.append(str(e))

    # Optionally mark the parent reconciliation as having been acted upon
    if request.reconciliation_id:
        try:
            recon = db.query(BankReconciliation).filter(
                BankReconciliation.id == uuid.UUID(request.reconciliation_id),
                BankReconciliation.business_id == biz.id,
            ).first()
            if recon:
                recon.status = "applied" # type: ignore
        except Exception:
            pass  # Non-critical; don't fail the whole apply

    db.commit()

    return BankReconciliationApplyResponse(
        applied_count=len(applied),
        error_count=len(errors),
        applied=applied,
        errors=errors,
    )


# ── GET /reconciliation/ ──────────────────────────────────────────────────────

@router.get("/", response_model=BankReconciliationListResponse)
def list_reconciliations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all past bank reconciliation runs for this business, newest first."""
    biz = _get_business(db, current_user)

    q = (
        db.query(BankReconciliation)
        .filter(BankReconciliation.business_id == biz.id)
        .order_by(BankReconciliation.created_at.desc())
    )
    total = q.count()
    total_pages = math.ceil(total / page_size)
    records = q.offset((page - 1) * page_size).limit(page_size).all()

    return BankReconciliationListResponse(
        reconciliations=[BankReconciliationResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── GET /reconciliation/{id} ──────────────────────────────────────────────────

@router.get("/{reconciliation_id}", response_model=BankReconciliationResponse)
def get_reconciliation(
    reconciliation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single reconciliation run including all match results."""
    biz = _get_business(db, current_user)

    recon = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id,
        BankReconciliation.business_id == biz.id,
    ).first()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")

    return BankReconciliationResponse.model_validate(recon)