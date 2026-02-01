"""
Check Database Connection
Usage: python scripts/check_db.py
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import engine, SessionLocal
from app.models.user import User
from sqlalchemy import text

def check_database():
    """Check database connection and table status"""
    print("=" * 60)
    print("🔍 DATABASE CONNECTION CHECK")
    print("=" * 60)
    print("")
    
    try:
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0] # type: ignore
            print("✅ Database connection successful!")
            print(f"   PostgreSQL version: {version[:50]}...")
            print("")
        
        # Check tables
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            
            if tables:
                print(f"✅ Found {len(tables)} table(s):")
                for table in tables:
                    print(f"   - {table}")
            else:
                print("⚠️  No tables found. Run migrations!")
                print("   Command: alembic upgrade head")
            print("")
        
        # Check user count
        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            print(f"👥 Users in database: {user_count}")
            
            if user_count > 0:
                print("\n   Recent users:")
                recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
                for user in recent_users:
                    verified = "✓" if user.is_verified else "✗" # type: ignore
                    admin = "👑" if user.is_superuser else "👤" # type: ignore
                    active = "🟢" if user.is_active else "🔴" # type: ignore
                    print(f"   {admin} {active} {user.email} {verified}")
            else:
                print("\n⚠️  No users in database.")
                print("   Run: python scripts/create_admin.py")
                print("   Run: python scripts/seed_test_data.py")
        finally:
            db.close()
        
        print("")
        print("=" * 60)
        print("✅ All checks passed!")
        print("=" * 60)
        
    except Exception as e:
        print("")
        print("=" * 60)
        print("❌ Database check failed!")
        print("=" * 60)
        print(f"Error: {e}")
        print("")
        import traceback
        traceback.print_exc()
        print("")
        print("Troubleshooting:")
        print("1. Check your DATABASE_URL in .env")
        print("2. Make sure PostgreSQL is running")
        print("3. Run: alembic upgrade head")
        print("=" * 60)

if __name__ == "__main__":
    check_database()