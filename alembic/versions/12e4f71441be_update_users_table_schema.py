"""Update users table schema

Revision ID: 12e4f71441be
Revises: aaf857db5b2b
Create Date: 2026-02-01

"""
from alembic import op # type: ignore
import sqlalchemy as sa # type: ignore
from sqlalchemy.dialects import postgresql # type: ignore

# revision identifiers, used by Alembic.
revision = '12e4f71441be'
down_revision = 'aaf857db5b2b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add phone column
    op.add_column('users', sa.Column('phone', sa.String(length=20), nullable=True))
    
    # Convert id to UUID with explicit USING clause
    op.execute('ALTER TABLE users ALTER COLUMN id TYPE UUID USING id::uuid')
    
    # Convert DateTime columns with timezone - with explicit USING clauses
    op.execute('ALTER TABLE users ALTER COLUMN locked_until TYPE TIMESTAMP WITH TIME ZONE USING locked_until::timestamp with time zone')
    op.execute('ALTER TABLE users ALTER COLUMN email_verified_at TYPE TIMESTAMP WITH TIME ZONE USING email_verified_at::timestamp with time zone')
    op.execute('ALTER TABLE users ALTER COLUMN reset_token_expires_at TYPE TIMESTAMP WITH TIME ZONE USING reset_token_expires_at::timestamp with time zone')
    op.execute('ALTER TABLE users ALTER COLUMN last_login TYPE TIMESTAMP WITH TIME ZONE USING last_login::timestamp with time zone')
    op.execute('ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at::timestamp with time zone')
    op.execute('ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at::timestamp with time zone')
    
    # Drop full_name column
    op.drop_column('users', 'full_name')


def downgrade() -> None:
    # Add back full_name column
    op.add_column('users', sa.Column('full_name', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    
    # Revert DateTime columns to timestamp without timezone
    op.execute('ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE')
    op.execute('ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE')
    op.execute('ALTER TABLE users ALTER COLUMN last_login TYPE TIMESTAMP WITHOUT TIME ZONE')
    op.execute('ALTER TABLE users ALTER COLUMN reset_token_expires_at TYPE TIMESTAMP WITHOUT TIME ZONE')
    op.execute('ALTER TABLE users ALTER COLUMN email_verified_at TYPE TIMESTAMP WITHOUT TIME ZONE')
    op.execute('ALTER TABLE users ALTER COLUMN locked_until TYPE TIMESTAMP WITHOUT TIME ZONE')
    
    # Revert id to VARCHAR
    op.execute('ALTER TABLE users ALTER COLUMN id TYPE VARCHAR USING id::varchar')
    
    # Drop phone column
    op.drop_column('users', 'phone')