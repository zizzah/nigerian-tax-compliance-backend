"""Add documents table for AI processing

Revision ID: week4_documents
Revises: 6d718367d4eb
Create Date: 2026-02-05 09:00:00

"""
from typing import Sequence, Union
from alembic import op # type: ignore
import sqlalchemy as sa # type: ignore
from sqlalchemy.dialects import postgresql # type: ignore
from sqlalchemy import text # type: ignore

# revision identifiers, used by Alembic.
revision: str = 'week4_documents'
down_revision: Union[str, None] = '6d718367d4eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add documents table"""
    
    # Use raw SQL to create ENUMs only if they don't exist
    conn = op.get_bind()
    
    # Create DocumentType enum
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE documenttype AS ENUM ('RECEIPT', 'INVOICE', 'BANK_STATEMENT', 'TAX_DOCUMENT', 'OTHER');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    # Create ProcessingStatus enum
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE processingstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REVIEW_NEEDED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('vendor_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Document info
        sa.Column('document_type', postgresql.ENUM(name='documenttype', create_type=False), nullable=False),
        sa.Column('document_number', sa.String(100), nullable=True),
        sa.Column('document_date', sa.Date(), nullable=True),
        
        # File info
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        
        # Processing status
        sa.Column('status', postgresql.ENUM(name='processingstatus', create_type=False), nullable=False, server_default='PENDING'),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('processing_duration_seconds', sa.Numeric(6, 2), nullable=True),
        
        # Extracted data
        sa.Column('vendor_name', sa.String(255), nullable=True),
        sa.Column('vendor_tin', sa.String(20), nullable=True),
        sa.Column('vendor_address', sa.Text(), nullable=True),
        sa.Column('vendor_phone', sa.String(20), nullable=True),
        
        # Line items
        sa.Column('line_items', postgresql.JSONB(), nullable=True),
        
        # Financial
        sa.Column('subtotal', sa.Numeric(15, 2), server_default='0', nullable=False),
        sa.Column('vat_amount', sa.Numeric(15, 2), server_default='0', nullable=False),
        sa.Column('total_amount', sa.Numeric(15, 2), server_default='0', nullable=False),
        sa.Column('vat_rate', sa.Numeric(5, 2), server_default='7.5', nullable=False),
        sa.Column('is_vatable', sa.Boolean(), server_default='true', nullable=False),
        
        # Payment info
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        
        # Categorization
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        
        # OCR data
        sa.Column('ocr_raw_text', sa.Text(), nullable=True),
        sa.Column('ocr_confidence', sa.Numeric(3, 2), nullable=True),
        
        # AI data
        sa.Column('ai_extracted_data', postgresql.JSONB(), nullable=True),
        sa.Column('ai_model_used', sa.String(50), nullable=True, server_default='llama-3.3-70b-versatile'),
        
        # Review
        sa.Column('requires_review', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        
        # Metadata
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default='false', nullable=False),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    )
    
    # Create indexes
    op.create_index('ix_documents_business_id', 'documents', ['business_id'])
    op.create_index('ix_documents_document_type', 'documents', ['document_type'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_document_date', 'documents', ['document_date'])
    op.create_index('ix_documents_category', 'documents', ['category'])
    op.create_index('ix_documents_requires_review', 'documents', ['requires_review'])
    op.create_index('ix_documents_is_archived', 'documents', ['is_archived'])
    
    # Composite indexes for common queries
    op.create_index('ix_documents_business_status', 'documents', ['business_id', 'status'])
    op.create_index('ix_documents_business_date', 'documents', ['business_id', 'document_date'])


def downgrade() -> None:
    """Downgrade schema - Remove documents table"""
    op.drop_index('ix_documents_business_date', table_name='documents')
    op.drop_index('ix_documents_business_status', table_name='documents')
    op.drop_index('ix_documents_is_archived', table_name='documents')
    op.drop_index('ix_documents_requires_review', table_name='documents')
    op.drop_index('ix_documents_category', table_name='documents')
    op.drop_index('ix_documents_document_date', table_name='documents')
    op.drop_index('ix_documents_status', table_name='documents')
    op.drop_index('ix_documents_document_type', table_name='documents')
    op.drop_index('ix_documents_business_id', table_name='documents')
    
    op.drop_table('documents')
    
    # Drop enums
    conn = op.get_bind()
    conn.execute(text("DROP TYPE IF EXISTS processingstatus CASCADE;"))
    conn.execute(text("DROP TYPE IF EXISTS documenttype CASCADE;"))