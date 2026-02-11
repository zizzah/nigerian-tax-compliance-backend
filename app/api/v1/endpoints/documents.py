"""
Document Processing API Endpoints - QStash Version
Location: app/api/v1/endpoints/documents.py

UPDATED: Uses QStash instead of Celery for background processing
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query # type: ignore
from fastapi.responses import FileResponse # type: ignore
from sqlalchemy.orm import Session # type: ignore
from typing import Optional, List
import uuid
from pathlib import Path
from datetime import datetime, timezone
import logging

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
    
    **UPDATED: Uses QStash for serverless background processing**
    
    **File types:** PNG, JPG, PDF (max 10MB)
    **Processing:** ~10-15 seconds with Groq AI
    """
    business = get_user_business(db, current_user.id)
    
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
    
    # ====================================================================
    # QUEUE FOR AI PROCESSING WITH QSTASH (REPLACES CELERY)
    # ====================================================================
    
    try:
        # Get your Render service URL from environment variable
        base_url = getattr(settings, 'RENDER_EXTERNAL_URL', "https://your-app.onrender.com")
        
        callback_url = f"{base_url}/api/v1/background/process-document"
        
        # Publish task to QStash
        response = qstash.publish(
            url=callback_url,
            body={
                "document_id": str(document.id),
                "business_id": str(business.id)
            },
            delay=0,  # Process immediately (or set delay in seconds)
            retries=3  # Retry up to 3 times on failure
        )
        
        task_id = response.get("messageId", "unknown")
        
        logger.info(f"Document queued for processing: {document.id}, QStash Message: {task_id}")
        
    except Exception as e:
        logger.error(f"Failed to queue document for processing: {e}")
        
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
        "task_id": task_id,
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
    """Get document details by ID"""
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
    document_type: Optional[DocumentType] = None,
    status: Optional[ProcessingStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all documents with optional filtering"""
    business = get_user_business(db, current_user.id)
    
    query = db.query(Document).filter(Document.business_id == business.id)
    
    if document_type:
        query = query.filter(Document.document_type == document_type)
    
    if status:
        query = query.filter(Document.status == status)
    
    total = query.count()
    documents = query.order_by(Document.uploaded_at.desc()).offset(skip).limit(limit).all()
    
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
    
    # Delete physical file
    try:
        file_path = Path(document.file_path)
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
    
    file_path = Path(document.file_path)
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=document.original_filename,
        media_type=document.file_type
    )


@router.get("/statistics/summary", response_model=DocumentStatistics)
async def get_document_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document processing statistics"""
    business = get_user_business(db, current_user.id)
    
    total_documents = db.query(Document).filter(Document.business_id == business.id).count()
    
    processed = db.query(Document).filter(
        Document.business_id == business.id,
        Document.status == ProcessingStatus.COMPLETED
    ).count()
    
    pending = db.query(Document).filter(
        Document.business_id == business.id,
        Document.status == ProcessingStatus.PENDING
    ).count()
    
    failed = db.query(Document).filter(
        Document.business_id == business.id,
        Document.status == ProcessingStatus.FAILED
    ).count()
    
    return {
        "total_documents": total_documents,
        "processed": processed,
        "pending": pending,
        "failed": failed
    }


@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reprocess a failed or completed document"""
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
    
    # Reset document status
    document.status = ProcessingStatus.PENDING
    document.processing_error = None
    document.processed_at = None
    db.commit()
    
    # Queue for processing with QStash
    try:
        base_url = getattr(settings, 'RENDER_EXTERNAL_URL', "https://your-app.onrender.com")
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
        
        logger.info(f"Document requeued for processing: {document.id}, QStash Message: {task_id}")
        
    except Exception as e:
        logger.error(f"Failed to requeue document: {e}")
        
        document.status = ProcessingStatus.FAILED
        document.processing_error = "Failed to queue for reprocessing"
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue document for reprocessing"
        )
    
    return {
        "document_id": document.id,
        "task_id": task_id,
        "status": document.status,
        "message": "Document requeued for AI processing.",
        "estimated_completion_seconds": 15
    }