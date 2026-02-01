"""
Create Admin User
Run this to create an admin account for testing
Usage: python scripts/create_admin.py
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Now imports will work
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash
import uuid

def create_admin():
    """Create admin user"""
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(User).filter(User.email == "admin@example.com").first()
        
        if existing_admin:
            print("⚠️  Admin user already exists!")
            print(f"   Email: {existing_admin.email}")
            print(f"   ID: {existing_admin.id}")
            return
        
        # Create admin user
        admin = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            password_hash=get_password_hash("Admin@123"),
            is_active=True,
            is_verified=True,
            is_superuser=True
        )
        
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print("=" * 60)
        print("✅ Admin user created successfully!")
        print("=" * 60)
        print(f"   Email: {admin.email}")
        print(f"   Password: Admin@123")
        print(f"   ID: {admin.id}")
        print("")
        print("⚠️  IMPORTANT: Change this password immediately in production!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()