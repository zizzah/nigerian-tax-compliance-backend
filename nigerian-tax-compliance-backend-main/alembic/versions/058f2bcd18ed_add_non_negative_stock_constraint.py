"""add_non_negative_stock_constraint

Revision ID: 058f2bcd18ed
Revises: 91735bd7ea66
Create Date: 2026-04-22 17:15:03.630339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '058f2bcd18ed'
down_revision: Union[str, Sequence[str], None] = '91735bd7ea66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    # Already applied directly in Neon — this keeps migration history in sync
    op.create_check_constraint(
        "quantity_in_stock_non_negative",
        "products",
        "quantity_in_stock >= 0"
    )

def downgrade() -> None:
    op.drop_constraint(
        "quantity_in_stock_non_negative",
        "products",
        type_="check"
    )