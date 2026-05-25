"""
Document Processing API Endpoints
Location: app/api/v1/endpoints/documents.py

Storage  : Cloudinary (persists across Render deploys)
Processing: FastAPI BackgroundTasks (no QStash dependency)
AI       : Groq llama-3.3-70b-versatile
"""
import asyncio
import math
import logging
import uuid
import time
import os
import urllib.request
import tempfile
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

import cloudinary
import cloudinary.uploader

from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor

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
)
from app.core.database import async_session_factory  # local import avoids circular deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents - AI Processing"])

# ── Configure Cloudinary ──────────────────────────────────────────────────────
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_user_business(db: AsyncSession, user_id: uuid.UUID) -> Business:
    result = await db.execute(select(Business).where(Business.user_id == user_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business


def _run_ocr_and_extraction_from_bytes(file_bytes: bytes, mime_type: str) -> dict:
    """For fresh uploads — bytes already in memory, no Cloudinary download needed."""
    tmp_path = None
    try:
        suffix = _ext_from_mimetype(mime_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        preprocessor = ImagePreprocessor()
        preprocessed_image = preprocessor.preprocess(tmp_path)

        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)

        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text from document")

        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)

        if not extracted_data.get("category"):
            try:
                line_items = extracted_data.get("line_items", [])
                description = line_items[0].get("description", "") if line_items else ""
                extracted_data["category"] = groq.categorize_expense(
                    description, extracted_data.get("vendor_name", "")
                )
            except Exception:
                extracted_data["category"] = "Other"

        return {
            "status":         "success",
            "extracted_data": extracted_data,
            "ocr_text":       ocr_text,
            "ocr_confidence": ocr_confidence,
            "error":          None,
        }

    except Exception as e:
        logger.error("OCR/extraction failed: %s", e, exc_info=True)
        return {
            "status":         "failed",
            "extracted_data": {},
            "ocr_text":       None,
            "ocr_confidence": None,
            "error":          str(e)[:500],
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass



def convert_decimals(obj):
    """Recursively convert Decimal and date objects for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def upload_to_cloudinary(file_bytes: bytes, filename: str, business_id: str, mime_type: str) -> dict:
    resource_type = "raw" if mime_type == "application/pdf" else "image"
    public_id = f"taxflow/{business_id}/{uuid.uuid4()}"
    return cloudinary.uploader.upload(
        file_bytes,
        public_id=public_id,
        resource_type=resource_type,
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


# ── Core processing logic (blocking I/O — runs in thread pool) ────────────────

def _run_ocr_and_extraction(cloudinary_url: str, mime_type: str) -> dict:
    """
    Download file from Cloudinary, run OCR, run Groq extraction.
    This is pure blocking I/O — always call via asyncio.to_thread().

    Returns a result dict with keys: status, extracted_data, ocr_text,
    ocr_confidence, error.
    """
    tmp_path = None
    try:
        suffix = _ext_from_mimetype(mime_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name

        req = urllib.request.Request(
            cloudinary_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(tmp_path, "wb") as f:
                f.write(resp.read())

        preprocessor = ImagePreprocessor()
        preprocessed_image = preprocessor.preprocess(tmp_path)

        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)

        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text from document")

        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)

        # Auto-categorise if Groq didn't
        if not extracted_data.get("category"):
            try:
                line_items = extracted_data.get("line_items", [])
                description = line_items[0].get("description", "") if line_items else ""
                extracted_data["category"] = groq.categorize_expense(
                    description, extracted_data.get("vendor_name", "")
                )
            except Exception:
                extracted_data["category"] = "Other"

        return {
            "status":         "success",
            "extracted_data": extracted_data,
            "ocr_text":       ocr_text,
            "ocr_confidence": ocr_confidence,
            "error":          None,
        }

    except Exception as e:
        logger.error("OCR/extraction failed: %s", e, exc_info=True)
        return {
            "status":         "failed",
            "extracted_data": {},
            "ocr_text":       None,
            "ocr_confidence": None,
            "error":          str(e)[:500],
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Background task (called by BackgroundTasks) ───────────────────────────────

async def process_document_background(
    document_id: uuid.UUID,
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> None:
    async with async_session_factory() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document:
                logger.error("Background task: document %s not found", document_id)
                return

            document.status = ProcessingStatus.PROCESSING # type: ignore
            document.processing_started_at = datetime.now(timezone.utc) # type: ignore
            await db.commit()

            start_time = time.time()

            logger.info(
                "PROCESSING_DEBUG: document_id=%s file_path=%s file_type=%s bytes_passed=%s",
                document_id,
                document.file_path,
                document.file_type,
                file_bytes is not None,
            )

            if file_bytes and mime_type:
                result_dict = await asyncio.to_thread(
                    _run_ocr_and_extraction_from_bytes,
                    file_bytes,
                    mime_type,
                )
            else:
                logger.info("No bytes passed — downloading from Cloudinary: %s", document.file_path)
                result_dict = await asyncio.to_thread(
                    _run_ocr_and_extraction,
                    document.file_path, # type: ignore
                    document.file_type,  # type: ignore
                )

            if result_dict["status"] == "failed":
                document.status = ProcessingStatus.FAILED  # type: ignore
                document.processing_error = result_dict["error"]
                document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
                document.processing_duration_seconds = time.time() - start_time # type: ignore
                await db.commit()
                logger.error("Document %s processing failed: %s", document_id, result_dict["error"])
                return

            extracted = result_dict["extracted_data"]

            document.ocr_raw_text   = result_dict["ocr_text"]
            document.ocr_confidence = result_dict["ocr_confidence"]

            document.vendor_name     = extracted.get("vendor_name")
            document.vendor_tin      = extracted.get("vendor_tin")
            document.vendor_address  = extracted.get("vendor_address")
            document.vendor_phone    = extracted.get("vendor_phone")
            document.document_number = extracted.get("document_number")

            doc_date = extracted.get("document_date")
            if isinstance(doc_date, date):
                document.document_date = doc_date # type: ignore
            elif isinstance(doc_date, str):
                try:
                    document.document_date = datetime.strptime(doc_date, "%Y-%m-%d").date() # type: ignore
                except Exception:
                    document.document_date = None # type: ignore
            else:
                document.document_date = None  # type: ignore

            document.line_items        = convert_decimals(extracted.get("line_items", []))  # type: ignore
            document.subtotal          = extracted.get("subtotal", 0)
            document.vat_amount        = extracted.get("vat_amount", 0)
            document.total_amount      = extracted.get("total_amount", 0)
            document.vat_rate          = extracted.get("vat_rate", 7.5)
            document.payment_method    = extracted.get("payment_method")
            document.payment_reference = extracted.get("payment_reference")
            document.category          = extracted.get("category", "Other")
            document.confidence_score  = extracted.get("confidence_score")
            document.requires_review   = extracted.get("requires_review", False)
            document.ai_extracted_data = convert_decimals(extracted)  # type: ignore
            document.ai_model_used     = "llama-3.3-70b-versatile" # type: ignore

            document.status = ProcessingStatus.COMPLETED  # type: ignore
            document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
            document.processing_duration_seconds = time.time() - start_time # type: ignore

            await db.commit()
            logger.info(
                "Document %s processed in %.2fs",
                document_id,
                document.processing_duration_seconds,
            )

        except Exception as e:
            logger.error("Background task crashed for document %s: %s", document_id, e, exc_info=True)
            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = ProcessingStatus.FAILED # type: ignore
                    doc.processing_error = str(e)[:500] # type: ignore
                    doc.processing_completed_at = datetime.now(timezone.utc) # type: ignore
                    await db.commit()
            except Exception:
                pass

# ── IMPORTANT: static routes must come BEFORE /{document_id} ─────────────────
# If /statistics/summary or /upload are registered after /{document_id},
# FastAPI tries to parse "statistics" or "upload" as a UUID and returns 422.

# ── GET /documents/statistics/summary ────────────────────────────────────────

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
        avg_confidence = avg.scalar()

        avg_p = await db.execute(
            select(sqlfunc.avg(Document.processing_duration_seconds))
            .where(Document.business_id == bid, Document.processing_duration_seconds.isnot(None))
        )
        avg_processing_time = avg_p.scalar()

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
        logger.error("Failed to get document statistics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET /documents/ ───────────────────────────────────────────────────────────

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

        documents_result = await db.execute(
            query.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        documents = documents_result.scalars().all()

        return DocumentListResponse(
            documents=documents,  # type: ignore
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


# ── POST /documents/upload ────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(default="RECEIPT"),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a receipt/document for AI processing.

    The file is stored in Cloudinary immediately. OCR + Groq extraction
    runs in the background — poll GET /documents/{id} for status.

    Supported: PNG, JPG, PDF (max 10 MB).
    """
    business = await get_user_business(db, current_user.id) # type: ignore

    # ── Validate ──────────────────────────────────────────────────────────────
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PNG, JPG, PDF",
        )

    file_bytes = await file.read()
    file_size  = len(file_bytes)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {file_size / (1024*1024):.1f} MB (max 10 MB)",
        )

    # ── Upload to Cloudinary ──────────────────────────────────────────────────
    try:
        cloud_result         = upload_to_cloudinary(
            file_bytes,
            file.filename or "document",
            str(business.id),
            file.content_type
        ) # type: ignore
        cloudinary_url       = cloud_result["secure_url"]
        cloudinary_public_id = cloud_result["public_id"]
        logger.info("Uploaded to Cloudinary: %s", cloudinary_public_id)
    except Exception as e:
        logger.error("Cloudinary upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="File upload to Cloudinary failed")

    # ── Create DB record ──────────────────────────────────────────────────────
    try:
        document = Document(
            business_id=business.id,
            document_type=DocumentType(document_type),
            original_filename=file.filename or "unknown",
            file_path=cloudinary_url,          # Cloudinary HTTPS URL
            file_size=file_size,
            file_type=file.content_type,
            status=ProcessingStatus.PENDING,
            notes=notes,
            # Store public_id for deletion later — review_notes is a dedicated
            # text field; use it until a cloudinary_public_id column is added.
            review_notes=cloudinary_public_id,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        logger.info("Document record created: %s", document.id)

    except Exception as e:
        # Clean up Cloudinary asset if DB write fails
        try:
            cloudinary.uploader.destroy(cloudinary_public_id, resource_type="auto")
        except Exception:
            pass
        logger.error("DB write failed after Cloudinary upload: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create document record")

    # ── Queue background processing ───────────────────────────────────────────
    background_tasks.add_task(process_document_background, document.id,file_bytes,file.content_type,) # type: ignore
    logger.info("Queued background processing for document: %s", document.id)

    return DocumentUploadResponse(
        document_id=document.id, # type: ignore
        status=document.status,  # type: ignore
        message="Document uploaded. AI processing started in background.",
        estimated_completion_seconds=15,
    )


# ── GET /documents/{id} ───────────────────────────────────────────────────────

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore
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


# ── GET /documents/{id}/download ─────────────────────────────────────────────

@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return RedirectResponse(url=document.file_path, status_code=302)  # type: ignore

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to download document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── POST /documents/{id}/reprocess ───────────────────────────────────────────

@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore
        result = await db.execute(select(Document).where(
            Document.id == document_id,
            Document.business_id == business.id,
        ))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        document.status                      = ProcessingStatus.PENDING # type: ignore
        document.processing_error            = None  # type: ignore
        document.processing_completed_at     = None  # type: ignore
        document.processing_started_at       = None  # type: ignore
        document.processing_duration_seconds = None  # type: ignore
        document.ocr_raw_text                = None  # type: ignore
        await db.commit()

        background_tasks.add_task(process_document_background, document.id) # type: ignore
        logger.info("Requeued background processing for document: %s", document.id)

        return DocumentUploadResponse(  # type: ignore
            document_id=document.id,  # type: ignore
            status=document.status, # type: ignore
            message="Document requeued for AI processing.",
            estimated_completion_seconds=15,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to reprocess document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── PATCH /documents/{id} ────────────────────────────────────────────────────

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


# ── DELETE /documents/{id} ───────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
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

        # review_notes stores cloudinary_public_id (see upload endpoint comment)
        if document.review_notes: # type: ignore
            delete_from_cloudinary(document.review_notes, resource_type="auto") # type: ignore

        await db.delete(document)
        await db.commit()
        return None

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")








