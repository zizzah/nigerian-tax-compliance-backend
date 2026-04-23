"""
Document Processing API Endpoints - CLOUDINARY VERSION
Location: app/api/v1/endpoints/documents.py

Files are stored in Cloudinary (not local disk) so they persist
across Render deploys and work correctly in production.
"""
import math
import logging
import uuid
import time
import os
import urllib.request
import tempfile
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore
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
from app.services.qstash_client import qstash

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


def upload_to_cloudinary(file_bytes: bytes, filename: str, business_id: str) -> dict:
    """
    Upload file bytes to Cloudinary.

    Returns a dict with:
      - public_id   : Cloudinary asset identifier
      - secure_url  : HTTPS URL to access the file
      - resource_type
    """
    unique_name = f"taxflow/{business_id}/{uuid.uuid4()}"

    result = cloudinary.uploader.upload(
        file_bytes,
        public_id=unique_name,
        resource_type="auto",
        overwrite=False,
        access_mode="public",
        type="upload",
    )
    return result


def delete_from_cloudinary(public_id: str, resource_type: str = "image") -> None:
    """Delete a file from Cloudinary by public_id."""
    try:
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as e:
        logger.warning("Could not delete Cloudinary asset %s: %s", public_id, e)


def _ext_from_mimetype(mime: str) -> str:
    """Return a file extension string for a given MIME type."""
    mapping = {
        "image/png":       ".png",
        "image/jpeg":      ".jpg",
        "image/jpg":       ".jpg",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime, ".jpg")


