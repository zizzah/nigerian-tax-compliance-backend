"""
Tests for security utilities
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    authenticate_user,
    check_user_locked,
    record_failed_login,
    reset_failed_logins,
    generate_verification_token,
    generate_reset_token
)


class TestPasswordFunctions:
    """Test password hashing and verification"""

    def test_get_password_hash(self):
        """Test password hashing"""
        password = "testpassword123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        password = "testpassword123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False


class TestTokenFunctions:
    """Test JWT token creation and verification"""

    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_refresh_token(self):
        """Test refresh token creation"""
        data = {"sub": "user123"}
        token = create_refresh_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload

    def test_verify_token_valid_access(self):
        """Test verifying valid access token"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        user_id = verify_token(token, token_type="access")
        assert user_id == "user123"

    def test_verify_token_valid_refresh(self):
        """Test verifying valid refresh token"""
        data = {"sub": "user123"}
        token = create_refresh_token(data)

        user_id = verify_token(token, token_type="refresh")
        assert user_id == "user123"

    def test_verify_token_invalid(self):
        """Test verifying invalid token"""
        with pytest.raises(Exception):  # Should raise HTTPException
            verify_token("invalid_token")

    def test_verify_token_wrong_type(self):
        """Test verifying token with wrong type"""
        data = {"sub": "user123"}
        token = create_access_token(data)  # Create access token

        with pytest.raises(Exception):  # Should raise HTTPException
            verify_token(token, token_type="refresh")  # Try to verify as refresh


class TestAuthenticationFunctions:
    """Test user authentication functions"""

    def test_authenticate_user_success(self, db_session, user_factory):
        """Test successful user authentication"""
        user = user_factory.create()
        db_session.commit()

        authenticated_user = authenticate_user(db_session, user.email, "testpassword123")
        assert authenticated_user is not None
        assert authenticated_user.id == user.id

    def test_authenticate_user_wrong_email(self, db_session):
        """Test authentication with wrong email"""
        authenticated_user = authenticate_user(db_session, "nonexistent@example.com", "testpassword123")
        assert authenticated_user is None

    def test_authenticate_user_wrong_password(self, db_session, user_factory):
        """Test authentication with wrong password"""
        user = user_factory.create()
        db_session.commit()

        authenticated_user = authenticate_user(db_session, user.email, "wrongpassword")
        assert authenticated_user is None


class TestAccountLocking:
    """Test account locking functionality"""

    def test_check_user_locked_not_locked(self, db_session, user_factory):
        """Test checking lock status for unlocked user"""
        user = user_factory.create(locked_until=None)
        db_session.commit()

        assert check_user_locked(user) is False

    def test_check_user_locked_future_lock(self, db_session, user_factory):
        """Test checking lock status for user locked in future"""
        future_time = datetime.utcnow() + timedelta(minutes=30)
        user = user_factory.create(locked_until=future_time)
        db_session.commit()

        assert check_user_locked(user) is True

    def test_check_user_locked_expired_lock(self, db_session, user_factory):
        """Test checking lock status for user with expired lock"""
        past_time = datetime.utcnow() - timedelta(minutes=30)
        user = user_factory.create(locked_until=past_time)
        db_session.commit()

        assert check_user_locked(user) is False

    def test_record_failed_login_first_attempt(self, db_session, user_factory):
        """Test recording first failed login attempt"""
        user = user_factory.create(failed_login_attempts=0, locked_until=None)
        db_session.commit()

        record_failed_login(db_session, user)
        db_session.refresh(user)

        assert user.failed_login_attempts == 1
        assert user.locked_until is None

    def test_record_failed_login_multiple_attempts(self, db_session, user_factory):
        """Test recording multiple failed login attempts"""
        user = user_factory.create(failed_login_attempts=4, locked_until=None)
        db_session.commit()

        record_failed_login(db_session, user)
        db_session.refresh(user)

        assert user.failed_login_attempts == 5
        assert user.locked_until is not None  # Should be locked

    def test_reset_failed_logins(self, db_session, user_factory):
        """Test resetting failed login attempts"""
        future_time = datetime.utcnow() + timedelta(minutes=30)
        user = user_factory.create(
            failed_login_attempts=3,
            locked_until=future_time,
            last_login=None
        )
        db_session.commit()

        reset_failed_logins(db_session, user)
        db_session.refresh(user)

        assert user.failed_login_attempts == 0
        assert user.locked_until is None
        assert user.last_login is not None


class TestTokenGeneration:
    """Test token generation functions"""

    def test_generate_verification_token(self):
        """Test verification token generation"""
        token1 = generate_verification_token()
        token2 = generate_verification_token()

        assert isinstance(token1, str)
        assert isinstance(token2, str)
        assert len(token1) > 0
        assert len(token2) > 0
        assert token1 != token2  # Should be unique

    def test_generate_reset_token(self):
        """Test reset token generation"""
        token1 = generate_reset_token()
        token2 = generate_reset_token()

        assert isinstance(token1, str)
        assert isinstance(token2, str)
        assert len(token1) > 0
        assert len(token2) > 0
        assert token1 != token2  # Should be unique
