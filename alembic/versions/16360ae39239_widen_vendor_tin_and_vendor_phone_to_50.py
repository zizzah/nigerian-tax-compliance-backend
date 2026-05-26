"""widen vendor_tin and vendor_phone to 50

Revision ID: 16360ae39239
Revises: <put_previous_revision_id_here>
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '16360ae39239'
down_revision = '058f2bcd18ed'  # ← replace None with your previous migration's revision ID
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('documents', 'vendor_tin',
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=True)
    op.alter_column('documents', 'vendor_phone',
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=True)


def downgrade():
    op.alter_column('documents', 'vendor_tin',
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=True)
    op.alter_column('documents', 'vendor_phone',
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=True)