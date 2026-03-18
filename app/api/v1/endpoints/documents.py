"""
Document Processing API Endpoints - FIXED VERSION
Location: app/api/v1/endpoints/documents.py

CHANGES:
- Synchronous processing in development mode (no QStash needed)
- Async QStash processing in production
- Better error handling
- FIXED: JSON serialization for dates and decimals
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
from pathlib import Path
from datetime import datetime, timezone, date
import logging
import time
from decimal import Decimal

logger = logging.getLogger(__name__)

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
    DocumentStatistics
)
from app.services.qstash_client import qstash

router = APIRouter(prefix="/documents", tags=["Documents - AI Processing"])


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    return business


def convert_decimals(obj):
    """
    Recursively convert Decimal and date objects for JSON serialization
    
    FIXED: Now handles date objects properly
    """
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()  # Convert dates to ISO string
    return obj


def process_document_sync(document: Document, db: Session) -> dict:
    """
    Process document synchronously (for development mode)
    
    FIXED: Properly handles date conversion and JSON serialization
    
    Args:
        document: Document object to process
        db: Database session
        
    Returns:
        Processing result dictionary
    """
    from app.services.ocr.preprocessor import ImagePreprocessor
    from app.services.ocr.extractor import OCRExtractor
    from app.services.ai.groq_extractor import GroqReceiptExtractor
    
    try:
        logger.info(f"Starting synchronous processing for document: {document.id}")
        
        # Update status
        document.status = ProcessingStatus.PROCESSING  # type: ignore
        document.processing_started_at = datetime.now(timezone.utc) # type: ignore

        db.commit()
        
        start_time = time.time()
        
        # Step 1: Preprocess image
        logger.info("Step 1: Preprocessing image...")
        preprocessor = ImagePreprocessor()
        
        file_path = Path(document.file_path) # type: ignore
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {document.file_path}")
        
        preprocessed_image = preprocessor.preprocess(str(file_path))
        
        # Step 2: Run OCR
        logger.info("Step 2: Running OCR...")
        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)
        
        document.ocr_raw_text = ocr_text # type: ignore
        document.ocr_confidence = ocr_confidence  # type: ignore
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
        document.vendor_name = extracted_data.get('vendor_name') # type: ignore
        document.vendor_tin = extracted_data.get('vendor_tin') # type: ignore
        document.vendor_address = extracted_data.get('vendor_address') # type: ignore
        document.vendor_phone = extracted_data.get('vendor_phone') # type: ignore
        
        # Document information
        document.document_number = extracted_data.get('document_number') # type: ignore
        
        # ====================================================================
        # FIXED: Handle date conversion properly
        # ====================================================================
        doc_date = extracted_data.get('document_date')
        if doc_date:
            # If it's already a date object, use it
            if isinstance(doc_date, date):
                document.document_date = doc_date # type: ignore
            # If it's a string, parse it
            elif isinstance(doc_date, str):
                try:
                    document.document_date = datetime.strptime(doc_date, '%Y-%m-%d').date() # type: ignore
                except Exception as e:
                    logger.warning(f"Failed to parse date '{doc_date}': {e}")
                    document.document_date = None # type: ignore
            else:
                document.document_date = None # type: ignore
        else:
            document.document_date = None # type: ignore
        
        # Line items - convert decimals for JSON storage
        line_items_raw = extracted_data.get('line_items', [])
        document.line_items = convert_decimals(line_items_raw) # type: ignore
        
        # Financial data
        document.subtotal = extracted_data.get('subtotal', 0) # type: ignore
        document.vat_amount = extracted_data.get('vat_amount', 0) # type: ignore
        document.total_amount = extracted_data.get('total_amount', 0) # type: ignore
        document.vat_rate = extracted_data.get('vat_rate', 7.5) # type: ignore
        
        # Payment information
        document.payment_method = extracted_data.get('payment_method') # type: ignore
        document.payment_reference = extracted_data.get('payment_reference') # type: ignore
        
        # Auto-categorize
        if not extracted_data.get('category') and document.vendor_name: # type: ignore
            try:
                line_items = document.line_items or []
                description = line_items[0].get('description', '') if line_items else '' # type: ignore
                category = groq.categorize_expense(description, document.vendor_name) # type: ignore
                document.category = category # type: ignore
            except Exception as e:
                logger.warning(f"Auto-categorization failed: {e}")
                document.category = 'Other'  # type: ignore
        else:
            document.category = extracted_data.get('category', 'Other')
        
        # Confidence and review flags
        document.confidence_score = extracted_data.get('confidence_score') # type: ignore
        document.requires_review = extracted_data.get('requires_review', False)
        
        # ====================================================================
        # FIXED: Convert dates and decimals before saving to JSONB
        # ====================================================================
        document.ai_extracted_data = convert_decimals(extracted_data) # type: ignore
        document.ai_model_used = "llama-3.3-70b-versatile" # type: ignore
        
        # Mark as completed
        document.status = ProcessingStatus.COMPLETED  # type: ignore
        document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
        
        processing_duration = time.time() - start_time
        document.processing_duration_seconds = processing_duration # type: ignore
        
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
            "confidence_score": float(document.confidence_score) if document.confidence_score else None, # type: ignore
            "processing_time": processing_duration
        }
    
    except Exception as e:
        logger.error(f"Synchronous processing failed: {e}", exc_info=True)
        
        # Mark as failed
        document.status = ProcessingStatus.FAILED # type: ignore
        document.processing_error = str(e)[:500] # type: ignore
        document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
        
        if document.processing_started_at: # type: ignore
            duration = (
                datetime.now(timezone.utc) - document.processing_started_at
            ).total_seconds()
            document.processing_duration_seconds = duration
        
        db.commit()
        
        raise


# ============================================================================
# Document Upload Endpoint - FIXED VERSION
# ============================================================================

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="RECEIPT"),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload receipt/document for AI processing with Groq
    
    **FIXED VERSION:**
    - Development: Synchronous processing (no QStash needed)
    - Production: Async QStash processing
    - Proper JSON serialization for dates and decimals
    
    **File types:** PNG, JPG, PDF (max 10MB)
    **Processing:** ~10-15 seconds with Groq AI
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed: PNG, JPG, PDF"
        )
    
    # Check file size (Max 10MB)
    file_size = 0
    max_size = 10 * 1024 * 1024  # 10MB in bytes
    
    for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
        file_size += len(chunk)
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {file_size / (1024*1024):.1f}MB (max 10MB)"
            )
    
    file.file.seek(0)
    
    # Create upload directory
    upload_base = Path("uploads") / "documents"
    upload_dir = upload_base / str(business.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    if file.filename:
        file_ext = Path(file.filename).suffix or ".jpg"
    else:
        file_ext = ".jpg"
    
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = upload_dir / unique_filename
    
    # Save file to disk
    try:
        with open(file_path, "wb") as f:
            content = file.file.read()
            f.write(content)
        
        logger.info(f"File saved successfully: {file_path}")
        
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # Create document record
    try:
        document = Document(
            business_id=business.id,
            document_type=DocumentType(document_type),
            original_filename=file.filename or "unknown",
            file_path=str(file_path),
            file_size=file_size,
            file_type=file.content_type,
            status=ProcessingStatus.PENDING,
            notes=notes
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        logger.info(f"Document created: {document.id}")
        
    except Exception as e:
        logger.error(f"Failed to create document record: {e}")
        
        # Clean up file if database insert fails
        try:
            file_path.unlink()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document record"
        )
    
    # ========================================================================
    # PROCESSING: Synchronous (Dev) or Async (Production)
    # ========================================================================
    
    try:
        # Check environment
        is_development = settings.ENVIRONMENT.lower() == "development"
        
        if is_development:
            # ================================================================
            # DEVELOPMENT MODE: Process synchronously
            # ================================================================
            logger.info("🔧 Development mode: Processing synchronously...")
            
            try:
                result = process_document_sync(document, db)
                
                return {
                    "document_id": document.id,
                    "status": document.status,
                    "message": f"Document processed successfully (sync mode)",
                    "estimated_completion_seconds": 0,  # Already done
                    "processing_result": result
                }
                
            except Exception as e:
                # Document already marked as failed in process_document_sync
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Document processing failed: {str(e)}"
                )
        
        else:
            # ================================================================
            # PRODUCTION MODE: Queue with QStash
            # ================================================================
            logger.info("🚀 Production mode: Queuing for async processing...")
            
            # Get production URL
            base_url = getattr(settings, 'RENDER_EXTERNAL_URL', None)
            
            if not base_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="RENDER_EXTERNAL_URL not configured. Set it in your environment variables."
                )
            
            callback_url = f"{base_url}/api/v1/background/process-document"
            
            # Publish task to QStash
            response = qstash.publish(
                url=callback_url,
                body={
                    "document_id": str(document.id),
                    "business_id": str(business.id)
                },
                delay=0,  # Process immediately
                retries=3  # Retry up to 3 times on failure
            )
            
            task_id = response.get("messageId", "unknown")
            
            logger.info(f"Document queued for processing: {document.id}, QStash Message: {task_id}")
            
            return {
                "document_id": document.id,
                "task_id": task_id,
                "status": document.status,
                "message": "Document uploaded. AI processing started.",
                "estimated_completion_seconds": 15
            }
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except Exception as e:
        logger.error(f"Failed to queue/process document: {e}", exc_info=True)
        
        # Mark as failed
        document.status = ProcessingStatus.FAILED # type: ignore
        document.processing_error = f"Failed to queue for processing: {str(e)}" # type: ignore
        document.processing_completed_at = datetime.now(timezone.utc) # type: ignore
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document uploaded but processing failed: {str(e)}"
        )


# ============================================================================
# Document Retrieval Endpoints (NO CHANGES)
# ============================================================================

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document details by ID"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    document_type: Optional[DocumentType] = None,
    status: Optional[ProcessingStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all documents with optional filtering"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    query = db.query(Document).filter(Document.business_id == business.id)
    
    if document_type:
        query = query.filter(Document.document_type == document_type)
    
    if status:
        query = query.filter(Document.status == status)
    
    total = query.count()
    documents = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "documents": documents,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    update_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update document metadata (notes, type, etc.)"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document and its file"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Delete physical file
    try:
        file_path = Path(document.file_path) # type: ignore
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file {document.file_path}: {e}")
    
    # Delete database record
    db.delete(document)
    db.commit()
    
    return None


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download the original document file"""
    business = get_user_business(db, current_user.id) # type: ignore
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_path = Path(document.file_path) # type: ignore
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=document.original_filename, # type: ignore
        media_type=document.file_type # type: ignore
    )


