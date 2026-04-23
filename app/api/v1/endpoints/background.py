"""
Background Task Endpoint (QStash Callback)
Location: app/api/v1/endpoints/background.py

Downloads the file from Cloudinary URL, runs OCR + Groq extraction,
saves results back to the document record.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
from sqlalchemy import select
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document, ProcessingStatus
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor
from datetime import datetime, timezone, date
from decimal import Decimal
import logging
import uuid
import time
import tempfile
import os
import urllib.request

router = APIRouter(prefix="/background", tags=["Background"])
logger = logging.getLogger(__name__)


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


def _ext_from_mimetype(mime: str) -> str:
    mapping = {
        "image/png":       ".png",
        "image/jpeg":      ".jpg",
        "image/jpg":       ".jpg",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime or "", ".jpg")


def verify_qstash_signature(request: Request, body: bytes) -> bool:
    try:
        from qstash import Receiver
        receiver = Receiver(
            current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
            next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
        )
        signature = request.headers.get("Upstash-Signature")
        if not signature:
            logger.error("No Upstash-Signature header found")
            return False
        receiver.verify(signature=signature, body=body.decode("utf-8"))
        return True
    except Exception as e:
        logger.error(f"QStash signature verification failed: {e}")
        return False


@router.post("/process-document")
async def process_document(request: Request, db: AsyncSession = Depends(get_db)):
    """
    QStash callback: download file from Cloudinary, run OCR + Groq, save results.
    """
    body = await request.body()

    if not verify_qstash_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid QStash signature")

    payload      = await request.json()
    document_id  = payload.get("document_id")

    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")

    logger.info("Processing document: %s", document_id)

    document = None
    tmp_path = None

    try:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        document = result.scalars().first()

        if not document:
            raise ValueError(f"Document {document_id} not found")

        document.status = ProcessingStatus.PROCESSING # type: ignore
        document.processing_started_at = datetime.now(timezone.utc) # type: ignore
        await db.commit()

        start_time = time.time()

        # ── Download from Cloudinary ──────────────────────────────────────────
        # document.file_path is the Cloudinary secure URL
        cloudinary_url = document.file_path
        logger.info("Downloading from Cloudinary: %s", cloudinary_url)

        ext = _ext_from_mimetype(document.file_type) # type: ignore
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name

        req = urllib.request.Request(
            cloudinary_url, # type: ignore
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(tmp_path, "wb") as f:
                f.write(resp.read())

        # ── Step 1: Preprocess ────────────────────────────────────────────────
        logger.info("Step 1: Preprocessing image...")
        preprocessor = ImagePreprocessor()
        preprocessed_image = preprocessor.preprocess(tmp_path)

        # ── Step 2: OCR ───────────────────────────────────────────────────────
        logger.info("Step 2: Running OCR...")
        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)

        document.ocr_raw_text  = ocr_text # type: ignore
        document.ocr_confidence = ocr_confidence # type: ignore
        await db.commit()

        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text")

        # ── Step 3: Groq AI extraction ────────────────────────────────────────
        logger.info("Step 3: AI extraction with Groq...")
        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)

        # ── Step 4: Save results ──────────────────────────────────────────────
        document.vendor_name     = extracted_data.get("vendor_name") # type: ignore
        document.vendor_tin      = extracted_data.get("vendor_tin") # type: ignore
        document.vendor_address  = extracted_data.get("vendor_address") # type: ignore
        document.vendor_phone    = extracted_data.get("vendor_phone") # type: ignore
        document.document_number = extracted_data.get("document_number") # type: ignore

        doc_date = extracted_data.get("document_date")
        if doc_date:
            if isinstance(doc_date, date):
                document.document_date = doc_date # type: ignore
            elif isinstance(doc_date, str):
                try:
                    document.document_date = datetime.strptime(doc_date, "%Y-%m-%d").date() # type: ignore
                except Exception:
                    document.document_date = None # type: ignore
        else:
            document.document_date = None # type: ignore

        document.line_items        = convert_decimals(extracted_data.get("line_items", [])) # type: ignore
        document.subtotal          = extracted_data.get("subtotal", 0) # type: ignore
        document.vat_amount        = extracted_data.get("vat_amount", 0) # type: ignore
        document.total_amount      = extracted_data.get("total_amount", 0) # type: ignore
        document.vat_rate          = extracted_data.get("vat_rate", 7.5) # type: ignore
        document.payment_method    = extracted_data.get("payment_method") # type: ignore
        document.payment_reference = extracted_data.get("payment_reference") # type: ignore

        if not extracted_data.get("category") and document.vendor_name: # type: ignore
            try:
                items       = document.line_items or []
                description = items[0].get("description", "") if items else "" # type: ignore
                document.category = groq.categorize_expense(description, document.vendor_name) # type: ignore
            except Exception:
                document.category = "Other" # type: ignore
        else:
            document.category = extracted_data.get("category", "Other")

        document.confidence_score  = extracted_data.get("confidence_score") # type: ignore
        document.requires_review   = extracted_data.get("requires_review", False)
        document.ai_extracted_data = convert_decimals(extracted_data) # type: ignore
        document.ai_model_used     = "llama-3.3-70b-versatile" # type: ignore

        processing_duration = time.time() - start_time
        document.status = ProcessingStatus.COMPLETED # type: ignore
        document.processing_completed_at    = datetime.now(timezone.utc) # type: ignore
        document.processing_duration_seconds = processing_duration # type: ignore

        await db.commit()

        logger.info(
            "Processed: %s | Vendor: %s | Total: NGN %.2f | Time: %.2fs",
            document.original_filename,
            document.vendor_name,
            float(document.total_amount),
            processing_duration
        )

        return {
            "status":           "processed",
            "document_id":      str(document.id),
            "vendor_name":      document.vendor_name,
            "total_amount":     float(document.total_amount),
            "confidence_score": float(document.confidence_score) if document.confidence_score else None, # type: ignore
            "processing_time":  processing_duration,
        }
    
    except HTTPException:
        raise
        

    except Exception as e:
        logger.error("Document processing failed: %s", e, exc_info=True)

        if document:
            document.status = ProcessingStatus.FAILED # type: ignore
            document.processing_error = str(e)[:500] # type: ignore
            document.processing_completed_at = datetime.now(timezone.utc) # type: ignore

            if document.processing_started_at: # type: ignore
                document.processing_duration_seconds = (
                    datetime.now(timezone.utc) - document.processing_started_at
                ).total_seconds()

            await db.commit()

        raise HTTPException(status_code=500, detail="Document processing failed")

    finally:
        # Always clean up the temp file
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass