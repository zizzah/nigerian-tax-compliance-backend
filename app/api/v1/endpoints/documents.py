"""
Document Processing API Endpoints
Location: app/api/v1/endpoints/documents.py

Storage   : None — files are processed in memory and discarded
Processing : FastAPI BackgroundTasks
AI         : Groq Vision (bank statements), OCR + Groq text (receipts)
"""
import asyncio
import math
import logging
import uuid
import time
import os
import tempfile
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.core.database import get_db, async_session_factory
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.receipt import Receipt
from app.models.bank_statement import BankStatement
from app.schemas.document import DocumentUploadResponse, DocumentStatistics
from app.schemas.receipt import ReceiptResponse, ReceiptListResponse, ReceiptUpdate
from app.schemas.bank_statement import BankStatementResponse, BankStatementListResponse, BankStatementUpdate
from app.services.ai.bank_statement_extractor import BankStatementExtractor
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents - AI Processing"])

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
MAX_FILE_SIZE_MB   = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return business


def _ext_from_mimetype(mime: str) -> str:
    return {
        "image/png":       ".png",
        "image/jpeg":      ".jpg",
        "image/jpg":       ".jpg",
        "application/pdf": ".pdf",
    }.get(mime, ".jpg")


def _parse_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _convert_decimals(obj):
    """Recursively convert Decimal and date objects for JSONB storage."""
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


# ── Blocking extraction (runs in thread pool) ─────────────────────────────────

def _run_receipt_extraction(file_path: str) -> dict:
    try:
        preprocessor = ImagePreprocessor()
        preprocessed = preprocessor.preprocess(file_path)

        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed)

        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text")

        groq = GroqReceiptExtractor()
        extracted = groq.extract_receipt_data(ocr_text=ocr_text)

        if not extracted.get("category"):
            try:
                items = extracted.get("line_items", [])
                description = items[0].get("description", "") if items else ""
                extracted["category"] = groq.categorize_expense(
                    description, extracted.get("vendor_name", "")
                )
            except Exception:
                extracted["category"] = "Other"

        return {
            "status": "success",
            "extracted_data": extracted,
            "ocr_text": ocr_text,
            "ocr_confidence": ocr_confidence,
            "error": None,
        }

    except Exception as e:
        logger.error("Receipt extraction failed: %s", e, exc_info=True)
        return {
            "status": "failed",
            "extracted_data": {},
            "ocr_text": None,
            "ocr_confidence": None,
            "error": str(e)[:500],
        }


def _run_bank_statement_extraction(file_path: str, mime_type: str) -> dict:
    try:
        extractor = BankStatementExtractor()
        data = extractor.extract(file_path, mime_type)
        return {"status": "success", "data": data, "error": None}
    except Exception as e:
        logger.error("Bank statement extraction failed: %s", e, exc_info=True)
        return {"status": "failed", "data": {}, "error": str(e)[:500]}


# ── Background task ───────────────────────────────────────────────────────────