async def process_document_sync(document: Document, db: AsyncSession) -> dict:
    """
    Process a document synchronously (development mode).
    Reads the file from Cloudinary URL via OCR, then runs Groq extraction.

    Returns a result dict on success or failure — never re-raises, so the
    caller's outer exception handler cannot roll back a committed FAILED status.
    """
    try:
        logger.info("Starting synchronous processing for document: %s", document.id)

        document.status = ProcessingStatus.PROCESSING  # type: ignore
        document.processing_started_at = datetime.now(timezone.utc)  # type: ignore
        await db.commit()

        start_time = time.time()

        cloudinary_url = document.file_path

        with tempfile.NamedTemporaryFile(delete=False, suffix=_ext_from_mimetype(document.file_type)) as tmp:  # type: ignore
            tmp_path = tmp.name

        try:
            req = urllib.request.Request(
                cloudinary_url,  # type: ignore
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(tmp_path, "wb") as f:
                    f.write(resp.read())

            # Step 1: Preprocess image
            logger.info("Step 1: Preprocessing image...")
            preprocessor = ImagePreprocessor()
            preprocessed_image = preprocessor.preprocess(tmp_path)

            # Step 2: OCR
            logger.info("Step 2: Running OCR...")
            ocr = OCRExtractor()
            ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)

            document.ocr_raw_text = ocr_text  # type: ignore
            document.ocr_confidence = ocr_confidence  # type: ignore
            await db.commit()

            if not ocr_text or len(ocr_text.strip()) < 10:
                raise ValueError("OCR extracted no meaningful text from image")

            # Step 3: Groq AI extraction
            logger.info("Step 3: AI extraction with Groq...")
            groq = GroqReceiptExtractor()
            extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # Step 4: Save extracted data
        logger.info("Step 4: Saving extracted data...")

        document.vendor_name    = extracted_data.get("vendor_name")  # type: ignore
        document.vendor_tin     = extracted_data.get("vendor_tin")  # type: ignore
        document.vendor_address = extracted_data.get("vendor_address")  # type: ignore
        document.vendor_phone   = extracted_data.get("vendor_phone")  # type: ignore
        document.document_number = extracted_data.get("document_number")  # type: ignore

        doc_date = extracted_data.get("document_date")
        if doc_date:
            if isinstance(doc_date, date):
                document.document_date = doc_date  # type: ignore
            elif isinstance(doc_date, str):
                try:
                    document.document_date = datetime.strptime(doc_date, "%Y-%m-%d").date()  # type: ignore
                except Exception:
                    document.document_date = None  # type: ignore
        else:
            document.document_date = None  # type: ignore

        document.line_items        = convert_decimals(extracted_data.get("line_items", []))  # type: ignore
        document.subtotal          = extracted_data.get("subtotal", 0)  # type: ignore
        document.vat_amount        = extracted_data.get("vat_amount", 0)  # type: ignore
        document.total_amount      = extracted_data.get("total_amount", 0)  # type: ignore
        document.vat_rate          = extracted_data.get("vat_rate", 7.5)  # type: ignore
        document.payment_method    = extracted_data.get("payment_method")  # type: ignore
        document.payment_reference = extracted_data.get("payment_reference")  # type: ignore

        if not extracted_data.get("category") and document.vendor_name:  # type: ignore
            try:
                line_items  = document.line_items or []
                description = line_items[0].get("description", "") if line_items else ""  # type: ignore
                document.category = groq.categorize_expense(description, document.vendor_name)  # type: ignore
            except Exception:
                document.category = "Other"  # type: ignore
        else:
            document.category = extracted_data.get("category", "Other")

        document.confidence_score  = extracted_data.get("confidence_score")  # type: ignore
        document.requires_review   = extracted_data.get("requires_review", False)
        document.ai_extracted_data = convert_decimals(extracted_data)  # type: ignore
        document.ai_model_used     = "llama-3.3-70b-versatile"  # type: ignore

        document.status = ProcessingStatus.COMPLETED  # type: ignore
        document.processing_completed_at = datetime.now(timezone.utc)  # type: ignore
        document.processing_duration_seconds = time.time() - start_time  # type: ignore

        await db.commit()

        logger.info(
            "Processed %s in %.2fs",
            document.original_filename,
            document.processing_duration_seconds,
        )

        return {
            "status":           "processed",
            "document_id":      str(document.id),
            "vendor_name":      document.vendor_name,
            "total_amount":     float(document.total_amount),
            "confidence_score": float(document.confidence_score) if document.confidence_score else None,  # type: ignore
            "processing_time":  float(document.processing_duration_seconds),  # type: ignore
        }

    except Exception as e:
        # Fix #4: commit the FAILED status here, then return a failure dict
        # instead of re-raising. Re-raising would let the caller's outer
        # except block roll back this commit, leaving the document stuck in
        # PROCESSING state permanently.
        logger.error("Synchronous processing failed: %s", e, exc_info=True)

        document.status = ProcessingStatus.FAILED  # type: ignore
        document.processing_error = str(e)[:500]  # type: ignore
        document.processing_completed_at = datetime.now(timezone.utc)  # type: ignore

        if document.processing_started_at:  # type: ignore
            document.processing_duration_seconds = (
                datetime.now(timezone.utc) - document.processing_started_at
            ).total_seconds()

        await db.commit()

        return {
            "status":      "failed",
            "document_id": str(document.id),
            "error":       str(e)[:500],
        }


