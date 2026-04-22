"""add_non_negative_stock_constraint

Revision ID: e3bafad6041d
Revises: 058f2bcd18ed
Create Date: 2026-04-22 17:19:13.294693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3bafad6041d'
down_revision: Union[str, Sequence[str], None] = '058f2bcd18ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
