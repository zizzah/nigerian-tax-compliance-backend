#!/usr/bin/env python
"""
Drop All Tables Script
Drops all tables in the database to start fresh
"""

from app.core.database import engine
from sqlalchemy import text, inspect

print("=" * 60)
print("DROPPING ALL TABLES")
print("=" * 60)
print()

try:
    with engine.connect() as conn:
        # Get all table names
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            print("No tables found in database")
        else:
            print(f"Found {len(tables)} table(s): {', '.join(tables)}")
            print()

            # Drop all tables
            for table in tables:
                print(f"Dropping table: {table}")
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                conn.commit()

            print()
            print("✅ Successfully dropped all tables")

        print()
        print("=" * 60)
        print("NEXT STEPS:")
        print("=" * 60)
        print()
        print("1. Run: alembic revision --autogenerate -m 'Initial migration'")
        print("2. Run: alembic upgrade head")
        print("3. Run: python verify_setup.py")
        print("4. Run: uvicorn app.main:app --reload")
        print()

except Exception as e:
    print(f"❌ Error: {e}")
    print()
    print("Make sure your database connection is working")
