"""
Document Processing API Endpoints
Location: app/api/v1/endpoints/documents.py

PRODUCTION VERSION - Fixed cross-platform file paths per deployment guide
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query # type: ignore
from fastapi.responses import FileResponse # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_ # type: ignore
from typing import Optional, List
import uuid
from pathlib import Path
from datetime import date, datetime, timezone
import math
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.dependencies import get_current_user
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
from app.tasks.document_processing import process_document

router = APIRouter(prefix="/documents", tags=["Documents - AI Processing"])


def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    return business


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
    
    **File types:** PNG, JPG, PDF (max 10MB)
    **Processing:** ~10-15 seconds with Groq AI
    
    FIXED: Cross-platform file paths using pathlib.Path
    """
    business = get_user_business(db, current_user.id)
    
    # ========================================================================
    # VALIDATE FILE TYPE
    # ========================================================================
    
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed: PNG, JPG, PDF"
        )
    
    # ========================================================================
    # CHECK FILE SIZE (Max 10MB)
    # ========================================================================
    
    file_size = 0
    max_size = 10 * 1024 * 1024  # 10MB in bytes
    
    for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
        file_size += len(chunk)
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {file_size / (1024*1024):.1f}MB (max 10MB)"
            )
    
    # Reset file pointer to beginning
    file.file.seek(0)
    
    # ========================================================================
    # CROSS-PLATFORM FILE PATH HANDLING - CRITICAL FIX
    # ========================================================================
    
    # Use pathlib for cross-platform paths (works on Windows, Linux, macOS)
    upload_base = Path("uploads") / "documents"
    upload_dir = upload_base / str(business.id)
    
    # Create directory (works on Windows and Linux)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename with proper extension
    if file.filename:
        file_ext = Path(file.filename).suffix or ".jpg"
    else:
        # Default to .jpg if no filename provided
        file_ext = ".jpg"
    
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = upload_dir / unique_filename
    
    # ========================================================================
    # SAVE FILE TO DISK
    # ========================================================================
    
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
    
    # ========================================================================
    # CREATE DOCUMENT RECORD
    # ========================================================================
    
    try:
        document = Document(
            business_id=business.id,
            document_type=DocumentType(document_type),
            original_filename=file.filename or "unknown",
            file_path=str(file_path),  # Store as string in database
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
    # QUEUE FOR AI PROCESSING
    # ========================================================================
    
    try:
        task = process_document.delay(str(document.id))
        logger.info(f"Document queued for processing: {document.id}, Task: {task.id}")
        
    except Exception as e:
        logger.error(f"Failed to queue document for processing: {e}")
        # Document is saved, but processing failed to queue
        # Mark as failed so user knows
        document.status = ProcessingStatus.FAILED
        document.processing_error = "Failed to queue for processing"
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document uploaded but failed to queue for processing"
        )
    
    return {
        "document_id": document.id,
        "task_id": task.id,
        "status": document.status,
        "message": "Document uploaded. AI processing started.",
        "estimated_completion_seconds": 15
    }


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document with extracted data"""
    business = get_user_business(db, current_user.id)
    
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[ProcessingStatus] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List documents with pagination"""
    business = get_user_business(db, current_user.id)
    
    query = db.query(Document).filter(
        Document.business_id == business.id,
        Document.is_archived == False
    )
    
    if status:
        query = query.filter(Document.status == status)
    
    total = query.count()
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
    documents = query.order_by(Document.created_at.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    return {
        "documents": documents,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    document_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update document (for corrections)"""
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    update_data = document_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    logger.info(f"Document updated: {document_id}")
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete document and its file
    
    FIXED: Cross-platform file deletion using pathlib
    """
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Delete file using pathlib (cross-platform)
    try:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"File deleted: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file {document.file_path}: {e}")
        # Continue with database deletion even if file deletion fails
    
    # Delete from database
    db.delete(document)
    db.commit()
    
    logger.info(f"Document deleted: {document_id}")


@router.get("/download/{document_id}")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download original document file
    
    FIXED: Cross-platform file path handling
    """
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Use pathlib to check file existence (cross-platform)
    file_path = Path(document.file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on disk"
        )
    
    # Return file for download
    return FileResponse(
        path=str(file_path),  # Convert Path to string for FileResponse
        filename=document.original_filename,
        media_type=document.file_type
    )


@router.get("/stats/overview", response_model=DocumentStatistics)
async def get_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document processing statistics"""
    business = get_user_business(db, current_user.id)
    
    docs = db.query(Document).filter(
        Document.business_id == business.id,
        Document.is_archived == False
    ).all()
    
    total = len(docs)
    completed = len([d for d in docs if d.status.value == ProcessingStatus.COMPLETED.value])
    failed = len([d for d in docs if d.status.value == ProcessingStatus.FAILED.value])
    pending = total - completed - failed
    requires_review = len([d for d in docs if d.requires_review is True])
    
    total_amount = sum(float(d.total_amount or 0) for d in docs)
    
    return {
        "total_documents": total,
        "pending_processing": pending,
        "completed": completed,
        "failed": failed,
        "requires_review": requires_review,
        "total_amount_processed": total_amount,
        "average_confidence_score": None,
        "average_processing_time": None,
        "by_type": {},
        "by_category": {},
        "by_status": {}
    }


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Check processing task status"""
    from celery.result import AsyncResult # type: ignore
    from app.celery_app import celery_app
    
    task = AsyncResult(task_id, app=celery_app)
    
    return {
        "task_id": task_id,
        "status": task.state.lower(),
        "result": task.result if task.state == 'SUCCESS' else None,
        "error": str(task.info) if task.state == 'FAILURE' else None
    }


# ============================================================================
# ADMIN ENDPOINTS - Document Recovery and Maintenance
# ============================================================================

@router.post("/admin/cleanup-stuck", status_code=status.HTTP_200_OK)
async def cleanup_stuck_documents(
    action: str = Query(..., pattern="^(mark_failed|delete)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to clean up stuck documents
    
    **Actions:**
    - `mark_failed`: Mark stuck documents as FAILED (safe)
    - `delete`: Delete stuck documents permanently (dangerous!)
    
    **Stuck documents** are those in PROCESSING/PENDING status for >10 minutes
    
    **Admin only** - requires superuser privileges
    """
    # TODO: Uncomment when is_superuser field is available
    # if not current_user.is_superuser:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Admin privileges required"
    #     )
    
    business = get_user_business(db, current_user.id)
    
    # Find stuck documents (processing for >10 minutes)
    from datetime import timedelta
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    
    stuck_documents = db.query(Document).filter(
        Document.business_id == business.id,
        Document.status.in_([ProcessingStatus.PROCESSING, ProcessingStatus.PENDING]),
        Document.created_at < cutoff_time
    ).all()
    
    if not stuck_documents:
        return {
            "message": "No stuck documents found",
            "count": 0
        }
    
    count = len(stuck_documents)
    document_ids = [str(doc.id) for doc in stuck_documents]
    
    if action == "mark_failed":
        # Mark as failed
        for doc in stuck_documents:
            doc.status = ProcessingStatus.FAILED
            doc.processing_error = "Marked as failed - worker crashed during processing"
            doc.processing_completed_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.warning(f"Marked {count} stuck documents as FAILED")
        
        return {
            "message": f"Marked {count} stuck documents as FAILED",
            "count": count,
            "action": "marked_failed",
            "document_ids": document_ids
        }
    
    elif action == "delete":
        # Delete documents and files (DANGEROUS!)
        deleted_files = 0
        
        for doc in stuck_documents:
            try:
                # Delete file using pathlib (cross-platform)
                file_path = Path(doc.file_path)
                if file_path.exists():
                    file_path.unlink()
                    deleted_files += 1
            except Exception as e:
                logger.error(f"Failed to delete file {doc.file_path}: {e}")
            
            # Delete from database
            db.delete(doc)
        
        db.commit()
        
        logger.warning(f"Deleted {count} stuck documents ({deleted_files} files)")
        
        return {
            "message": f"Deleted {count} stuck documents",
            "count": count,
            "deleted_files": deleted_files,
            "action": "deleted",
            "document_ids": document_ids
        }


@router.post("/admin/reprocess/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reprocess a failed or stuck document
    
    Useful for documents that failed due to temporary errors
    """
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Verify file still exists (cross-platform check)
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on disk. Cannot reprocess."
        )
    
    # Reset document status
    document.status = ProcessingStatus.PENDING
    document.processing_error = None
    document.processing_started_at = None
    document.processing_completed_at = None
    document.confidence_score = None
    
    db.commit()
    
    # Queue for reprocessing
    task = process_document.delay(str(document.id))
    
    logger.info(f"Document queued for reprocessing: {document_id}")
    
    return {
        "message": "Document queued for reprocessing",
        "document_id": document_id,
        "task_id": task.id,
        "status": document.status
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def documents_health():
    """Health check for documents endpoints"""
    # Check uploads directory exists
    upload_dir = Path("uploads") / "documents"
    
    return {
        "status": "healthy",
        "service": "documents",
        "upload_dir_exists": upload_dir.exists(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }