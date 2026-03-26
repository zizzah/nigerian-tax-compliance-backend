"""add_ai_insights_and_bank_reconciliations

Revision ID: 001_add_ai_features
Revises: <YOUR_CURRENT_HEAD>   ← replace with your actual latest revision ID
Create Date: 2026-03-26

Creates two new tables:
  - ai_insights           (proactive AI dashboard insights)
  - bank_reconciliations  (bank statement reconciliation runs)

Run with:
    alembic upgrade head
    -- or --
    alembic upgrade 001_add_ai_features
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ── Revision identifiers ──────────────────────────────────────────────────────
revision = "001_add_ai_features"
down_revision = "59e68cff5f43"   # ← SET THIS to your current head revision string
branch_labels = None
depends_on = None


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:

    # ──────────────────────────────────────────────────────────────────────────
    # TABLE: ai_insights
    # Stores proactive AI-generated insights for each business.
    # Generated on dashboard load; cached for 24 hours; dismissible.
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "ai_insights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # insight_type: cash_flow | overdue_risk | customer_behavior |
        #               revenue_trend | anomaly | positive
        sa.Column("insight_type", sa.String(50), nullable=False),
        # severity: info | warning | critical | positive
        sa.Column("severity",     sa.String(20), nullable=False),
        sa.Column("title",        sa.String(255), nullable=False),
        sa.Column("body",         sa.Text,        nullable=False),
        sa.Column("action_label", sa.String(100), nullable=True),
        sa.Column("action_url",   sa.String(500), nullable=True),
        # data_snapshot: the raw metrics dict that generated this insight
        sa.Column("data_snapshot", postgresql.JSONB, nullable=True),
        sa.Column(
            "is_dismissed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes for ai_insights
    op.create_index(
        "ix_ai_insights_business_id",
        "ai_insights",
        ["business_id"],
    )
    op.create_index(
        "ix_ai_insights_created_at",
        "ai_insights",
        ["created_at"],
    )
    op.create_index(
        "ix_ai_insights_business_dismissed",
        "ai_insights",
        ["business_id", "is_dismissed", "created_at"],
    
    )

    # ──────────────────────────────────────────────────────────────────────────
    # TABLE: bank_reconciliations
    # Records each bank statement upload and reconciliation run.
    # One row per upload; stores the full transaction list and match results
    # as JSONB so the user can revisit previous reconciliations.
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "bank_reconciliations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename",  sa.String(255), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=True),
        # Statement date range (parsed from document when possible)
        sa.Column("period_from", sa.Date, nullable=True),
        sa.Column("period_to",   sa.Date, nullable=True),
        # Summary counters
        sa.Column(
            "total_credits",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "matched_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "unmatched_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        # status: processing | completed | failed
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'processing'"),
        ),
        # Full payloads stored as JSONB
        sa.Column("raw_transactions", postgresql.JSONB, nullable=True),
        sa.Column("match_results",    postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes for bank_reconciliations
    op.create_index(
        "ix_bank_reconciliations_business_id",
        "bank_reconciliations",
        ["business_id"],
    )
    op.create_index(
        "ix_bank_reconciliations_status",
        "bank_reconciliations",
        ["status"],
    )
    op.create_index(
        "ix_bank_reconciliations_created_at",
        "bank_reconciliations",
        ["created_at"],
    )


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # bank_reconciliations
    op.drop_index("ix_bank_reconciliations_created_at",  table_name="bank_reconciliations")
    op.drop_index("ix_bank_reconciliations_status",      table_name="bank_reconciliations")
    op.drop_index("ix_bank_reconciliations_business_id", table_name="bank_reconciliations")
    op.drop_table("bank_reconciliations")

    # ai_insights
    op.drop_index("ix_ai_insights_business_dismissed", table_name="ai_insights")
    op.drop_index("ix_ai_insights_created_at",         table_name="ai_insights")
    op.drop_index("ix_ai_insights_business_id",        table_name="ai_insights")
    op.drop_table("ai_insights")