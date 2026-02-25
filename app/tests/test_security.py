"""
Security Function Tests
Location: app/tests/test_security.py

Tests for core security functions including:
- Password hashing/verification
- Token generation/validation
- Authentication helpers
"""
import pytest
from datetime import datetime, timedelta, timezone
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
    
    def test_password_hash_is_consistent(self):
        """Test that hashing the same password produces consistent results"""
        password = "Test@123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # bcrypt generates different salts, so hashes will differ
        # But both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)
    
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
    
    def test_verify_none_password(self):
        """Test verification with None password"""
        password = "Secure@123"
        hashed = get_password_hash(password)
        
        assert verify_password(None, hashed) is False # type: ignore


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
    
    def test_decode_access_token_expired(self):
        """Test decoding an expired token"""
        # Create a token that's already expired
        data = {"sub": "test-user-id"}
        expires_delta = timedelta(hours=-1)  # Already expired
        token = create_access_token(data, expires_delta)
        
        payload = decode_access_token(token)
        
        # decode_access_token should return None for expired tokens
        # (jwt.decode raises ExpiredSignatureError which is caught)
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
        assert "script" not in result
    
    def test_sanitize_input_removes_quotes(self):
        """Test removal of quote characters"""
        value = "He said \"hello\" and 'goodbye'"
        result = sanitize_input(value)
        
        assert '"' not in result
        assert "'" not in result
    
    def test_sanitize_input_removes_ampersand(self):
        """Test removal of ampersand"""
        value = "Tom & Jerry"
        result = sanitize_input(value)
        
        assert "&" not in result
    
    def test_sanitize_input_trims_whitespace(self):
        """Test whitespace trimming"""
        value = "  hello world  "
        result = sanitize_input(value)
        
        assert result == "hello world"
    
    def test_sanitize_input_max_length(self):
        """Test max length enforcement"""
        value = "a" * 300
        result = sanitize_input(value, max_length=255)
        
        assert len(result) == 255
    
    def test_sanitize_input_empty_string(self):
        """Test sanitization of empty string"""
        result = sanitize_input("")
        
        assert result == ""
    
    def test_sanitize_input_none(self):
        """Test sanitization of None"""
        result = sanitize_input(None) # type: ignore
        
        assert result == ""
    
    def test_sanitize_input_removes_null_bytes(self):
        """Test removal of null bytes"""
        value = "hello\x00world"
        result = sanitize_input(value)
        
        assert "\x00" not in result
        assert result == "helloworld"


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
    
    def test_validate_email_valid_with_plus(self):
        """Test validation of email with plus addressing"""
        assert validate_email("user+tag@example.com") is True
    
    def test_validate_email_valid_with_dot(self):
        """Test validation of email with dots in local part"""
        assert validate_email("first.last@example.com") is True
    
    def test_validate_email_invalid_no_at(self):
        """Test rejection of email without @"""
        assert validate_email("userexample.com") is False
    
    def test_validate_email_invalid_no_domain(self):
        """Test rejection of email without domain"""
        assert validate_email("user@") is False
    
    def test_validate_email_invalid_no_local(self):
        """Test rejection of email without local part"""
        assert validate_email("@example.com") is False
    
    def test_validate_email_invalid_empty(self):
        """Test rejection of empty email"""
        assert validate_email("") is False
    
    def test_validate_email_invalid_none(self):
        """Test rejection of None email"""
        assert validate_email(None) is False # type: ignore
    
    def test_validate_email_invalid_too_long(self):
        """Test rejection of overly long email"""
        long_email = "a" * 250 + "@example.com"
        assert validate_email(long_email) is False
    
    def test_validate_email_invalid_no_tld(self):
        """Test rejection of email without TLD"""
        assert validate_email("user@example") is False
