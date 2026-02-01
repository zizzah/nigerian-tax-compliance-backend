"""
Test if configuration is working
"""
from app.core.config import settings
from app.core.database import engine
from sqlalchemy import text

print("Testing configuration...")
print(f"✓ App Name: {settings.APP_NAME}")
print(f"✓ Database URL: {settings.DATABASE_URL[:20]}...")
print(f"✓ Environment: {settings.ENVIRONMENT}")

print("\nTesting database connection...")
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✓ Database connection successful!")
except Exception as e:
    print(f"✗ Database connection failed: {e}")