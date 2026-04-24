"""add_non_negative_stock_constraint
Revision ID: 058f2bcd18ed
Revises: 91735bd7ea66
Create Date: 2026-04-22 17:15:03.630339
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '058f2bcd18ed'
down_revision: Union[str, Sequence[str], None] = '91735bd7ea66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        DO `push
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'quantity_in_stock_non_negative'
            ) THEN
                ALTER TABLE products
                ADD CONSTRAINT quantity_in_stock_non_negative
                CHECK (quantity_in_stock >= 0);
            END IF;
        END
        `push;
    """)

def downgrade() -> None:
    op.drop_constraint(
        'quantity_in_stock_non_negative',
        'products',
        type_='check'
    )
