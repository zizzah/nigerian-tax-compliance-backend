#!/usr/bin/env python3
"""
Check if performance indexes exist in the database
"""
from sqlalchemy import create_engine, text
from app.core.config import settings

print("🔍 Checking database indexes...\n")

engine = create_engine(settings.DATABASE_URL)

# Check for critical indexes
critical_indexes = [
    'ix_customers_created_at',
    'ix_customers_email',
    'ix_customers_business_active_created',
    'ix_invoices_created_at',
    'ix_products_name',
    'ix_payments_created_at'
]

with engine.connect() as conn:
    print("Critical Performance Indexes:\n")
    missing_count = 0
    
    for index_name in critical_indexes:
        result = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE indexname = :index_name
        """), {"index_name": index_name})
        
        exists = result.fetchone()
        
        if exists:
            print(f"✅ {index_name}")
        else:
            print(f"❌ {index_name} - MISSING!")
            missing_count += 1
    
    print("\n" + "="*80)
    
    if missing_count == 0:
        print("\n✅ All critical indexes exist!")
    else:
        print(f"\n⚠️  {missing_count} indexes are missing!")
        print("\nRun: python apply_indexes.py")
    
    print("\n" + "="*80)
    print("\n📋 All indexes on 'customers' table:\n")
    
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'customers'
        ORDER BY indexname
    """))
    
    for row in result:
        print(f"  • {row[0]}")

engine.dispose()