"""
Document Processing API Endpoints — Bank Statement Version
Location: app/api/v1/endpoints/documents.py

Storage   : Cloudinary
Processing : FastAPI BackgroundTasks (no QStash)
AI         : Groq Vision — no Tesseract for bank statements
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
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc
import traceback
from app.core.database import async_session_factory
    

import cloudinary
import cloudinary.uploader

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.business import Business
from app.models.document import Document, DocumentType, ProcessingStatus
from app.schemas.document import (
    DocumentUploadResponse,
    DocumentResponse,
    DocumentListResponse,
    DocumentUpdate,
    DocumentStatistics,
    BankStatementResponse,
)
from app.services.ai.bank_statement_extractor import BankStatementExtractor
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents - AI Processing"])

# ── Cloudinary config ─────────────────────────────────────────────────────────
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
MAX_FILE_SIZE_MB   = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return business


def convert_decimals(obj):
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def upload_to_cloudinary(file_bytes: bytes, filename: str, business_id: str) -> dict:
    public_id = f"taxflow/{business_id}/{uuid.uuid4()}"
    return cloudinary.uploader.upload(
        file_bytes,
        public_id=public_id,
        resource_type="auto",
        overwrite=False,
        access_mode="public",
        type="upload",
    )


def delete_from_cloudinary(public_id: str, resource_type: str = "image") -> None:
    try:
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as e:
        logger.warning("Could not delete Cloudinary asset %s: %s", public_id, e)


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


# ── Blocking extraction functions (run in thread pool) ────────────────────────

def _run_receipt_extraction(file_path: str, mime_type: str) -> dict:
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
    from app.core.database import async_session_factory
    
    async with async_session_factory() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if not document:
                logger.error("BG TASK: document %s not found", document_id)
                return

            document.status = ProcessingStatus.PROCESSING
            document.processing_started_at = datetime.now(timezone.utc)
            await db.commit()

            start_time = time.time()
            is_statement = document.document_type == DocumentType.BANK_STATEMENT

            if is_statement:
                result_dict = await asyncio.to_thread(
                    _run_bank_statement_extraction,
                    tmp_file_path,
                    mime_type,
                )
            else:
                result_dict = await asyncio.to_thread(
                    _run_receipt_extraction,
                    tmp_file_path,
                    mime_type,
                )

            elapsed = time.time() - start_time

            if result_dict["status"] == "failed":
                document.status = ProcessingStatus.FAILED
                document.processing_error = result_dict["error"]
                document.processing_completed_at = datetime.now(timezone.utc)
                document.processing_duration_seconds = elapsed
                await db.commit()
                return

            if is_statement:
                _apply_bank_statement_data(document, result_dict["data"])
            else:
                _apply_receipt_data(document, result_dict)

            document.status = ProcessingStatus.COMPLETED
            document.processing_completed_at = datetime.now(timezone.utc)
            document.processing_duration_seconds = elapsed
            await db.commit()
            logger.info("Document %s completed in %.2fs", document_id, elapsed)

        except Exception as e:
            logger.error("BG TASK CRASHED for %s: %s", document_id, e, exc_info=True)
            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = ProcessingStatus.FAILED
                    doc.processing_error = str(e)[:500]
                    doc.processing_completed_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                pass
        finally:
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass


def _apply_bank_statement_data(document: Document, data: dict) -> None:
    """Write extracted bank statement fields onto the Document ORM object."""
    # Account info — reuse existing columns
    document.vendor_name     = data.get("account_name")  # type: ignore     # account holder name
    document.document_number = data.get("account_number")  # type: ignore    # account number
    document.vendor_address  = data.get("bank_name")    # type: ignore      # bank name
    document.document_date   = _parse_date(data.get("period_from")) # type: ignore

    # Bank-specific columns
    document.opening_balance     = data.get("opening_balance") # type: ignore
    document.closing_balance     = data.get("closing_balance") # type: ignore
    document.total_inflow        = data.get("total_inflow") # type: ignore
    document.total_outflow       = data.get("total_outflow") # type: ignore
    document.inflow_transactions  = convert_decimals(data.get("inflows", [])) # type: ignore
    document.outflow_transactions = convert_decimals(data.get("outflows", [])) # type: ignore

    # Store full AI response for debugging
    document.ai_extracted_data = convert_decimals(data) # type: ignore
    document.ai_model_used     = "llama-4-scout-17b-16e-instruct"  # type: ignore
    document.confidence_score  = data.get("confidence_score") # type: ignore
    document.requires_review   = (
        data.get("confidence_score", 1.0) < float(
            getattr(settings, "OCR_CONFIDENCE_THRESHOLD", 0.7)
        )
    )


def _apply_receipt_data(document: Document, result_dict: dict) -> None:
    """Write extracted receipt fields onto the Document ORM object."""
    extracted = result_dict["extracted_data"]

    document.ocr_raw_text   = result_dict.get("ocr_text") # type: ignore
    document.ocr_confidence = result_dict.get("ocr_confidence")  # type: ignore

    document.vendor_name     = extracted.get("vendor_name")
    document.vendor_tin      = extracted.get("vendor_tin")
    document.vendor_address  = extracted.get("vendor_address")
    document.vendor_phone    = extracted.get("vendor_phone")
    document.document_number = extracted.get("document_number")
    document.document_date   = _parse_date(extracted.get("document_date")) # type: ignore

    document.line_items        = convert_decimals(extracted.get("line_items", [])) # type: ignore
    document.subtotal          = extracted.get("subtotal", 0)
    document.vat_amount        = extracted.get("vat_amount", 0)
    document.total_amount      = extracted.get("total_amount", 0)
    document.vat_rate          = extracted.get("vat_rate", 7.5)
    document.payment_method    = extracted.get("payment_method")
    document.payment_reference = extracted.get("payment_reference")
    document.category          = extracted.get("category", "Other")
    document.confidence_score  = extracted.get("confidence_score")
    document.requires_review   = extracted.get("requires_review", False)
    document.ai_extracted_data = convert_decimals(extracted) # type: ignore
    document.ai_model_used     = "llama-3.3-70b-versatile" # type: ignore


# ── Static routes BEFORE /{document_id} ──────────────────────────────────────

# ── GET /statistics/summary ───────────────────────────────────────────────────

@router.get("/statistics/summary", response_model=DocumentStatistics)
async def get_document_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        bid = business.id

        status_result = await db.execute(
            select(Document.status, sqlfunc.count(Document.id))
            .where(Document.business_id == bid)
            .group_by(Document.status)
        )
        by_status: dict = {
            (s.value if hasattr(s, "value") else str(s)): cnt
            for s, cnt in status_result.all()
        }

        total_documents    = sum(by_status.values())
        pending_processing = by_status.get("PENDING", 0) + by_status.get("PROCESSING", 0)
        completed          = by_status.get("COMPLETED", 0)
        failed             = by_status.get("FAILED", 0)

        req = await db.execute(
            select(sqlfunc.count(Document.id))
            .where(Document.business_id == bid, Document.requires_review == True)  # noqa: E712
        )
        requires_review = req.scalar_one_or_none() or 0

        total_amt = await db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(Document.total_amount), 0))
            .where(Document.business_id == bid, Document.status == ProcessingStatus.COMPLETED)
        )
        total_amount_processed = Decimal(str(total_amt.scalar_one_or_none() or 0))

        avg = await db.execute(
            select(sqlfunc.avg(Document.confidence_score))
            .where(Document.business_id == bid, Document.confidence_score.isnot(None))
        )
        avg_p = await db.execute(
            select(sqlfunc.avg(Document.processing_duration_seconds))
            .where(Document.business_id == bid, Document.processing_duration_seconds.isnot(None))
        )

        types = await db.execute(
            select(Document.document_type, sqlfunc.count(Document.id))
            .where(Document.business_id == bid)
            .group_by(Document.document_type)
        )
        by_type: dict = {
            (t.value if hasattr(t, "value") else str(t)): cnt
            for t, cnt in types.all()
        }

        cat = await db.execute(
            select(Document.category, sqlfunc.count(Document.id))
            .where(Document.business_id == bid, Document.category.isnot(None))
            .group_by(Document.category)
        )
        by_category: dict = {(c or "Unknown"): cnt for c, cnt in cat.all()}

        avg_confidence      = avg.scalar()
        avg_processing_time = avg_p.scalar()

        return {
            "total_documents":          total_documents,
            "pending_processing":       pending_processing,
            "completed":                completed,
            "failed":                   failed,
            "requires_review":          requires_review,
            "total_amount_processed":   total_amount_processed,
            "average_confidence_score": float(avg_confidence) if avg_confidence else None,
            "average_processing_time":  float(avg_processing_time) if avg_processing_time else None,
            "by_type":                  by_type,
            "by_category":              by_category,
            "by_status":                by_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to get statistics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET / ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    document_type: Optional[DocumentType] = None,
    status: Optional[ProcessingStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        query = select(Document).where(Document.business_id == business.id)

        if document_type:
            query = query.where(Document.document_type == document_type)
        if status:
            query = query.where(Document.status == status)

        total_result = await db.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )
        total = total_result.scalar_one()

        docs_result = await db.execute(
            query.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        documents = docs_result.scalars().all()

        return DocumentListResponse(
            documents=documents, # type: ignore
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 1,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to list documents: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    """
    Upload a document for AI processing.

    - BANK_STATEMENT → Groq Vision extracts inflows/outflows (no Tesseract)
    - RECEIPT/INVOICE → OCR + Groq text extraction

    Supported formats: PNG, JPG, PDF (max 10 MB).
    Processing runs in background — poll GET /documents/{id} for status.
    """
    business = await get_user_business(db, current_user.id) # type: ignore

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PNG, JPG, PDF",
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

    # Validate document_type enum early for a clear error message
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type: {document_type}. "
                   f"Allowed: {[e.value for e in DocumentType]}",
        )

    # Upload to Cloudinary
    try:
        cloud_result         = upload_to_cloudinary(file_bytes, file.filename or "document", str(business.id))
        cloudinary_url       = cloud_result["secure_url"]
        cloudinary_public_id = cloud_result["public_id"]
        logger.info("Uploaded to Cloudinary: %s", cloudinary_public_id)
    except Exception as e:
        logger.error("Cloudinary upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="File upload to Cloudinary failed")

    # Create DB record
    try:
        document = Document(
            business_id=business.id,
            document_type=doc_type,
            original_filename=file.filename or "unknown",
            file_path=cloudinary_url,
            file_size=file_size,
            file_type=file.content_type,
            status=ProcessingStatus.PENDING,
            notes=notes,
            review_notes=cloudinary_public_id,  # stores public_id for deletion
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        logger.info("Document record created: %s", document.id)
    except Exception as e:
        try:
            cloudinary.uploader.destroy(cloudinary_public_id, resource_type="auto")
        except Exception:
            pass
        logger.error("DB write failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create document record")

    # Write file bytes to a temp path so the background task can read them
    # (file_bytes would be lost after the request returns)
    suffix = _ext_from_mimetype(file.content_type)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_bytes)
    tmp.close()
    tmp_path_for_bg = tmp.name

    background_tasks.add_task(
        process_document_background,
        document.id,  # type: ignore
        tmp_path_for_bg,
        file.content_type,
    )
    logger.info("Queued background processing for document: %s", document.id)

    return DocumentUploadResponse(
        document_id=document.id, # type: ignore
        status=document.status, # type: ignore
        message=(
            "Bank statement uploaded. Extracting inflows and outflows..."
            if doc_type == DocumentType.BANK_STATEMENT
            else "Document uploaded. AI processing started."
        ),
        estimated_completion_seconds=20 if doc_type == DocumentType.BANK_STATEMENT else 15,
    )


# ── GET /{document_id} ────────────────────────────────────────────────────────

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to get document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET /{document_id}/bank-summary ──────────────────────────────────────────

@router.get("/{document_id}/bank-summary", response_model=BankStatementResponse)
async def get_bank_statement_summary(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns structured inflow/outflow summary for a bank statement document.
    Returns 400 if the document is not a BANK_STATEMENT type.
    """
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if document.document_type != DocumentType.BANK_STATEMENT: # type: ignore
            raise HTTPException(
                status_code=400,
                detail="This document is not a bank statement",
            )
        return BankStatementResponse(
            id=str(document.id),
            business_id=str(document.business_id),
            document_type=document.document_type.value,
            original_filename=document.original_filename, # type: ignore
            file_path=document.file_path, # type: ignore
            status=document.status.value,
            account_name=document.vendor_name, # type: ignore
            account_number=document.document_number, # type: ignore
            bank_name=document.vendor_address, # type: ignore
            period_from=document.document_date, # type: ignore
            opening_balance=document.opening_balance, # type: ignore
            closing_balance=document.closing_balance, # type: ignore
            total_inflow=document.total_inflow, # type: ignore
            total_outflow=document.total_outflow, # type: ignore
            inflow_transactions=document.inflow_transactions, # type: ignore
            outflow_transactions=document.outflow_transactions, # type: ignore
            confidence_score=document.confidence_score, # type: ignore
            processing_error=document.processing_error, # type: ignore
            ai_model_used=document.ai_model_used, # type: ignore
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to get bank summary %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET /{document_id}/download ───────────────────────────────────────────────

@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return RedirectResponse(url=document.file_path, status_code=302) # type: ignore
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to download document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── POST /{document_id}/reprocess ─────────────────────────────────────────────

@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        document.status                      = ProcessingStatus.PENDING # type: ignore
        document.processing_error            = None # type: ignore
        document.processing_completed_at     = None # type: ignore
        document.processing_started_at       = None # type: ignore
        document.processing_duration_seconds = None # type: ignore
        document.ocr_raw_text                = None # type: ignore
        await db.commit()

        background_tasks.add_task(process_document_background, document.id) # type: ignore

        return DocumentUploadResponse(
            document_id=document.id, # type: ignore
            status=document.status, # type: ignore
            message="Document requeued for AI processing.",
            estimated_completion_seconds=20,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to reprocess document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── PATCH /{document_id} ──────────────────────────────────────────────────────

@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    update_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(document, field, value)

        await db.commit()
        await db.refresh(document)
        return document
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to update document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── DELETE /{document_id} ─────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id) # type: ignore

        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        if document.cloudinary_public_id: # type: ignore
            delete_from_cloudinary(document.cloudinary_public_id, resource_type="auto") # type: ignore

        await db.delete(document)
        await db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")