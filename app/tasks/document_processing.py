"""
Background Tasks for Document Processing
Location: app/tasks/document_processing.py

Powered by Groq AI for fast, efficient processing
"""
from celery import Task
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor
from datetime import datetime
import logging
import uuid
import time

logger = logging.getLogger(__name__)


class DocumentProcessingTask(Task):
    """Base task for document processing with error handling"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        document_id = args[0]
        db = SessionLocal()
        
        try:
            document = db.query(Document).filter(Document.id == uuid.UUID(document_id)).first()
            if document:
                document.status = ProcessingStatus.FAILED # type: ignore
                document.processing_error = str(exc)[:500]  # type: ignore # Limit error length
                document.processing_completed_at = datetime.utcnow() # type: ignore
                
                # Calculate processing duration
                if document.processing_started_at: # type: ignore
                    duration = (datetime.utcnow() - document.processing_started_at).total_seconds()
                    document.processing_duration_seconds = duration
                
                db.commit()
                logger.error(f"Document {document_id} processing failed: {exc}")
                
        except Exception as e:
            logger.error(f"Failed to update document status: {e}")
        finally:
            db.close()


@celery_app.task(base=DocumentProcessingTask, bind=True, max_retries=3)
def process_document(self, document_id: str):
    """
    Main document processing task
    
    Pipeline:
    1. Preprocess image (enhance quality)
    2. Run OCR (extract text with Tesseract)
    3. Use Groq AI (extract structured data)
    4. Save results to database
    5. Update document status
    
    Args:
        document_id: UUID of document to process
    """
    db = SessionLocal()
    
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == uuid.UUID(document_id)
        ).first()
        
        if not document:
            logger.error(f"Document not found: {document_id}")
            return {"error": "Document not found"}
        
        logger.info(f"Processing document: {document.original_filename}")
        
        # Update status
        document.status = ProcessingStatus.PROCESSING # type: ignore
        document.processing_started_at = datetime.utcnow() # type: ignore
        db.commit()
        
        start_time = time.time()
        
        # Step 1: Preprocess image
        logger.info("Step 1: Preprocessing image...")
        preprocessor = ImagePreprocessor()
        preprocessed_image = preprocessor.preprocess(document.file_path) # type: ignore
        
        # Step 2: Run OCR
        logger.info("Step 2: Running OCR...")
        ocr = OCRExtractor()
        ocr_text, ocr_confidence = ocr.extract_with_confidence(preprocessed_image)
        
        # Save OCR results
        document.ocr_raw_text = ocr_text # type: ignore
        document.ocr_confidence = ocr_confidence # type: ignore
        db.commit()
        
        logger.info(f"OCR confidence: {ocr_confidence:.2%}")
        logger.info(f"OCR text preview: {ocr_text[:200]}")
        
        # Step 3: AI Extraction with Groq
        logger.info("Step 3: AI extraction with Groq...")
        groq = GroqReceiptExtractor()
        extracted_data = groq.extract_receipt_data(ocr_text=ocr_text)
        
        # Step 4: Save extracted data to document
        logger.info("Step 4: Saving extracted data...")
        
        document.vendor_name = extracted_data.get('vendor_name') # type: ignore
        document.vendor_tin = extracted_data.get('vendor_tin') # type: ignore
        document.vendor_address = extracted_data.get('vendor_address') # type: ignore
        document.vendor_phone = extracted_data.get('vendor_phone') # type: ignore
        
        document.document_number = extracted_data.get('document_number') # type: ignore
        document.document_date = extracted_data.get('document_date') # type: ignore
        
        document.line_items = extracted_data.get('line_items', [])
        
        document.subtotal = extracted_data.get('subtotal', 0)
        document.vat_amount = extracted_data.get('vat_amount', 0)
        document.total_amount = extracted_data.get('total_amount', 0)
        document.vat_rate = extracted_data.get('vat_rate', 7.5)
        
        document.payment_method = extracted_data.get('payment_method') # type: ignore
        document.payment_reference = extracted_data.get('payment_reference') # type: ignore
        
        # Auto-categorize if category not provided
        if not extracted_data.get('category') and document.vendor_name: # type: ignore
            try:
                line_items = document.line_items or []
                description = line_items[0].get('description', '') if line_items else ''
                category = groq.categorize_expense(description, document.vendor_name) # type: ignore
                document.category = category # type: ignore
            except Exception as e:
                logger.warning(f"Auto-categorization failed: {e}")
                document.category = extracted_data.get('category', 'Other')
        else:
            document.category = extracted_data.get('category', 'Other')
        
        # Confidence and review flags
        document.confidence_score = extracted_data.get('confidence_score') # type: ignore
        document.requires_review = extracted_data.get('requires_review', False)
        
        # Save full AI response for debugging
        document.ai_extracted_data = extracted_data # type: ignore
        document.ai_model_used = "llama-3.3-70b-versatile" # type: ignore
        
        # Mark as completed
        document.status = ProcessingStatus.COMPLETED # type: ignore
        document.processing_completed_at = datetime.utcnow() # type: ignore
        
        # Calculate processing duration
        processing_duration = time.time() - start_time
        document.processing_duration_seconds = processing_duration # type: ignore
        
        db.commit()
        
        logger.info(f"✅ Successfully processed document: {document.original_filename}")
        logger.info(f"   Vendor: {document.vendor_name}")
        logger.info(f"   Total: ₦{float(document.total_amount):,.2f}")
        logger.info(f"   Confidence: {document.confidence_score}")
        logger.info(f"   Processing time: {processing_duration:.2f}s")
        
        return {
            "document_id": str(document.id),
            "status": "completed",
            "vendor_name": document.vendor_name,
            "total_amount": float(document.total_amount),
            "confidence_score": float(document.confidence_score), # type: ignore
            "processing_time": processing_duration
        }
        
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        
        # Update document with error
        if document:
            document.status = ProcessingStatus.FAILED # type: ignore
            document.processing_error = str(e)[:500] # type: ignore
            document.processing_completed_at = datetime.utcnow() # type: ignore
            
            if document.processing_started_at: # type: ignore
                duration = (datetime.utcnow() - document.processing_started_at).total_seconds()
                document.processing_duration_seconds = duration
            
            db.commit()
        
        # Retry task with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        
    finally:
        db.close()


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


@celery_app.task
def cleanup_old_documents(days: int = 90):
    """
    Cleanup old archived documents
    
    Args:
        days: Delete documents archived more than this many days ago
    """
    from datetime import timedelta
    
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Find old archived documents
        old_docs = db.query(Document).filter(
            Document.is_archived == True,
            Document.updated_at < cutoff_date
        ).all()
        
        count = len(old_docs)
        
        # Delete files and records
        for doc in old_docs:
            try:
                # Delete file
                from pathlib import Path
                file_path = Path(doc.file_path) # type: ignore
                if file_path.exists():
                    file_path.unlink()
                
                # Delete record
                db.delete(doc)
            except Exception as e:
                logger.error(f"Failed to delete document {doc.id}: {e}")
        
        db.commit()
        
        logger.info(f"Cleaned up {count} old documents")
        
        return {
            "deleted_count": count,
            "cutoff_date": str(cutoff_date)
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise
    finally:
        db.close()