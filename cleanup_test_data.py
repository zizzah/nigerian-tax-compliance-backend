"""
Database Cleanup Script for Testing
====================================

This script cleans up test data from the database before running tests.

Run before testing: python cleanup_test_data.py
"""

from sqlalchemy import create_engine, text
from app.core.config import settings
import sys

def cleanup_test_data():
    """Remove all test data from database"""
    
    print("=" * 80)
    print("DATABASE CLEANUP - Test Data Removal")
    print("=" * 80)
    print()
    
    try:
        # Create engine
        engine = create_engine(settings.DATABASE_URL)
        
        print("Connecting to database...")
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                # Delete test users (and cascade to businesses, customers, etc.)
                print("Deleting test users and related data...")
                result = conn.execute(text("""
                    DELETE FROM users 
                    WHERE email LIKE 'test_%@example.com'
                    OR email LIKE '%@test.com'
                """))
                deleted_users = result.rowcount
                
                # Commit transaction
                trans.commit()
                
                print(f"✓ Deleted {deleted_users} test users and their data")
                print()
                print("Database cleanup complete!")
                print()
                print("You can now run: python test_all_endpoints.py")
                
                return True
                
            except Exception as e:
                trans.rollback()
                print(f"✗ Error during cleanup: {e}")
                return False
                
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        print()
        print("Make sure:")
        print("1. Database is running")
        print("2. DATABASE_URL is correct in .env")
        return False


if __name__ == "__main__":
    success = cleanup_test_data()
    sys.exit(0 if success else 1)