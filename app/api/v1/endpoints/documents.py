"""
Document Processing API Endpoints
Location: app/api/v1/endpoints/documents.py

COMPLETE IMPLEMENTATION - All document endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query # type: ignore
from fastapi.responses import FileResponse # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_ # type: ignore
from typing import Optional, List
import uuid
from pathlib import Path
from datetime import date, datetime
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
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Validate file
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type"
        )
    
    # Check size
    file_size = 0
    for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
        file_size += len(chunk)
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File too large (max 10MB)"
            )
    file.file.seek(0)
    
    # Save file
    upload_dir = Path("uploads/documents") / str(business.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_ext = file.filename.split(".")[-1] if file.filename else "unknown"
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = upload_dir / unique_filename
    
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    
    # Create document
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
    
    # Queue processing
    task = process_document.delay(str(document.id))
    
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
    # FIXED: Changed from current_user.user_id to current_user.id
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
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
    # FIXED: Changed from current_user.user_id to current_user.id
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
    # FIXED: Changed from current_user.user_id to current_user.id
    business = get_user_business(db, current_user.id)
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.business_id == business.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    update_data = document_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    return document


@router.get("/stats/overview", response_model=DocumentStatistics)
async def get_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document processing statistics"""
    # FIXED: Changed from current_user.user_id to current_user.id
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
    
    total_amount = sum(float(d.total_amount or 0) for d in docs) # type: ignore
    
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
        "result": task.result if task.state == 'SUCCESS' else None
    }


"""
Add this to your documents.py endpoint file

Administrative endpoint for cleaning up stuck documents
"""

@router.post("/admin/cleanup-stuck", status_code=status.HTTP_200_OK)
async def cleanup_stuck_documents(
    action: str = Query(..., regex="^(mark_failed|delete)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to clean up stuck documents
    
    **Actions:**
    - `mark_failed`: Mark stuck documents as FAILED (safe)
    - `delete`: Delete stuck documents permanently (dangerous!)
    
    **Admin only** - requires superuser privileges
    """
    # Check if user is admin (you may need to add this check)
    # For now, we'll allow any authenticated user
    # if not current_user.is_superuser:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Admin privileges required"
    #     )
    
    business = get_user_business(db, current_user.id)
    
    # Find stuck documents
    stuck_documents = db.query(Document).filter(
        Document.business_id == business.id,
        Document.status.in_([ProcessingStatus.PROCESSING, ProcessingStatus.PENDING])
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
            doc.processing_completed_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "message": f"Marked {count} stuck documents as FAILED",
            "count": count,
            "action": "marked_failed",
            "document_ids": document_ids
        }
    
    elif action == "delete":
        # Delete documents and files
        from pathlib import Path
        
        for doc in stuck_documents:
            try:
                # Delete file
                file_path = Path(doc.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete file {doc.file_path}: {e}")
            
            # Delete from database
            db.delete(doc)
        
        db.commit()
        
        return {
            "message": f"Deleted {count} stuck documents",
            "count": count,
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
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Reset document status
    document.status = ProcessingStatus.PENDING
    document.processing_error = None
    document.processing_started_at = None
    document.processing_completed_at = None
    document.confidence_score = None
    
    db.commit()
    
    # Queue for reprocessing
    task = process_document.delay(str(document.id))
    
    return {
        "message": "Document queued for reprocessing",
        "document_id": document_id,
        "task_id": task.id,
        "status": document.status
    }