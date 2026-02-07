"""
Background Tasks for Document Processing
Location: app/tasks/document_processing.py

PRODUCTION VERSION - Includes:
- Automatic stuck document recovery
- Task timeouts (5 minutes)
- Enhanced error handling
- Cross-platform file paths
- Retry with exponential backoff

Powered by Groq AI for fast, efficient processing
"""
from celery import Task # type: ignore
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded # type: ignore
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import json
import logging
import uuid
import time

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def convert_decimals(obj):
    """Recursively convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj


# ============================================================================
# ENHANCED TASK CLASS WITH AUTOMATIC RECOVERY
# ============================================================================

class DocumentProcessingTask(Task):
    """
    Enhanced task class with automatic failure handling
    
    Features:
    - Automatic status updates on failure
    - Task timeout handling
    - Processing duration tracking
    - Detailed error logging
    """
    
    # Task timeout configuration
    time_limit = 300  # 5 minutes hard limit
    soft_time_limit = 270  # 4.5 minutes soft limit (warning)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Handle task failure - PRODUCTION VERSION
        
        Automatically marks document as FAILED when:
        - Task times out
        - Worker crashes
        - Processing raises exception
        """
        document_id = args[0] if args else None
        
        if not document_id:
            logger.error("Task failed but no document_id provided")
            return
        
        db = SessionLocal()
        
        try:
            document = db.query(Document).filter(
                Document.id == uuid.UUID(document_id)
            ).first()
            
            if document:
                # Determine failure reason
                if isinstance(exc, (SoftTimeLimitExceeded, TimeLimitExceeded)):
                    error_msg = "Processing timed out after 5 minutes"
                    logger.error(f"Document {document_id} timed out")
                else:
                    error_msg = str(exc)[:500]
                    logger.error(f"Document {document_id} failed: {exc}")
                
                # Update document status
                document.status = ProcessingStatus.FAILED
                document.processing_error = error_msg
                document.processing_completed_at = datetime.now(timezone.utc)
                
                # Calculate processing duration
                if document.processing_started_at:
                    duration = (
                        datetime.now(timezone.utc) - document.processing_started_at
                    ).total_seconds()
                    document.processing_duration_seconds = duration
                
                db.commit()
                
                logger.info(f"Document {document_id} marked as FAILED")
        
        except Exception as e:
            logger.error(f"Failed to update document status on failure: {e}")
        finally:
            db.close()
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        document_id = args[0] if args else None
        retry_count = self.request.retries
        logger.warning(
            f"Retrying document {document_id} (attempt {retry_count + 1}/3): {exc}"
        )


# ============================================================================
# MAIN DOCUMENT PROCESSING TASK
# ============================================================================

