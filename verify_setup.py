#!/usr/bin/env python
"""
Setup Verification Script
Tests database connection and environment configuration
"""

import sys
from pathlib import Path

print("=" * 70)
print("🔍 SETUP VERIFICATION SCRIPT")
print("=" * 70)
print()

# ============================================================================
# Step 1: Check if .env exists
# ============================================================================
print("Step 1: Checking .env file...")
if not Path(".env").exists():
    print("❌ .env file not found!")
    print("   Create it from .env.example or use the corrected version")
    sys.exit(1)
print("✅ .env file exists")
print()

# ============================================================================
# Step 2: Load configuration
# ============================================================================
print("Step 2: Loading configuration...")
try:
    from app.core.config import settings
    print("✅ Configuration loaded successfully")
    print(f"   - App Name: {settings.APP_NAME}")
    print(f"   - Version: {settings.APP_VERSION}")
    print(f"   - Environment: {settings.ENVIRONMENT}")
    print(f"   - Debug: {settings.DEBUG}")
except Exception as e:
    print(f"❌ Failed to load configuration: {e}")
    print()
    print("Common issues:")
    print("1. Make sure app/core/config.py exists")
    print("2. Check if pydantic-settings is installed: pip install pydantic-settings")
    print("3. Verify DATABASE_URL format in .env")
    sys.exit(1)
print()

# ============================================================================
# Step 3: Check DATABASE_URL format
# ============================================================================
print("Step 3: Checking DATABASE_URL format...")
db_url = settings.DATABASE_URL

# Check for common mistakes
if db_url.startswith("psql "):
    print("❌ DATABASE_URL has 'psql' command prefix - remove it!")
    print(f"   Current: {db_url[:50]}...")
    print("   Should start with: postgresql://")
    sys.exit(1)

if not db_url.startswith("postgresql://"):
    print(f"❌ DATABASE_URL should start with 'postgresql://'")
    print(f"   Current: {db_url[:50]}...")
    sys.exit(1)

print("✅ DATABASE_URL format looks correct")
print(f"   - Host: {db_url.split('@')[1].split('/')[0]}")
print()

# ============================================================================
# Step 4: Test database connection
# ============================================================================
print("Step 4: Testing database connection...")
try:
    from app.core.database import engine
    from sqlalchemy import text
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print("✅ Database connection successful!")
        print(f"   - PostgreSQL version: {version.split(',')[0]}")
except Exception as e:
    print(f"❌ Database connection failed!")
    print(f"   Error: {e}")
    print()
    print("Troubleshooting:")
    print("1. Check if DATABASE_URL in .env is correct")
    print("2. Verify your Neon database is running")
    print("3. Check if your IP is whitelisted (Neon usually allows all)")
    print("4. Try connecting via psql command line to verify credentials")
    sys.exit(1)
print()

# ============================================================================
# Step 5: Check if models are importable
# ============================================================================
print("Step 5: Checking models...")
try:
    from app.models import User
    print("✅ User model imported successfully")
except Exception as e:
    print(f"❌ Failed to import models: {e}")
    print("   Make sure app/models/user.py exists")
    sys.exit(1)
print()

# ============================================================================
# Step 6: Check if tables exist
# ============================================================================
print("Step 6: Checking database tables...")
try:
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if not tables:
        print("⚠️  No tables found in database")
        print("   Run: alembic upgrade head")
    else:
        print(f"✅ Found {len(tables)} table(s):")
        for table in tables:
            print(f"   - {table}")
    
    if 'users' in tables:
        print("✅ Users table exists - ready to go!")
    else:
        print("⚠️  Users table not found")
        print("   Run these commands:")
        print("   1. alembic revision --autogenerate -m 'Initial migration'")
        print("   2. alembic upgrade head")
        
except Exception as e:
    print(f"⚠️  Could not check tables: {e}")
print()

# ============================================================================
# Step 7: Check critical dependencies
# ============================================================================
print("Step 7: Checking critical dependencies...")

dependencies = {
    'fastapi': 'FastAPI',
    'sqlalchemy': 'SQLAlchemy',
    'alembic': 'Alembic',
    'pydantic': 'Pydantic',
    'jose': 'python-jose',
    'passlib': 'Passlib',
}

missing = []
for module, name in dependencies.items():
    try:
        __import__(module)
        print(f"   ✅ {name}")
    except ImportError:
        print(f"   ❌ {name} not installed")
        missing.append(name)

if missing:
    print()
    print(f"❌ Missing dependencies: {', '.join(missing)}")
    print("   Run: pip install -r requirements.txt")
    sys.exit(1)
print()

# ============================================================================
# Step 8: Check API Keys (optional)
# ============================================================================
print("Step 8: Checking API Keys (optional)...")
if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-"):
    print("   ✅ OpenAI API key is set")
else:
    print("   ⚠️  OpenAI API key not set (optional)")

if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.startswith("sk-ant-"):
    print("   ✅ Anthropic API key is set")
else:
    print("   ⚠️  Anthropic API key not set (optional)")
print()

# ============================================================================
# Final Summary
# ============================================================================
print("=" * 70)
print("📊 VERIFICATION SUMMARY")
print("=" * 70)
print()
print("✅ Environment configured correctly")
print("✅ Database connection working")
print("✅ All critical dependencies installed")
print()

if 'users' in tables:
    print("🎉 Your setup is complete and ready!")
    print()
    print("Next steps:")
    print("1. Start the server: uvicorn app.main:app --reload")
    print("2. Visit API docs: http://localhost:8000/docs")
    print("3. Start building features!")
else:
    print("⚠️  Setup is almost complete!")
    print()
    print("Final steps:")
    print("1. Create migration: alembic revision --autogenerate -m 'Initial migration'")
    print("2. Apply migration: alembic upgrade head")
    print("3. Run this script again to verify")
    print("4. Start server: uvicorn app.main:app --reload")

print()
print("=" * 70)