async def process_document_background(
    document_id: uuid.UUID,
    tmp_file_path: str,
    mime_type: str,
) -> None:
    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if not document:
                logger.error("BG TASK: document %s not found", document_id)
                return

            document.status = ProcessingStatus.PROCESSING # type: ignore
            document.processing_started_at = datetime.now(timezone.utc) # type: ignore
            await db.commit()

            start_time = time.time()
            is_statement = document.document_type == DocumentType.BANK_STATEMENT

            if is_statement: # type: ignore
                result_dict = await asyncio.to_thread(
                    _run_bank_statement_extraction,
                    tmp_file_path,
                    mime_type,
                )
            else:
                result_dict = await asyncio.to_thread(
                    _run_receipt_extraction,
                    tmp_file_path,
                )

            elapsed = time.time() - start_time

            if result_dict["status"] == "failed":
                document.status = ProcessingStatus.FAILED # type: ignore
                document.processing_error = result_dict["error"]
                document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
                document.processing_duration_seconds = Decimal(str(round(elapsed, 2))) # type: ignore
                await db.commit()
                return

            # ── Write to child table ──────────────────────────────────────────
            if is_statement: # type: ignore
                child = _build_bank_statement(document, result_dict["data"])
            else:
                child = _build_receipt(document, result_dict)

            db.add(child)

            # ── Update document processing metadata ───────────────────────────
            document.status = ProcessingStatus.COMPLETED # type: ignore
            document.confidence_score = child.ai_extracted_data.get("confidence_score") if child.ai_extracted_data else None  # type: ignore
            document.ai_model_used = (  # type: ignore
                "llama-4-scout-17b-16e-instruct"
                if is_statement  # type: ignore
                else "llama-3.3-70b-versatile"
            )
            document.requires_review = _needs_review(child, is_statement) # type: ignore
            document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
            document.processing_duration_seconds = Decimal(str(round(elapsed, 2))) # type: ignore

            await db.commit()
            logger.info("Document %s completed in %.2fs", document_id, elapsed)

        except Exception as e:
            logger.error("BG TASK CRASHED for %s: %s", document_id, e, exc_info=True)
            try:
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = ProcessingStatus.FAILED # type: ignore
                    doc.processing_error = str(e)[:500] # type: ignore
                    doc.processing_completed_at = datetime.now(timezone.utc) # type: ignore
                    await db.commit()
            except Exception:
                pass
        finally:
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass


def _build_receipt(document: Document, result_dict: dict) -> Receipt:
    """Build a Receipt ORM object from extraction results."""
    extracted = result_dict["extracted_data"]
    return Receipt(
        document_id=document.id,
        business_id=document.business_id,
        document_type=document.document_type,
        ocr_raw_text=result_dict.get("ocr_text"),
        ocr_confidence=result_dict.get("ocr_confidence"),
        vendor_name=extracted.get("vendor_name"),
        vendor_tin=extracted.get("vendor_tin"),
        vendor_address=extracted.get("vendor_address"),
        vendor_phone=extracted.get("vendor_phone"),
        document_number=extracted.get("document_number"),
        document_date=_parse_date(extracted.get("document_date")),
        line_items=_convert_decimals(extracted.get("line_items", [])),
        subtotal=extracted.get("subtotal", 0),
        vat_amount=extracted.get("vat_amount", 0),
        total_amount=extracted.get("total_amount", 0),
        vat_rate=extracted.get("vat_rate", 7.5),
        payment_method=extracted.get("payment_method"),
        payment_reference=extracted.get("payment_reference"),
        category=extracted.get("category", "Other"),
        ai_extracted_data=_convert_decimals(extracted),
    )


def _build_bank_statement(document: Document, data: dict) -> BankStatement:
    """Build a BankStatement ORM object from extraction results."""
    return BankStatement(
        document_id=document.id,
        business_id=document.business_id,
        account_name=data.get("account_name"),
        account_number=data.get("account_number"),
        bank_name=data.get("bank_name"),
        period_from=_parse_date(data.get("period_from")),
        period_to=_parse_date(data.get("period_to")),
        opening_balance=data.get("opening_balance"),
        closing_balance=data.get("closing_balance"),
        total_inflow=data.get("total_inflow"),
        total_outflow=data.get("total_outflow"),
        inflow_transactions=_convert_decimals(data.get("inflows", [])),
        outflow_transactions=_convert_decimals(data.get("outflows", [])),
        ai_extracted_data=_convert_decimals(data),
    )


def _needs_review(child, is_statement: bool) -> bool:
    """Determine if document needs human review."""
    if is_statement:
        data = child.ai_extracted_data or {}
        return float(data.get("confidence_score", 1.0)) < float(
            getattr(settings, "OCR_CONFIDENCE_THRESHOLD", 0.7)
        )
    extracted = child.ai_extracted_data or {}
    return bool(extracted.get("requires_review", False))


