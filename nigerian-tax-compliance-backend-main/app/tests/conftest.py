import pytest # type: ignore
import os

# Set required environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("QSTASH_TOKEN", "test-qstash-token")
os.environ.setdefault("QSTASH_CURRENT_SIGNING_KEY", "test-signing-key")
os.environ.setdefault("QSTASH_NEXT_SIGNING_KEY", "test-next-signing-key")

from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker # type: ignore
from fastapi.testclient import TestClient # type: ignore
from app.core.database import Base, get_db # type: ignore
from app.main import app
from app.core.config import settings

# Use SQLite for testing instead of PostgreSQL
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}  # Only needed for SQLite
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create test database"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create test client"""
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data():
    """Test user data"""
    return {
        "email": "test@example.com",
        "password": "Test@123",
        "confirm_password": "Test@123",
        "first_name": "Test",
        "last_name": "User"
    }