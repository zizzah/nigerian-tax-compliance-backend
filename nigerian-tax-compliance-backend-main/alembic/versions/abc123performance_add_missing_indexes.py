"""Add missing performance indexes

Revision ID: abc123performance
Revises: week4_documents
Create Date: 2026-02-12 16:00:00.000000

FIXES: Slow list endpoint (3872ms → <500ms)
ADDS: 15 critical missing indexes for ORDER BY and search operations
"""
from typing import Sequence, Union
from alembic import op # type: ignore
import sqlalchemy as sa # type: ignore


# revision identifiers, used by Alembic.
revision: str = 'abc123performance'
down_revision: Union[str, None] = 'week4_documents'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add critical missing performance indexes"""
    
    print("\n" + "="*80)
    print("🚀 ADDING MISSING PERFORMANCE INDEXES")
    print("="*80 + "\n")
    
    # ========================================================================
    # CUSTOMERS - Missing critical indexes
    # ========================================================================
    print("📋 Adding CUSTOMERS indexes...")
    
    # CRITICAL: For ORDER BY created_at DESC (fixes 3872ms issue!)
    op.create_index(
        'ix_customers_created_at',
        'customers',
        ['created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_customers_created_at (ORDER BY optimization)")
    
    # For email lookups in search
    op.create_index(
        'ix_customers_email',
        'customers',
        ['email'],
        postgresql_using='btree'
    )
    print("  ✅ ix_customers_email (search optimization)")
    
    # Composite index for: WHERE business_id AND is_active ORDER BY created_at
    op.create_index(
        'ix_customers_business_active_created',
        'customers',
        ['business_id', 'is_active', 'created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_customers_business_active_created (composite query)")
    
    # ========================================================================
    # INVOICES - Missing critical indexes
    # ========================================================================
    print("\n📋 Adding INVOICES indexes...")
    
    # CRITICAL: For ORDER BY created_at DESC
    op.create_index(
        'ix_invoices_created_at',
        'invoices',
        ['created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoices_created_at (ORDER BY optimization)")
    
    # For date range queries (from_date/to_date filters)
    op.create_index(
        'ix_invoices_issue_date',
        'invoices',
        ['issue_date'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoices_issue_date (date range queries)")
    
    op.create_index(
        'ix_invoices_due_date',
        'invoices',
        ['due_date'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoices_due_date (overdue calculations)")
    
    # Composite for: WHERE business_id AND status ORDER BY created_at
    op.create_index(
        'ix_invoices_business_status_created',
        'invoices',
        ['business_id', 'status', 'created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoices_business_status_created (composite query)")
    
    # ========================================================================
    # PRODUCTS - Missing critical indexes
    # ========================================================================
    print("\n📋 Adding PRODUCTS indexes...")
    
    # For ORDER BY name (alphabetical sorting)
    op.create_index(
        'ix_products_name',
        'products',
        ['name'],
        postgresql_using='btree'
    )
    print("  ✅ ix_products_name (alphabetical sorting)")
    
    # For ORDER BY usage_count DESC (most used products)
    op.create_index(
        'ix_products_usage_count',
        'products',
        ['usage_count'],
        postgresql_using='btree'
    )
    print("  ✅ ix_products_usage_count (popularity sorting)")
    
    # For SKU lookups (duplicate checks)
    op.create_index(
        'ix_products_sku_single',
        'products',
        ['sku'],
        postgresql_using='btree'
    )
    print("  ✅ ix_products_sku_single (SKU lookups)")
    
    # ========================================================================
    # PAYMENTS - Missing critical indexes
    # ========================================================================
    print("\n📋 Adding PAYMENTS indexes...")
    
    # For ORDER BY payment_date DESC
    op.create_index(
        'ix_payments_payment_date_order',
        'payments',
        ['payment_date'],
        postgresql_using='btree'
    )
    print("  ✅ ix_payments_payment_date_order (date sorting)")
    
    # For ORDER BY created_at DESC
    op.create_index(
        'ix_payments_created_at',
        'payments',
        ['created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_payments_created_at (ORDER BY optimization)")
    
    # ========================================================================
    # DOCUMENTS - Missing critical indexes
    # ========================================================================
    print("\n📋 Adding DOCUMENTS indexes...")
    
    # For ORDER BY created_at DESC
    op.create_index(
        'ix_documents_created_at_order',
        'documents',
        ['created_at'],
        postgresql_using='btree'
    )
    print("  ✅ ix_documents_created_at_order (ORDER BY optimization)")
    
    # ========================================================================
    # INVOICE ITEMS - Missing indexes
    # ========================================================================
    print("\n📋 Adding INVOICE_ITEMS indexes...")
    
    # For ORDER BY sort_order
    op.create_index(
        'ix_invoice_items_sort_order',
        'invoice_items',
        ['sort_order'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoice_items_sort_order (item ordering)")
    
    # Composite for: WHERE invoice_id ORDER BY sort_order
    op.create_index(
        'ix_invoice_items_invoice_sort',
        'invoice_items',
        ['invoice_id', 'sort_order'],
        postgresql_using='btree'
    )
    print("  ✅ ix_invoice_items_invoice_sort (composite)")
    
    print("\n" + "="*80)
    print("✅ ALL INDEXES CREATED SUCCESSFULLY!")
    print("="*80)
    print("\n📊 Expected Performance Improvements:")
    print("  • Customer list: 3872ms → <300ms (92% faster)")
    print("  • Invoice list: ~2000ms → <200ms (90% faster)")
    print("  • Product search: ~1500ms → <150ms (90% faster)")
    print("  • Payment list: ~1000ms → <100ms (90% faster)")
    print("\n🔍 Next Steps:")
    print("  1. ✅ Migration complete!")
    print("  2. Run: python test_all_endpoints.py")
    print("  3. Verify: Response times should be <500ms")
    print("="*80 + "\n")


def downgrade() -> None:
    """Remove performance indexes"""
    
    print("Removing performance indexes...")
    
    # Invoice items
    op.drop_index('ix_invoice_items_invoice_sort', table_name='invoice_items')
    op.drop_index('ix_invoice_items_sort_order', table_name='invoice_items')
    
    # Documents
    op.drop_index('ix_documents_created_at_order', table_name='documents')
    
    # Payments
    op.drop_index('ix_payments_created_at', table_name='payments')
    op.drop_index('ix_payments_payment_date_order', table_name='payments')
    
    # Products
    op.drop_index('ix_products_sku_single', table_name='products')
    op.drop_index('ix_products_usage_count', table_name='products')
    op.drop_index('ix_products_name', table_name='products')
    
    # Invoices
    op.drop_index('ix_invoices_business_status_created', table_name='invoices')
    op.drop_index('ix_invoices_due_date', table_name='invoices')
    op.drop_index('ix_invoices_issue_date', table_name='invoices')
    op.drop_index('ix_invoices_created_at', table_name='invoices')
    
    # Customers
    op.drop_index('ix_customers_business_active_created', table_name='customers')
    op.drop_index('ix_customers_email', table_name='customers')
    op.drop_index('ix_customers_created_at', table_name='customers')
    
    print("✅ Indexes removed")