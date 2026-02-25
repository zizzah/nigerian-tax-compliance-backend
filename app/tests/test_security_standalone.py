"""
Security Function Tests - Standalone Version
Location: app/tests/test_security_standalone.py

Tests for core security functions including:
- Password hashing/verification
- Token generation/validation
- Authentication helpers
"""
import pytest
import os
import sys

# Set required environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-12345678901234567890")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("QSTASH_TOKEN", "test-qstash-token")
os.environ.setdefault("QSTASH_CURRENT_SIGNING_KEY", "test-signing-key")
os.environ.setdefault("QSTASH_NEXT_SIGNING_KEY", "test-next-signing-key")

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

# Import security functions directly
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    sanitize_input,
    validate_email
)


# ============================================================================
# Password Hashing Tests
# ============================================================================

class TestPasswordHashing:
    """Test password hashing and verification functions"""
    
    def test_password_hash_returns_string(self):
        """Test that password hash returns a non-empty string"""
        password = "Test@123"
        hashed = get_password_hash(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
    
    def test_password_hash_is_different_from_plain(self):
        """Test that hashed password is different from plain text"""
        password = "Test@123"
        hashed = get_password_hash(password)
        
        assert hashed != password
    
    def test_verify_correct_password(self):
        """Test verification with correct password"""
        password = "Secure@123"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_incorrect_password(self):
        """Test verification with incorrect password"""
        password = "Secure@123"
        wrong_password = "Wrong@123"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_verify_empty_password(self):
        """Test verification with empty password"""
        password = "Secure@123"
        hashed = get_password_hash(password)
        
        assert verify_password("", hashed) is False


# ============================================================================
# Token Generation Tests
# ============================================================================

class TestTokenGeneration:
    """Test JWT token generation and validation functions"""
    
    def test_create_access_token_returns_string(self):
        """Test that create_access_token returns a JWT string"""
        data = {"sub": "test-user-id", "email": "test@example.com"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_custom_expiry(self):
        """Test token creation with custom expiration"""
        data = {"sub": "test-user-id"}
        expires_delta = timedelta(hours=2)
        token = create_access_token(data, expires_delta)
        
        assert isinstance(token, str)
        
        # Decode and check expiration
        payload = decode_access_token(token)
        assert payload is not None
        assert "exp" in payload
    
    def test_decode_access_token_valid(self):
        """Test decoding a valid token"""
        data = {"sub": "test-user-id", "email": "test@example.com"}
        token = create_access_token(data)
        
        payload = decode_access_token(token)
        
        assert payload is not None
        assert payload["sub"] == "test-user-id"
        assert payload["email"] == "test@example.com"
    
    def test_decode_access_token_invalid(self):
        """Test decoding an invalid token"""
        payload = decode_access_token("invalid-token-string")
        
        assert payload is None
    
    def test_token_contains_expected_claims(self):
        """Test that token contains all expected claims"""
        data = {
            "sub": "user-123",
            "email": "user@example.com",
            "type": "access"
        }
        token = create_access_token(data)
        payload = decode_access_token(token)
        
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert payload["type"] == "access"
        assert "exp" in payload


# ============================================================================
# Input Sanitization Tests
# ============================================================================

class TestInputSanitization:
    """Test input sanitization functions"""
    
    def test_sanitize_input_normal_string(self):
        """Test sanitization of normal string"""
        value = "Hello World"
        result = sanitize_input(value)
        
        assert result == "Hello World"
    
    def test_sanitize_input_removes_dangerous_chars(self):
        """Test removal of dangerous characters"""
        value = "<script>alert('xss')</script>"
        result = sanitize_input(value)
        
        assert "<" not in result
        assert ">" not in result
    
    def test_sanitize_input_trims_whitespace(self):
        """Test whitespace trimming"""
        value = "  hello world  "
        result = sanitize_input(value)
        
        assert result == "hello world"
    
    def test_sanitize_input_empty_string(self):
        """Test sanitization of empty string"""
        result = sanitize_input("")
        
        assert result == ""


# ============================================================================
# Email Validation Tests
# ============================================================================

class TestEmailValidation:
    """Test email validation function"""
    
    def test_validate_email_valid_simple(self):
        """Test validation of simple valid email"""
        assert validate_email("user@example.com") is True
    
    def test_validate_email_valid_with_subdomain(self):
        """Test validation of email with subdomain"""
        assert validate_email("user@mail.example.com") is True
    
    def test_validate_email_invalid_no_at(self):
        """Test rejection of email without @"""
        assert validate_email("userexample.com") is False
    
    def test_validate_email_invalid_empty(self):
        """Test rejection of empty email"""
        assert validate_email("") is False
    
    def test_validate_email_invalid_none(self):
        """Test rejection of None email"""
        assert validate_email(None) is False # type: ignore


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
