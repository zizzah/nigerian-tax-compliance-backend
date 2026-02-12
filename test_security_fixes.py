
"""
File: test_security_fixes.py (CREATE NEW)
"""

import pytest # type: ignore
from fastapi.testclient import TestClient # type: ignore
from app.main import app

client = TestClient(app)

def test_rate_limiting():
    """Test rate limiting works"""
    # Make 10 rapid login attempts
    for i in range(10):
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "wrong"
        })
        
        if i < 5:
            assert response.status_code in [401, 422]  # Normal errors
        else:
            assert response.status_code == 429  # Rate limited

def test_xss_prevention():
    """Test XSS is prevented"""
    # Try to inject script
    # (Requires auth - implement with proper test fixtures)
    pass

def test_security_headers():
    """Test security headers are present"""
    response = client.get("/")
    
    assert "X-Content-Type-Options" in response.headers
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"

def test_cors_strict():
    """Test CORS only allows configured origins"""
    # Try request from unauthorized origin
    response = client.get("/", headers={
        "Origin": "https://evil.com"
    })
    
    # Should not have CORS headers for evil origin
    assert "Access-Control-Allow-Origin" not in response.headers or \
           response.headers.get("Access-Control-Allow-Origin") != "https://evil.com"

