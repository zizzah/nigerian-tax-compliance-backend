"""add cloudinary_public_id and bank statement columns

Revision ID: add_cloudinary_and_bank_cols
Revises: <replace with your latest revision id>
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision    = 'add_cloudinary_and_bank_cols'
down_revision = '16360ae39239'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Proper column for Cloudinary public_id (was hacked into review_notes)
    op.add_column('documents', sa.Column('cloudinary_public_id', sa.String(500), nullable=True))

    # Bank statement columns
    op.add_column('documents', sa.Column('opening_balance',      sa.Numeric(15, 2), nullable=True))
    op.add_column('documents', sa.Column('closing_balance',      sa.Numeric(15, 2), nullable=True))
    op.add_column('documents', sa.Column('total_inflow',         sa.Numeric(15, 2), nullable=True))
    op.add_column('documents', sa.Column('total_outflow',        sa.Numeric(15, 2), nullable=True))
    op.add_column('documents', sa.Column('inflow_transactions',  JSONB,             nullable=True))
    op.add_column('documents', sa.Column('outflow_transactions', JSONB,             nullable=True))

    # Migrate existing data: copy review_notes → cloudinary_public_id
    # for rows where review_notes looks like a Cloudinary public_id
    op.execute("""
        UPDATE documents
        SET cloudinary_public_id = review_notes
        WHERE review_notes LIKE 'taxflow/%'
    """)

    # Widen ai_model_used from 50 to 100 chars
    op.alter_column('documents', 'ai_model_used',
                    existing_type=sa.String(50),
                    type_=sa.String(100),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('documents', 'ai_model_used',
                    existing_type=sa.String(100),
                    type_=sa.String(50),
                    existing_nullable=True)
    op.drop_column('documents', 'outflow_transactions')
    op.drop_column('documents', 'inflow_transactions')
    op.drop_column('documents', 'total_outflow')
    op.drop_column('documents', 'total_inflow')
    op.drop_column('documents', 'closing_balance')
    op.drop_column('documents', 'opening_balance')
    op.drop_column('documents', 'cloudinary_public_id')