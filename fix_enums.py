from sqlalchemy import create_engine, text
from app.core.config import settings

# Create engine
engine = create_engine(settings.DATABASE_URL)

# Drop the existing ENUM types
with engine.connect() as conn:
    conn.execute(text("DROP TYPE IF EXISTS documenttype CASCADE;"))
    conn.execute(text("DROP TYPE IF EXISTS processingstatus CASCADE;"))
    conn.commit()
    print("✅ Dropped existing ENUM types successfully!")

print("Now run: alembic upgrade head")