@celery_app.task(
    base=DocumentProcessingTask,
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True
)
def process_document(self, document_id: str):
    """
    Main document processing task - PRODUCTION VERSION
    
    Pipeline:
    1. Preprocess image (enhance quality)
    2. Run OCR (extract text with Tesseract)
    3. Use Groq AI (extract structured data)
    4. Save results to database
    5. Update document status
    
    Features:
    - 5-minute timeout (automatic failure)
    - Cross-platform file paths
    - Automatic retry with exponential backoff
    - Detailed error logging
    - Progress tracking
    
    Args:
        document_id: UUID of document to process
    """
    db = SessionLocal()
    document = None
    
    try:
        # ====================================================================
        # GET DOCUMENT
        # ====================================================================
        
        document = db.query(Document).filter(
            Document.id == uuid.UUID(document_id)
        ).first()
        
        if not document:
            logger.error(f"Document not found: {document_id}")
            raise ValueError(f"Document {document_id} not found")
        
        logger.info(f"Processing document: {document.original_filename}")
        
        # ====================================================================
        # UPDATE STATUS TO PROCESSING
        # ====================================================================
        
        document.status = ProcessingStatus.PROCESSING
        document.processing_started_at = datetime.now(timezone.utc)
        db.commit()
        
        start_time = time.time()
        
        # ====================================================================
        # STEP 1: PREPROCESS IMAGE
        # ====================================================================
        
        logger.info("Step 1: Preprocessing image...")
        preprocessor = ImagePreprocessor()
        
        # Check if file exists (cross-platform using pathlib)
        file_path = Path(document.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {document.file_path}")
        
        # Pass file path as string to preprocessor
        preprocessed_image = preprocessor.preprocess(str(file_path))
        
        # ====================================================================
        # STEP 2: RUN OCR
        # ====================================================================
        
        logger.info("Step 2: Running OCR...")
        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)
        
        # Save OCR results
        document.ocr_raw_text = ocr_text
        document.ocr_confidence = ocr_confidence
        db.commit()
        
        logger.info(f"OCR confidence: {ocr_confidence:.2%}")
        logger.info(f"OCR text preview: {ocr_text[:200]}")
        
        # Validate OCR extracted meaningful text
        if not ocr_text or len(ocr_text.strip()) < 10:
            raise ValueError("OCR extracted no meaningful text from image")
        
        # ====================================================================
        # STEP 3: AI EXTRACTION WITH GROQ
        # ====================================================================
        
        logger.info("Step 3: AI extraction with Groq...")
        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)
        
        # ====================================================================
        # STEP 4: SAVE EXTRACTED DATA TO DOCUMENT
        # ====================================================================
        
        logger.info("Step 4: Saving extracted data...")
        
        # Vendor information
        document.vendor_name = extracted_data.get('vendor_name')
        document.vendor_tin = extracted_data.get('vendor_tin')
        document.vendor_address = extracted_data.get('vendor_address')
        document.vendor_phone = extracted_data.get('vendor_phone')
        
        # Document information
        document.document_number = extracted_data.get('document_number')
        document.document_date = extracted_data.get('document_date')
        
        # Line items (convert Decimals to floats for JSONB)
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
        
        # Auto-categorize if not provided
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
        
        # Save full AI response for debugging (convert Decimals first)
        document.ai_extracted_data = convert_decimals(extracted_data)
        document.ai_model_used = "llama-3.3-70b-versatile"
        
        # ====================================================================
        # MARK AS COMPLETED
        # ====================================================================
        
        document.status = ProcessingStatus.COMPLETED
        document.processing_completed_at = datetime.now(timezone.utc)
        
        # Calculate processing duration
        processing_duration = time.time() - start_time
        document.processing_duration_seconds = processing_duration
        
        db.commit()
        
        # ====================================================================
        # SUCCESS LOGGING
        # ====================================================================
        
        logger.info(f"✅ Successfully processed: {document.original_filename}")
        logger.info(f"   Vendor: {document.vendor_name}")
        logger.info(f"   Total: ₦{float(document.total_amount):,.2f}")
        logger.info(f"   Confidence: {document.confidence_score}")
        logger.info(f"   Processing time: {processing_duration:.2f}s")
        
        return {
            "document_id": str(document.id),
            "status": "completed",
            "vendor_name": document.vendor_name,
            "total_amount": float(document.total_amount),
            "confidence_score": float(document.confidence_score) if document.confidence_score else None,
            "processing_time": processing_duration
        }
    
    except SoftTimeLimitExceeded:
        # Soft timeout (4.5 minutes) - task will be killed soon
        logger.error(f"Document {document_id} processing soft timeout (>4.5 min)")
        
        if document:
            document.status = ProcessingStatus.FAILED
            document.processing_error = "Processing took too long (>4.5 minutes)"
            document.processing_completed_at = datetime.now(timezone.utc)
            
            if document.processing_started_at:
                duration = (
                    datetime.now(timezone.utc) - document.processing_started_at
                ).total_seconds()
                document.processing_duration_seconds = duration
            
            db.commit()
        
        raise  # Re-raise to trigger on_failure handler
    
    except Exception as e:
        # Any other error
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
        
        # Retry with exponential backoff (60s, 120s, 240s)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    
    finally:
        db.close()


# ============================================================================
# AUTOMATIC STUCK DOCUMENT RECOVERY - CRITICAL FOR PRODUCTION
# ============================================================================

