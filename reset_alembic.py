from app.core.database import engine
from sqlalchemy import text

print("=" * 60)
print("RESETTING ALEMBIC")
print("=" * 60)
print()
print("Dropping alembic_version table...")

try:
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conn.commit()
    print("✅ Successfully dropped alembic_version table")
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
    print("Try running this SQL manually in your database:")
    print("DROP TABLE IF EXISTS alembic_version;")