# ── Upload endpoint ───────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="RECEIPT"),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload receipt/document for AI processing.

    Files are stored in Cloudinary — they persist across Render deploys.
    Processing: ~10-15 seconds with Groq AI.
    Supported: PNG, JPG, PDF (max 10 MB).
    """
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore

        # ── Validate MIME type ────────────────────────────────────────────────
        allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type: {file.content_type}. Allowed: PNG, JPG, PDF",
            )

        # ── Read & size-check ─────────────────────────────────────────────────
        file_bytes = await file.read()
        file_size  = len(file_bytes)

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {file_size / (1024*1024):.1f} MB (max 10 MB)",
            )

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        # ── Upload to Cloudinary ──────────────────────────────────────────────
        try:
            cloud_result = upload_to_cloudinary(
                file_bytes,
                filename=file.filename or "document",
                business_id=str(business.id),
            )
            cloudinary_url       = cloud_result["secure_url"]
            cloudinary_public_id = cloud_result["public_id"]
            logger.info("Uploaded to Cloudinary: %s", cloudinary_public_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Cloudinary upload failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File upload to Cloudinary failed",
            )

        # ── Create DB record ──────────────────────────────────────────────────
        try:
            document = Document(
                business_id=business.id,
                document_type=DocumentType(document_type),
                original_filename=file.filename or "unknown",
                file_path=cloudinary_url,
                file_size=file_size,
                file_type=file.content_type,
                status=ProcessingStatus.PENDING,
                notes=notes,
            )
            document.review_notes = cloudinary_public_id  # type: ignore

            db.add(document)
            await db.commit()
            await db.refresh(document)
            logger.info("Document record created: %s", document.id)

        except Exception as e:
            try:
                cloudinary.uploader.destroy(cloudinary_public_id, resource_type="auto")
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create document record",
            )

        # ── Process (sync dev / async prod) ──────────────────────────────────
        try:
            is_development = settings.ENVIRONMENT.lower() == "development"

            if is_development:
                logger.info("Development mode: processing synchronously...")
                # process_document_sync never re-raises — it returns a result dict.
                # Check the returned status to surface processing failures to the caller.
                result = await process_document_sync(document, db)
                if result["status"] == "failed":
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Document uploaded but processing failed: {result['error']}",
                    )
                return {
                    "document_id":                  document.id,
                    "status":                       document.status,
                    "message":                      "Document processed successfully",
                    "estimated_completion_seconds": 0,
                }

            else:
                logger.info("Production mode: queuing with QStash...")
                base_url = getattr(settings, "RENDER_EXTERNAL_URL", None)
                if not base_url:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="RENDER_EXTERNAL_URL not configured",
                    )

                callback_url = f"{base_url}/api/v1/background/process-document"
                response = qstash.publish(
                    url=callback_url,
                    body={"document_id": str(document.id), "business_id": str(business.id)},
                    delay=0,
                    retries=3,
                )
                task_id = response.get("messageId", "unknown")
                logger.info("Queued document %s, QStash message: %s", document.id, task_id)

                return {
                    "document_id":                  document.id,
                    "task_id":                      task_id,
                    "status":                       document.status,
                    "message":                      "Document uploaded. AI processing started.",
                    "estimated_completion_seconds": 15,
                }

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to queue/process document: %s", e, exc_info=True)
            document.status = ProcessingStatus.FAILED  # type: ignore
            document.processing_error = f"Failed to queue: {str(e)}"  # type: ignore
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document uploaded but processing failed: {str(e)}",
            )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to upload document: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET /documents/ ───────────────────────────────────────────────────────────

@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    document_type: Optional[DocumentType] = None,
    status: Optional[ProcessingStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore

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
            query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
        )
        documents = documents_result.scalars().all()

        return {
            "total":       total,
            "documents":   documents,
            "skip":        skip,
            "limit":       limit,
            "has_more":    skip + limit < total,
            "page":        (skip // limit) + 1 if limit > 0 else 1,
            "page_size":   len(documents),
            "total_page":  math.ceil(total / limit) if limit > 0 else 0,
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to list documents: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── GET /documents/statistics/summary ────────────────────────────────────────
# Fix #1: registered BEFORE /{document_id} so FastAPI does not swallow this
# path as a UUID parameter match (document_id = "statistics" → 422).

@router.get("/statistics/summary", response_model=DocumentStatistics)
async def get_document_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        business = await get_user_business(db, current_user.id)  # type: ignore
        bid = business.id

        status_result = await db.execute(
            select(Document.status, sqlfunc.count(Document.id))
            .where(Document.business_id == bid)
            .group_by(Document.status)
        )
        status_rows = status_result.all()
        by_status: dict = {
            (s.value if hasattr(s, "value") else str(s)): cnt
            for s, cnt in status_rows
        }

        total_documents    = sum(by_status.values())
        pending_processing = by_status.get("PENDING", 0) + by_status.get("PROCESSING", 0)
        completed          = by_status.get("COMPLETED", 0)
        failed             = by_status.get("FAILED", 0)

        req = await db.execute(
            select(sqlfunc.count(Document.id))
            .where(Document.business_id == bid, Document.requires_review == True)
        )
        requires_review = req.scalar_one_or_none()

        total = await db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(Document.total_amount), 0))
            .where(Document.business_id == bid, Document.status == ProcessingStatus.COMPLETED)
        )
        total_amount_processed = total.scalar_one_or_none() or Decimal("0")

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
        type_rows = types.all()
        by_type: dict = {
            (t.value if hasattr(t, "value") else str(t)): cnt
            for t, cnt in type_rows
        }

        cat = await db.execute(
            select(Document.category, sqlfunc.count(Document.id))
            .where(Document.business_id == bid, Document.category.isnot(None))
            .group_by(Document.category)
        )
        cat_rows = cat.all()
        by_category: dict = {(c or "Unknown"): cnt for c, cnt in cat_rows}

        return {
            "total_documents":          total_documents,
            "pending_processing":       pending_processing,
            "completed":                completed,
            "failed":                   failed,
            "requires_review":          requires_review,
            "total_amount_processed":   Decimal(str(total_amount_processed)),
            "average_confidence_score": float(avg_confidence) if avg_confidence else None,
            "average_processing_time":  float(avg_processing_time) if avg_processing_time else None,
            "by_type":                  by_type,
            "by_category":              by_category,
            "by_status":                by_status,
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to get document statistics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return document

    except HTTPException:
        await db.rollback()
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        return RedirectResponse(url=document.file_path, status_code=302)  # type: ignore

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to download document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── POST /documents/{id}/reprocess ───────────────────────────────────────────

@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        # Reset status
        document.status                      = ProcessingStatus.PENDING  # type: ignore
        document.processing_error            = None  # type: ignore
        document.processing_completed_at     = None  # type: ignore
        document.processing_started_at       = None  # type: ignore
        document.processing_duration_seconds = None  # type: ignore
        document.ocr_raw_text                = None  # type: ignore
        await db.commit()

        is_development = settings.ENVIRONMENT.lower() == "development"

        if is_development:
            proc_result  = await process_document_sync(document, db)
            if proc_result ["status"] == "failed":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Reprocessing failed: {proc_result ['error']}",
                )
            return {
                "document_id":                  document.id,
                "status":                       document.status,
                "message":                      "Document reprocessed successfully",
                "estimated_completion_seconds": 0,
            }
        else:
            base_url = getattr(settings, "RENDER_EXTERNAL_URL", None)
            if not base_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="RENDER_EXTERNAL_URL not configured",
                )
            callback_url = f"{base_url}/api/v1/background/process-document"
            response = qstash.publish(
                url=callback_url,
                body={"document_id": str(document.id), "business_id": str(business.id)},
                delay=0,
                retries=3,
            )
            return {
                "document_id":                  document.id,
                "task_id":                      response.get("messageId", "unknown"),
                "status":                       document.status,
                "message":                      "Document requeued for AI processing.",
                "estimated_completion_seconds": 15,
            }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to reprocess document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── PATCH /documents/{id} ─────────────────────────────────────────────────────

@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    update_data: DocumentUpdate,
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        # Fix #2: .dict() is deprecated in Pydantic v2 — use .model_dump()
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(document, field, value)

        await db.commit()
        await db.refresh(document)
        return document

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to update document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── DELETE /documents/{id} ────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        if document.review_notes:  # type: ignore
            delete_from_cloudinary(document.review_notes, resource_type="auto")  # type: ignore

        await db.delete(document)
        await db.commit()
        return None

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")