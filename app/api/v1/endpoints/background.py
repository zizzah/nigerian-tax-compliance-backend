"""
Background Task Endpoint (QStash Callback)
Location: app/api/v1/endpoints/background.py
"""
from fastapi import APIRouter, Request, HTTPException, Depends # type: ignore
from upstash_qstash import verify_signature # type: ignore
from sqlalchemy.orm import Session # type: ignore
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document, ProcessingStatus
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import logging
import uuid
import time

router = APIRouter(prefix="/background", tags=["Background"])
logger = logging.getLogger(__name__)


def convert_decimals(obj):
    """Recursively convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj


@router.post("/process-document")
async def process_document(request: Request, db: Session = Depends(get_db)):
    """
    QStash callback endpoint for document processing
    
    This endpoint is called by QStash to process documents in the background
    """
    # ====================================================================
    # VERIFY REQUEST IS FROM QSTASH (SECURITY)
    # ====================================================================
    
    body = await request.body()
    signature = request.headers.get("Upstash-Signature")
    
    is_valid = verify_signature(
        body=body,
        signature=signature,
        current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
        next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
    )
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid QStash signature")
    
    # ====================================================================
    # GET PAYLOAD
    # ====================================================================
    
    payload = await request.json()
    document_id = payload.get("document_id")
    
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    
    logger.info(f"Processing document: {document_id}")
    
    # ====================================================================
    # PROCESS DOCUMENT
    # ====================================================================
    
    document = None
    
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == uuid.UUID(document_id)
        ).first()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Update status to PROCESSING
        document.status = ProcessingStatus.PROCESSING
        document.processing_started_at = datetime.now(timezone.utc)
        db.commit()
        
        start_time = time.time()
        
        # Step 1: Preprocess image
        logger.info("Step 1: Preprocessing image...")
        preprocessor = ImagePreprocessor()
        
        file_path = Path(document.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {document.file_path}")
        
        preprocessed_image = preprocessor.preprocess(str(file_path))
        
        # Step 2: Run OCR
        logger.info("Step 2: Running OCR...")
        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)
        
        document.ocr_raw_text = ocr_text
        document.ocr_confidence = ocr_confidence
        db.commit()
        
        logger.info(f"OCR confidence: {ocr_confidence:.2%}")
        
        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text from image")
        
        # Step 3: AI extraction with Groq
        logger.info("Step 3: AI extraction with Groq...")
        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)
        
        # Step 4: Save extracted data
        logger.info("Step 4: Saving extracted data...")
        
        # Vendor information
        document.vendor_name = extracted_data.get('vendor_name')
        document.vendor_tin = extracted_data.get('vendor_tin')
        document.vendor_address = extracted_data.get('vendor_address')
        document.vendor_phone = extracted_data.get('vendor_phone')
        
        # Document information
        document.document_number = extracted_data.get('document_number')
        document.document_date = extracted_data.get('document_date')
        
        # Line items
        line_items_raw = extracted_data.get('line_items', [])
        document.line_items = convert_decimals(line_items_raw)
        
        # Financial data
        document.subtotal = extracted_data.get('subtotal', 0)
        document.vat_amount = extracted_data.get('vat_amount', 0)
        document.total_amount = extracted_data.get('total_amount', 0)
        document.vat_rate = extracted_data.get('vat_rate', 7.5)
        
        # Payment information
        document.payment_method = extracted_data.get('payment_method')
        document.payment_reference = extracted_data.get('payment_reference')
        
        # Auto-categorize
        if not extracted_data.get('category') and document.vendor_name:
            try:
                line_items = document.line_items or []
                description = line_items[0].get('description', '') if line_items else '' # type: ignore
                category = groq.categorize_expense(description, document.vendor_name) # type: ignore
                document.category = category
            except Exception as e:
                logger.warning(f"Auto-categorization failed: {e}")
                document.category = 'Other'
        else:
            document.category = extracted_data.get('category', 'Other')
        
        # Confidence and review flags
        document.confidence_score = extracted_data.get('confidence_score')
        document.requires_review = extracted_data.get('requires_review', False)
        
        # Save full AI response
        document.ai_extracted_data = convert_decimals(extracted_data)
        document.ai_model_used = "llama-3.3-70b-versatile"
        
        # Mark as completed
        document.status = ProcessingStatus.COMPLETED
        document.processing_completed_at = datetime.now(timezone.utc)
        
        processing_duration = time.time() - start_time
        document.processing_duration_seconds = processing_duration
        
        db.commit()
        
        logger.info(f"✅ Successfully processed: {document.original_filename}")
        logger.info(f"   Vendor: {document.vendor_name}")
        logger.info(f"   Total: ₦{float(document.total_amount):,.2f}")
        logger.info(f"   Processing time: {processing_duration:.2f}s")
        
        return {
            "status": "processed",
            "document_id": str(document.id),
            "vendor_name": document.vendor_name,
            "total_amount": float(document.total_amount),
            "confidence_score": float(document.confidence_score) if document.confidence_score else None,
            "processing_time": processing_duration
        }
    
    except Exception as e:
        logger.error(f"Document processing failed: {e}", exc_info=True)
        
        if document:
            document.status = ProcessingStatus.FAILED
            document.processing_error = str(e)[:500]
            document.processing_completed_at = datetime.now(timezone.utc)
            
            if document.processing_started_at:
                duration = (
                    datetime.now(timezone.utc) - document.processing_started_at
                ).total_seconds()
                document.processing_duration_seconds = duration
            
            db.commit()
        
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )