"""
Bank Statement Reconciliation Endpoints (ASYNC VERSION)
"""

import math
import uuid
import logging
import tempfile
import os
from datetime import date as date_type, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

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

async def _get_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalar_one_or_none()

    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")

    return biz


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import fitz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        doc = fitz.open(tmp_path)
        text = "\n".join(page.get_text() for page in doc)  # type: ignore
        doc.close()
        os.unlink(tmp_path)
        return text
    except ImportError:
        logger.warning("PyMuPDF not installed — fallback to raw decode")
        return file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return file_bytes.decode("utf-8", errors="replace")


# ── POST /upload ──────────────────────────────────────────────────────────────

@router.post("/upload", response_model=BankReconciliationUploadResponse, status_code=201)
async def upload_bank_statement(
    file: UploadFile = File(...),
    bank_name: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)

    content = await file.read()
    filename = file.filename or "statement"

    if filename.lower().endswith(".pdf") or file.content_type == "application/pdf":
        text = _extract_pdf_text(content)
    else:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text.")

    reconciler = BankReconciler()
    transactions = reconciler.parse_statement_text(text, bank_name)

    if not transactions:
        raise HTTPException(status_code=422, detail="No credit transactions found.")

    # ⚠️ IMPORTANT: keep db passed as-is (no await inside service)
    matches = await  reconciler.match_transactions(transactions, str(biz.id), db)

    matched   = [m for m in matches if m["matched"]] # type: ignore
    unmatched = [m for m in matches if not m["matched"]] # type: ignore
    total_credits = round(sum(float(m["transaction"].get("amount", 0)) for m in matches), 2) # type: ignore

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
    await db.commit()
    await db.refresh(recon)

    return BankReconciliationUploadResponse(
        reconciliation_id=str(recon.id),
        filename=filename,
        bank_name=bank_name or "Unknown",
        total_transactions=len(transactions),
        matched_count=len(matched),
        unmatched_count=len(unmatched),
        total_credit_amount=total_credits,
        status="completed",
        matches=matches, # type: ignore
    )


# ── POST /apply ───────────────────────────────────────────────────────────────

@router.post("/apply", response_model=BankReconciliationApplyResponse)
async def apply_reconciliation(
    request: ApplyMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)

    applied = []
    errors: list[str] = []

    for match in request.matches:
        if not match.get("matched") or not match.get("invoice_id"):
            continue

        try:
            result = await db.execute(
                select(Invoice).where(
                    Invoice.id == uuid.UUID(match["invoice_id"]),
                    Invoice.business_id == biz.id,
                )
            )
            inv = result.scalar_one_or_none()

            if not inv:
                errors.append(f"Invoice {match['invoice_id']} not found")
                continue

            txn = match["transaction"]

            try:
                txn_date = date_type.fromisoformat(txn.get("date"))
            except Exception:
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
                new_status=str(inv.status.value if hasattr(inv.status, "value") else inv.status),
            ))

        except Exception as e:
            logger.error(f"Apply failed: {e}")
            errors.append(str(e))

    if request.reconciliation_id:
        try:
            result = await db.execute(
                select(BankReconciliation).where(
                    BankReconciliation.id == uuid.UUID(request.reconciliation_id),
                    BankReconciliation.business_id == biz.id,
                )
            )
            recon = result.scalar_one_or_none()
            if recon:
                recon.status = "applied" # type: ignore
        except Exception:
            pass

    await db.commit()

    return BankReconciliationApplyResponse(
        applied_count=len(applied),
        error_count=len(errors),
        applied=applied,
        errors=errors,
    )


# ── GET / ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=BankReconciliationListResponse)
async def list_reconciliations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)

    # total count
    result = await db.execute(
        select(func.count()).select_from(BankReconciliation).where(
            BankReconciliation.business_id == biz.id
        )
    )
    total = result.scalar() or 0

    total_pages = math.ceil(total / page_size)

    result = await db.execute(
        select(BankReconciliation)
        .where(BankReconciliation.business_id == biz.id)
        .order_by(BankReconciliation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = result.scalars().all()

    return BankReconciliationListResponse(
        reconciliations=[BankReconciliationResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── GET /{id} ─────────────────────────────────────────────────────────────────

@router.get("/{reconciliation_id}", response_model=BankReconciliationResponse)
async def get_reconciliation(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = await _get_business(db, current_user)

    result = await db.execute(
        select(BankReconciliation).where(
            BankReconciliation.id == reconciliation_id,
            BankReconciliation.business_id == biz.id,
        )
    )
    recon = result.scalar_one_or_none()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    return BankReconciliationResponse.model_validate(recon)