@router.get("/statistics/summary", response_model=DocumentStatistics)
async def get_document_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document processing statistics"""
    from sqlalchemy import func as sqlfunc
    from decimal import Decimal as D
 
    business = get_user_business(db, current_user.id) # type: ignore
    bid = business.id
 
    # Counts by status
    status_rows = (
        db.query(Document.status, sqlfunc.count(Document.id))
        .filter(Document.business_id == bid)
        .group_by(Document.status)
        .all()
    )
    by_status: dict = {}
    for s, cnt in status_rows:
        key = s.value if hasattr(s, "value") else str(s)
        by_status[key] = cnt
 
    total_documents    = sum(by_status.values())
    pending_processing = by_status.get("PENDING", 0) + by_status.get("PROCESSING", 0)
    completed          = by_status.get("COMPLETED", 0)
    failed             = by_status.get("FAILED", 0)
 
    requires_review = (
        db.query(sqlfunc.count(Document.id))
        .filter(Document.business_id == bid, Document.requires_review == True)
        .scalar() or 0
    )
 
    total_amount_processed = (
        db.query(sqlfunc.coalesce(sqlfunc.sum(Document.total_amount), 0))
        .filter(Document.business_id == bid, Document.status == ProcessingStatus.COMPLETED)
        .scalar() or D("0")
    )
 
    avg_confidence = (
        db.query(sqlfunc.avg(Document.confidence_score))
        .filter(Document.business_id == bid, Document.confidence_score.isnot(None))
        .scalar()
    )
 
    avg_processing_time = (
        db.query(sqlfunc.avg(Document.processing_duration_seconds))
        .filter(Document.business_id == bid, Document.processing_duration_seconds.isnot(None))
        .scalar()
    )
 
    # Counts by document type
    type_rows = (
        db.query(Document.document_type, sqlfunc.count(Document.id))
        .filter(Document.business_id == bid)
        .group_by(Document.document_type)
        .all()
    )
    by_type: dict = {
        (t.value if hasattr(t, "value") else str(t)): cnt
        for t, cnt in type_rows
    }
 
    # Counts by category
    cat_rows = (
        db.query(Document.category, sqlfunc.count(Document.id))
        .filter(Document.business_id == bid, Document.category.isnot(None))
        .group_by(Document.category)
        .all()
    )
    by_category: dict = {(c or "Unknown"): cnt for c, cnt in cat_rows}
 
    return {
        "total_documents":        total_documents,
        "pending_processing":     pending_processing,
        "completed":              completed,
        "failed":                 failed,
        "requires_review":        requires_review,
        "total_amount_processed": D(str(total_amount_processed)),
        "average_confidence_score": float(avg_confidence) if avg_confidence else None,
        "average_processing_time":  float(avg_processing_time) if avg_processing_time else None,
        "by_type":     by_type,
        "by_category": by_category,
        "by_status":   by_status,
    }

@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reprocess a failed or completed document
    
    Respects development/production mode:
    - Development: Reprocesses synchronously
    - Production: Requeues with QStash
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Reset document status
    document.status = ProcessingStatus.PENDING # type: ignore
    document.processing_error = None # type: ignore
    document.processing_completed_at = None # type: ignore
    document.processing_started_at = None # type: ignore
    document.processing_duration_seconds = None # type: ignore

    db.commit()
    
    try:
        # Check environment
        is_development = settings.ENVIRONMENT.lower() == "development"
        
        if is_development:
            # Development: Process synchronously
            logger.info("🔧 Reprocessing synchronously (development mode)...")
            
            result = process_document_sync(document, db)
            
            return {
                "document_id": document.id,
                "status": document.status,
                "message": "Document reprocessed successfully (sync mode)",
                "estimated_completion_seconds": 0,
                "processing_result": result
            }
        
        else:
            # Production: Queue with QStash
            logger.info("🚀 Requeuing for async processing (production mode)...")
            
            base_url = getattr(settings, 'RENDER_EXTERNAL_URL', None)
            
            if not base_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="RENDER_EXTERNAL_URL not configured"
                )
            
            callback_url = f"{base_url}/api/v1/background/process-document"
            
            response = qstash.publish(
                url=callback_url,
                body={
                    "document_id": str(document.id),
                    "business_id": str(business.id)
                },
                delay=0,
                retries=3
            )
            
            task_id = response.get("messageId", "unknown")
            
            logger.info(f"Document requeued: {document.id}, QStash Message: {task_id}")
            
            return {
                "document_id": document.id,
                "task_id": task_id,
                "status": document.status,
                "message": "Document requeued for AI processing.",
                "estimated_completion_seconds": 15
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to reprocess document: {e}", exc_info=True)
        
        document.status = ProcessingStatus.FAILED # type: ignore
        document.processing_error = f"Reprocessing failed: {str(e)}"  # type: ignore

        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}"
        )