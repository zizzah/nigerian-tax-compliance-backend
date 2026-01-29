#!/usr/bin/env python
"""
Check Tables Script
Check if tables exist in the database
"""

from app.core.database import engine
from sqlalchemy import text

print("=" * 50)
print("CHECKING TABLES")
print("=" * 50)
print()

try:
    with engine.connect() as conn:
        # Check if users table exists
        result = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')"))
        exists = result.fetchone()[0]
        print(f"Users table exists: {exists}")

        # List all tables
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = result.fetchall()
        print(f"All tables: {[row[0] for row in tables]}")

        conn.commit()

except Exception as e:
    print(f"❌ Error: {e}")
