# alembic/versions/0001_reset_documents_receipts_bank_statements.py
"""
Reset documents table. Create receipts and bank_statements tables.

Revision ID: 0001_reset_documents
Revises: add_cloudinary_and_bank_cols
Create Date: 2026-05-28
"""
from alembic import op

revision      = '0001_reset_documents'
down_revision = 'add_cloudinary_and_bank_cols'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bank_statements CASCADE")
    op.execute("DROP TABLE IF EXISTS receipts CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TYPE IF EXISTS documenttype CASCADE")
    op.execute("DROP TYPE IF EXISTS processingstatus CASCADE")

    op.execute("""
        CREATE TYPE documenttype AS ENUM (
            'RECEIPT', 'INVOICE', 'BANK_STATEMENT', 'TAX_DOCUMENT', 'OTHER'
        )
    """)

    op.execute("""
        CREATE TYPE processingstatus AS ENUM (
            'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REVIEW_NEEDED'
        )
    """)

    op.execute("""
        CREATE TABLE documents (
            id                          UUID          NOT NULL DEFAULT gen_random_uuid(),
            business_id                 UUID          NOT NULL,
            document_type               documenttype  NOT NULL,
            original_filename           VARCHAR(255)  NOT NULL,
            file_size                   INTEGER       NOT NULL,
            file_type                   VARCHAR(50)   NOT NULL,
            status                      processingstatus NOT NULL DEFAULT 'PENDING',
            confidence_score            NUMERIC(3,2),
            processing_started_at       TIMESTAMPTZ,
            processing_completed_at     TIMESTAMPTZ,
            processing_error            TEXT,
            processing_duration_seconds NUMERIC(6,2),
            ai_model_used               VARCHAR(100),
            requires_review             BOOLEAN       NOT NULL DEFAULT false,
            review_notes                TEXT,
            reviewed_by_user_id         UUID,
            reviewed_at                 TIMESTAMPTZ,
            notes                       TEXT,
            is_archived                 BOOLEAN       NOT NULL DEFAULT false,
            created_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)

    op.execute("CREATE INDEX ix_documents_business_id    ON documents (business_id)")
    op.execute("CREATE INDEX ix_documents_document_type  ON documents (document_type)")
    op.execute("CREATE INDEX ix_documents_status         ON documents (status)")
    op.execute("CREATE INDEX ix_documents_requires_review ON documents (requires_review)")
    op.execute("CREATE INDEX ix_documents_is_archived    ON documents (is_archived)")

    op.execute("""
        CREATE TABLE receipts (
            id                  UUID          NOT NULL DEFAULT gen_random_uuid(),
            document_id         UUID          NOT NULL UNIQUE,
            business_id         UUID          NOT NULL,
            customer_id         UUID,
            vendor_id           UUID,
            document_type       documenttype  NOT NULL,
            document_number     VARCHAR(100),
            document_date       DATE,
            vendor_name         VARCHAR(255),
            vendor_tin          VARCHAR(50),
            vendor_address      TEXT,
            vendor_phone        VARCHAR(50),
            line_items          JSONB,
            subtotal            NUMERIC(15,2) DEFAULT 0,
            vat_amount          NUMERIC(15,2) DEFAULT 0,
            total_amount        NUMERIC(15,2) DEFAULT 0,
            vat_rate            NUMERIC(5,2)  DEFAULT 7.5,
            is_vatable          BOOLEAN       DEFAULT true,
            payment_method      VARCHAR(50),
            payment_reference   VARCHAR(100),
            category            VARCHAR(100),
            tags                JSONB,
            ocr_raw_text        TEXT,
            ocr_confidence      NUMERIC(3,2),
            ai_extracted_data   JSONB,
            created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_receipts_document
                FOREIGN KEY (document_id)
                REFERENCES documents (id)
                ON DELETE CASCADE
        )
    """)

    op.execute("CREATE INDEX ix_receipts_document_id   ON receipts (document_id)")
    op.execute("CREATE INDEX ix_receipts_business_id   ON receipts (business_id)")
    op.execute("CREATE INDEX ix_receipts_document_date ON receipts (document_date)")
    op.execute("CREATE INDEX ix_receipts_category      ON receipts (category)")

    op.execute("""
        CREATE TABLE bank_statements (
            id                      UUID        NOT NULL DEFAULT gen_random_uuid(),
            document_id             UUID        NOT NULL UNIQUE,
            business_id             UUID        NOT NULL,
            account_name            VARCHAR(255),
            account_number          VARCHAR(100),
            bank_name               VARCHAR(100),
            period_from             DATE,
            period_to               DATE,
            opening_balance         NUMERIC(15,2),
            closing_balance         NUMERIC(15,2),
            total_inflow            NUMERIC(15,2),
            total_outflow           NUMERIC(15,2),
            inflow_transactions     JSONB,
            outflow_transactions    JSONB,
            ai_extracted_data       JSONB,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_bank_statements_document
                FOREIGN KEY (document_id)
                REFERENCES documents (id)
                ON DELETE CASCADE
        )
    """)

    op.execute("CREATE INDEX ix_bank_statements_document_id ON bank_statements (document_id)")
    op.execute("CREATE INDEX ix_bank_statements_business_id ON bank_statements (business_id)")
    op.execute("CREATE INDEX ix_bank_statements_period_from ON bank_statements (period_from)")
    op.execute("CREATE INDEX ix_bank_statements_period_to   ON bank_statements (period_to)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bank_statements CASCADE")
    op.execute("DROP TABLE IF EXISTS receipts CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TYPE IF EXISTS processingstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS documenttype CASCADE")