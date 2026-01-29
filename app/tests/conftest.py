"""
Test configuration and fixtures for authentication system tests
"""
import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from factory import LazyFunction
from factory.alchemy import SQLAlchemyModelFactory

from app.core.database import Base, get_db
from app.core.config import settings
from app.main import app
from app.models import User
from app.core.security import get_password_hash


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def test_db():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_db):
    """Provide a clean database session for each test"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Provide a test client with database session override"""
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# User factory for creating test users
class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = None  # Will be set in fixture

    id = LazyFunction(lambda: str(uuid.uuid4()))
    email = LazyFunction(lambda: f"test_{uuid.uuid4()}@example.com")
    password_hash = LazyFunction(lambda: get_password_hash("testpassword123"))
    full_name = "Test User"
    is_active = True
    is_verified = True
    is_superuser = False
    failed_login_attempts = 0
    locked_until = None
    last_login = None
    email_verified_at = None
    verification_token = None
    reset_token = None
    reset_token_expires_at = None


@pytest.fixture(scope="function")
def user_factory(db_session):
    """Provide a user factory with database session"""
    UserFactory._meta.sqlalchemy_session = db_session
    return UserFactory


@pytest.fixture(scope="function")
def test_user(db_session, user_factory):
    """Create a test user"""
    user = user_factory.create()
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def unverified_user(db_session, user_factory):
    """Create an unverified test user"""
    user = user_factory.create(is_verified=False)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def inactive_user(db_session, user_factory):
    """Create an inactive test user"""
    user = user_factory.create(is_active=False)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def locked_user(db_session, user_factory):
    """Create a locked test user"""
    from datetime import datetime, timedelta
    user = user_factory.create(
        failed_login_attempts=5,
        locked_until=datetime.utcnow() + timedelta(minutes=30)
    )
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def superuser(db_session, user_factory):
    """Create a superuser"""
    user = user_factory.create(is_superuser=True)
    db_session.commit()
    return user
