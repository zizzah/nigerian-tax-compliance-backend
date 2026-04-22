"""Add unique constraint on business_id + sku

Revision ID: 6d718367d4eb
Revises: 0d4f3aaa0f58
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op # type: ignore
import sqlalchemy as sa # type: ignore


# revision identifiers, used by Alembic.
revision: str = '6d718367d4eb'
down_revision: Union[str, None] = '0d4f3aaa0f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint on (business_id, sku) combination"""
    
    # First, clean up any existing duplicates
    # This query will keep the most recently created product for each duplicate SKU
    op.execute("""
        DELETE FROM products
        WHERE id NOT IN (
            SELECT DISTINCT ON (business_id, sku) id
            FROM products
            WHERE sku IS NOT NULL
            ORDER BY business_id, sku, created_at DESC
        )
        AND sku IS NOT NULL
    """)
    
    # Add the unique constraint
    op.create_unique_constraint(
        'uq_products_business_sku',  # Constraint name
        'products',                   # Table name
        ['business_id', 'sku']        # Columns
    )
    
    # Create an index for better query performance
    op.create_index(
        'ix_products_business_sku',
        'products',
        ['business_id', 'sku'],
        unique=True
    )


def downgrade() -> None:
    """Remove the unique constraint"""
    op.drop_index('ix_products_business_sku', table_name='products')
    op.drop_constraint('uq_products_business_sku', 'products', type_='unique')