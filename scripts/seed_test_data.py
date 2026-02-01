"""
Seed Test Data
Run this to create test users for development
Usage: python scripts/seed_test_data.py
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash
import uuid

def seed_test_users():
    """Create test users for development"""
    db = SessionLocal()
    
    test_users = [
        {
            "email": "user1@example.com",
            "password": "User1@123",
            "is_verified": True,
            "phone": "+2348012345678"
        },
        {
            "email": "user2@example.com",
            "password": "User2@123",
            "is_verified": True,
            "phone": "+2348012345679"
        },
        {
            "email": "user3@example.com",
            "password": "User3@123",
            "is_verified": False,
            "phone": "+2348012345680"
        },
        {
            "email": "verified@example.com",
            "password": "Verified@123",
            "is_verified": True,
            "phone": None
        },
        {
            "email": "unverified@example.com",
            "password": "Unverified@123",
            "is_verified": False,
            "phone": None
        }
    ]
    
    try:
        created_count = 0
        skipped_count = 0
        
        print("=" * 60)
        print("🌱 SEEDING TEST DATA")
        print("=" * 60)
        print("")
        
        for user_data in test_users:
            # Check if user already exists
            existing_user = db.query(User).filter(User.email == user_data["email"]).first()
            
            if existing_user:
                print(f"⏭️  Skipping {user_data['email']} (already exists)")
                skipped_count += 1
                continue
            
            # Create user
            user = User(
                id=uuid.uuid4(),
                email=user_data["email"],
                password_hash=get_password_hash(user_data["password"]),
                phone=user_data.get("phone"),
                is_active=True,
                is_verified=user_data["is_verified"]
            )
            db.add(user)
            created_count += 1
            print(f"✅ Created: {user_data['email']}")
        
        db.commit()
        
        print("")
        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"✅ Created: {created_count} users")
        print(f"⏭️  Skipped: {skipped_count} users (already existed)")
        print("")
        
        if created_count > 0:
            print("=" * 60)
            print("🔑 TEST USER CREDENTIALS")
            print("=" * 60)
            for user_data in test_users:
                verified_status = "✓ Verified" if user_data["is_verified"] else "✗ Not Verified"
                print(f"\n  Email: {user_data['email']}")
                print(f"  Password: {user_data['password']}")
                print(f"  Status: {verified_status}")
            print("")
            print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error seeding test data: {e}")
        print("")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_test_users()