@celery_app.task
def recover_stuck_documents():
    """
    Automatically recover documents stuck in PROCESSING/PENDING
    
    Run this every 10 minutes via Celery Beat
    
    Recovery logic:
    - Documents in PROCESSING for >10 min → Mark as FAILED
    - Documents in PENDING for >10 min → Retry processing
    
    This prevents documents from being stuck forever when:
    - Worker crashes mid-processing
    - Redis connection lost
    - Task killed unexpectedly
    """
    db = SessionLocal()
    
    try:
        # Find documents stuck for more than 10 minutes
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        # Find stuck PROCESSING documents
        stuck_processing = db.query(Document).filter(
            Document.status == ProcessingStatus.PROCESSING,
            Document.processing_started_at < cutoff_time
        ).all()
        
        # Find stuck PENDING documents
        stuck_pending = db.query(Document).filter(
            Document.status == ProcessingStatus.PENDING,
            Document.created_at < cutoff_time
        ).all()
        
        recovered_count = 0
        retry_count = 0
        
        # Mark stuck PROCESSING documents as FAILED
        for doc in stuck_processing:
            logger.warning(f"Recovering stuck PROCESSING document: {doc.id}")
            doc.status = ProcessingStatus.FAILED
            doc.processing_error = "Worker crashed or timed out - recovered by monitoring task"
            doc.processing_completed_at = datetime.now(timezone.utc)
            
            # Calculate duration
            if doc.processing_started_at:
                duration = (
                    datetime.now(timezone.utc) - doc.processing_started_at
                ).total_seconds()
                doc.processing_duration_seconds = duration
            
            recovered_count += 1
        
        # Retry stuck PENDING documents (they never started processing)
        for doc in stuck_pending:
            logger.warning(f"Retrying stuck PENDING document: {doc.id}")
            try:
                # Verify file still exists before retrying
                file_path = Path(doc.file_path)
                if not file_path.exists():
                    logger.error(f"File missing for document {doc.id}, marking as FAILED")
                    doc.status = ProcessingStatus.FAILED
                    doc.processing_error = "File not found - cannot retry"
                    doc.processing_completed_at = datetime.now(timezone.utc)
                    recovered_count += 1
                    continue
                
                # Queue for reprocessing
                task = process_document.delay(str(doc.id))
                logger.info(f"Queued stuck document {doc.id} for retry: {task.id}")
                retry_count += 1
            
            except Exception as e:
                logger.error(f"Failed to retry document {doc.id}: {e}")
                doc.status = ProcessingStatus.FAILED
                doc.processing_error = f"Auto-retry failed: {str(e)[:200]}"
                doc.processing_completed_at = datetime.now(timezone.utc)
                recovered_count += 1
        
        db.commit()
        
        # Log summary
        if recovered_count > 0 or retry_count > 0:
            logger.info(
                f"Recovery complete: {recovered_count} marked as FAILED, "
                f"{retry_count} queued for retry"
            )
        
        return {
            "recovered_count": recovered_count,
            "retry_count": retry_count,
            "stuck_processing": len(stuck_processing),
            "stuck_pending": len(stuck_pending),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Stuck document recovery failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


# ============================================================================
# CLEANUP TASKS
# ============================================================================

@celery_app.task
def cleanup_old_results():
    """
    Clean up old Celery task results from Redis
    
    Run this every hour via Celery Beat to prevent Redis memory buildup
    """
    from celery.result import AsyncResult # type: ignore
    
    try:
        # This task just expires old results
        # Celery handles this automatically with result_expires setting
        # But we can add custom cleanup logic here if needed
        
        logger.info("Old results cleanup completed (handled by Celery)")
        
        return {
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise


@celery_app.task
def cleanup_old_documents(days: int = 90):
    """
    Cleanup old archived documents
    
    Args:
        days: Delete documents archived more than this many days ago
    """
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Find old archived documents
        old_docs = db.query(Document).filter(
            Document.is_archived == True,
            Document.updated_at < cutoff_date
        ).all()
        
        count = len(old_docs)
        deleted_files = 0
        
        # Delete files and records
        for doc in old_docs:
            try:
                # Delete file (cross-platform using pathlib)
                file_path = Path(doc.file_path)
                if file_path.exists():
                    file_path.unlink()
                    deleted_files += 1
                
                # Delete record
                db.delete(doc)
            except Exception as e:
                logger.error(f"Failed to delete document {doc.id}: {e}")
        
        db.commit()
        
        logger.info(
            f"Cleaned up {count} old documents "
            f"({deleted_files} files deleted)"
        )
        
        return {
            "deleted_count": count,
            "deleted_files": deleted_files,
            "cutoff_date": str(cutoff_date),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise
    finally:
        db.close()


# ============================================================================
# BATCH PROCESSING
# ============================================================================

@celery_app.task
def process_batch_documents(document_ids: list):
    """
    Process multiple documents in batch
    
    Useful for bulk upload scenarios
    
    Args:
        document_ids: List of document UUIDs to process
    """
    results = []
    
    for doc_id in document_ids:
        try:
            result = process_document.delay(doc_id)
            results.append({
                "document_id": doc_id,
                "task_id": result.id,
                "status": "queued"
            })
        except Exception as e:
            logger.error(f"Failed to queue document {doc_id}: {e}")
            results.append({
                "document_id": doc_id,
                "error": str(e),
                "status": "failed_to_queue"
            })
    
    return results


# ============================================================================
# HEALTH CHECK
# ============================================================================

@celery_app.task
def health_check():
    """
    Health check task for monitoring
    
    Tests:
    - Celery worker is running
    - Can access database
    - Can process tasks
    """
    db = SessionLocal()
    
    try:
        # Test database connection
        from sqlalchemy import text # type: ignore
        db.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "connected"
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    finally:
        db.close()