# ── POST /upload ──────────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(default="RECEIPT"),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PNG, JPG, PDF",
        )

    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type: {document_type}. Allowed: {[e.value for e in DocumentType]}",
        )

    file_bytes = await file.read()
    file_size  = len(file_bytes)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {file_size / (1024*1024):.1f} MB (max {MAX_FILE_SIZE_MB} MB)",
        )

    # Create Document record — no Cloudinary, no file_path
    document = Document(
        business_id=business.id,
        document_type=doc_type,
        original_filename=file.filename or "unknown",
        file_size=file_size,
        file_type=file.content_type,
        status=ProcessingStatus.PENDING,
        notes=notes,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Write to temp file — background task reads this, then deletes it
    suffix  = _ext_from_mimetype(file.content_type)
    tmp     = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_bytes)
    tmp.close()

    background_tasks.add_task(
        process_document_background,
        document.id,  # type: ignore
        tmp.name,
        file.content_type,
    )

    return DocumentUploadResponse(
        document_id=document.id,  # type: ignore
        status=document.status,  # type: ignore
        message=(
            "Bank statement uploaded. Extracting inflows and outflows..."
            if doc_type == DocumentType.BANK_STATEMENT
            else "Document uploaded. AI processing started."
        ),
        estimated_completion_seconds=20 if doc_type == DocumentType.BANK_STATEMENT else 15,
    )


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    result = await db.execute(
        select(Document.status, Document.processing_error)
        .where(Document.id == document_id, Document.business_id == business.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": row.status, "processing_error": row.processing_error}


@router.get("/{document_id}/receipt", response_model=ReceiptResponse)
async def get_receipt_by_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    row = (await db.execute(
        select(Receipt, Document)
        .join(Document, Receipt.document_id == Document.id)
        .where(Receipt.document_id == document_id, Receipt.business_id == business.id)
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return _merge_receipt_response(*row)


# ── GET /receipts ─────────────────────────────────────────────────────────────

@router.get("/receipts", response_model=ReceiptListResponse)
async def list_receipts(
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore

    query = (
        select(Receipt, Document)
        .join(Document, Receipt.document_id == Document.id)
        .where(Receipt.business_id == business.id)
    )
    if category:
        query = query.where(Receipt.category == category)

    total = (await db.execute(
        select(sqlfunc.count()).select_from(query.subquery())
    )).scalar_one()

    rows = (await db.execute(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()

    receipts = [_merge_receipt_response(receipt, document) for receipt, document in rows]

    return ReceiptListResponse(
        receipts=receipts,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ── GET /bank-statements ──────────────────────────────────────────────────────

@router.get("/bank-statements", response_model=BankStatementListResponse)
async def list_bank_statements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore

    query = (
        select(BankStatement, Document)
        .join(Document, BankStatement.document_id == Document.id)
        .where(BankStatement.business_id == business.id)
    )

    total = (await db.execute(
        select(sqlfunc.count()).select_from(query.subquery())
    )).scalar_one()

    rows = (await db.execute(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()

    statements = [_merge_bank_statement_response(bs, document) for bs, document in rows]

    return BankStatementListResponse(
        statements=statements,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ── GET /receipts/{receipt_id} ────────────────────────────────────────────────

@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    row = (await db.execute(
        select(Receipt, Document)
        .join(Document, Receipt.document_id == Document.id)
        .where(Receipt.id == receipt_id, Receipt.business_id == business.id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return _merge_receipt_response(*row)


# ── GET /bank-statements/{statement_id} ───────────────────────────────────────

@router.get("/bank-statements/{statement_id}", response_model=BankStatementResponse)
async def get_bank_statement(
    statement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    row = (await db.execute(
        select(BankStatement, Document)
        .join(Document, BankStatement.document_id == Document.id)
        .where(BankStatement.id == statement_id, BankStatement.business_id == business.id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    return _merge_bank_statement_response(*row)


# ── PATCH /receipts/{receipt_id} ──────────────────────────────────────────────

@router.patch("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def update_receipt(
    receipt_id: uuid.UUID,
    update_data: ReceiptUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    row = (await db.execute(
        select(Receipt, Document)
        .join(Document, Receipt.document_id == Document.id)
        .where(Receipt.id == receipt_id, Receipt.business_id == business.id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    receipt, document = row
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(receipt, field, value)

    await db.commit()
    await db.refresh(receipt)
    return _merge_receipt_response(receipt, document)


# ── PATCH /bank-statements/{statement_id} ─────────────────────────────────────

@router.patch("/bank-statements/{statement_id}", response_model=BankStatementResponse)
async def update_bank_statement(
    statement_id: uuid.UUID,
    update_data: BankStatementUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    row = (await db.execute(
        select(BankStatement, Document)
        .join(Document, BankStatement.document_id == Document.id)
        .where(BankStatement.id == statement_id, BankStatement.business_id == business.id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    statement, document = row
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(statement, field, value)

    await db.commit()
    await db.refresh(statement)
    return _merge_bank_statement_response(statement, document)


# ── DELETE /{document_id} ─────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # CASCADE on FK handles receipts/bank_statements deletion automatically
    await db.delete(document)
    await db.commit()


# ── GET /statistics/summary ───────────────────────────────────────────────────

@router.get("/statistics/summary", response_model=DocumentStatistics)
async def get_document_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(db, current_user.id)  # type: ignore
    bid = business.id

    by_status_rows = (await db.execute(
        select(Document.status, sqlfunc.count(Document.id))
        .where(Document.business_id == bid)
        .group_by(Document.status)
    )).all()
    by_status = {
        (s.value if hasattr(s, "value") else str(s)): cnt
        for s, cnt in by_status_rows
    }

    total_documents    = sum(by_status.values())
    pending_processing = by_status.get("PENDING", 0) + by_status.get("PROCESSING", 0)
    completed          = by_status.get("COMPLETED", 0)
    failed             = by_status.get("FAILED", 0)

    requires_review = (await db.execute(
        select(sqlfunc.count(Document.id))
        .where(Document.business_id == bid, Document.requires_review == True)  # noqa: E712
    )).scalar_one_or_none() or 0

    # total_amount lives on receipts now
    total_amount_processed = Decimal(str(
        (await db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(Receipt.total_amount), 0))
            .join(Document, Receipt.document_id == Document.id)
            .where(Receipt.business_id == bid, Document.status == ProcessingStatus.COMPLETED)
        )).scalar_one_or_none() or 0
    ))

    avg_confidence = (await db.execute(
        select(sqlfunc.avg(Document.confidence_score))
        .where(Document.business_id == bid, Document.confidence_score.isnot(None))
    )).scalar()

    avg_processing_time = (await db.execute(
        select(sqlfunc.avg(Document.processing_duration_seconds))
        .where(Document.business_id == bid, Document.processing_duration_seconds.isnot(None))
    )).scalar()

    by_type = {
        (t.value if hasattr(t, "value") else str(t)): cnt
        for t, cnt in (await db.execute(
            select(Document.document_type, sqlfunc.count(Document.id))
            .where(Document.business_id == bid)
            .group_by(Document.document_type)
        )).all()
    }

    by_status_final = by_status

    return DocumentStatistics(
        total_documents=total_documents,
        pending_processing=pending_processing,
        completed=completed,
        failed=failed,
        requires_review=requires_review,
        total_amount_processed=total_amount_processed,
        average_confidence_score=float(avg_confidence) if avg_confidence else None,
        average_processing_time=float(avg_processing_time) if avg_processing_time else None,
        by_type=by_type,
        by_status=by_status_final,
    )


@router.post("/debug/pdf-extract")
async def debug_pdf_extract(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Temporary debug endpoint — remove after investigation."""
    import tempfile, os
    import fitz

    file_bytes = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(file_bytes)
    tmp.close()

    try:
        doc = fitz.open(tmp.name)
        result = {}
        for page_num in range(len(doc)):
            page = doc[page_num]
            words = page.get_text("words")
            result[f"page_{page_num+1}"] = {
                "word_count": len(words),
                "first_50_words": [
                    {"text": w[4], "x": round(w[0], 1), "y": round(w[1], 1)} # type: ignore
                    for w in words[:50]
                ]
            }
        doc.close()
        return result
    finally:
        os.unlink(tmp.name)





# ── Response builders ─────────────────────────────────────────────────────────

def _merge_receipt_response(receipt: Receipt, document: Document) -> ReceiptResponse:
    """Merge Document + Receipt into a single ReceiptResponse."""
    return ReceiptResponse(
        # From Document
        id=document.id,  # type: ignore
        business_id=document.business_id,  # type: ignore
        document_type=document.document_type,  # type: ignore
        original_filename=document.original_filename,  # type: ignore
        file_size=document.file_size,  # type: ignore
        file_type=document.file_type,  # type: ignore
        status=document.status,  # type: ignore
        confidence_score=document.confidence_score,  # type: ignore
        processing_error=document.processing_error,  # type: ignore
        processing_duration_seconds=document.processing_duration_seconds,  # type: ignore
        processing_completed_at=document.processing_completed_at,  # type: ignore
        ai_model_used=document.ai_model_used,  # type: ignore
        requires_review=document.requires_review,  # type: ignore
        review_notes=document.review_notes,  # type: ignore
        reviewed_by_user_id=document.reviewed_by_user_id,  # type: ignore
        reviewed_at=document.reviewed_at,  # type: ignore
        notes=document.notes,  # type: ignore
        is_archived=document.is_archived,  # type: ignore
        created_at=document.created_at,  # type: ignore
        updated_at=document.updated_at,  # type: ignore
        # From Receipt
        customer_id=receipt.customer_id,  # type: ignore
        vendor_id=receipt.vendor_id,  # type: ignore
        document_number=receipt.document_number,  # type: ignore
        document_date=receipt.document_date,  # type: ignore
        vendor_name=receipt.vendor_name,  # type: ignore
        vendor_tin=receipt.vendor_tin,  # type: ignore
        vendor_address=receipt.vendor_address,  # type: ignore
        vendor_phone=receipt.vendor_phone,  # type: ignore
        line_items=receipt.line_items,  # type: ignore
        subtotal=receipt.subtotal,  # type: ignore
        vat_amount=receipt.vat_amount,  # type: ignore
        total_amount=receipt.total_amount,  # type: ignore
        vat_rate=receipt.vat_rate,  # type: ignore
        is_vatable=receipt.is_vatable,  # type: ignore
        payment_method=receipt.payment_method,  # type: ignore
        payment_reference=receipt.payment_reference,  # type: ignore
        category=receipt.category,  # type: ignore
        tags=receipt.tags,  # type: ignore
        ocr_confidence=receipt.ocr_confidence,  # type: ignore
        ai_extracted_data=receipt.ai_extracted_data,  # type: ignore
    )


def _merge_bank_statement_response(statement: BankStatement, document: Document) -> BankStatementResponse:
    """Merge Document + BankStatement into a single BankStatementResponse."""
    return BankStatementResponse(
        # From Document
        id=document.id,  # type: ignore
        business_id=document.business_id,  # type: ignore
        document_type=document.document_type,  # type: ignore
        original_filename=document.original_filename,  # type: ignore
        file_size=document.file_size,  # type: ignore
        file_type=document.file_type,  # type: ignore
        status=document.status,  # type: ignore
        confidence_score=document.confidence_score,  # type: ignore
        processing_error=document.processing_error,  # type: ignore
        processing_duration_seconds=document.processing_duration_seconds,  # type: ignore
        processing_completed_at=document.processing_completed_at,  # type: ignore
        ai_model_used=document.ai_model_used,  # type: ignore
        requires_review=document.requires_review,  # type: ignore
        review_notes=document.review_notes,  # type: ignore
        reviewed_by_user_id=document.reviewed_by_user_id,  # type: ignore
        reviewed_at=document.reviewed_at,  # type: ignore
        notes=document.notes,  # type: ignore
        is_archived=document.is_archived,  # type: ignore
        created_at=document.created_at,  # type: ignore
        updated_at=document.updated_at,  # type: ignore
        # From BankStatement
        account_name=statement.account_name,  # type: ignore
        account_number=statement.account_number,  # type: ignore
        bank_name=statement.bank_name,  # type: ignore
        period_from=statement.period_from,  # type: ignore
        period_to=statement.period_to,  # type: ignore
        opening_balance=statement.opening_balance,  # type: ignore
        closing_balance=statement.closing_balance,  # type: ignore
        total_inflow=statement.total_inflow,  # type: ignore
        total_outflow=statement.total_outflow,  # type: ignore
        inflow_transactions=statement.inflow_transactions,  # type: ignore
        outflow_transactions=statement.outflow_transactions,  # type: ignore
    )