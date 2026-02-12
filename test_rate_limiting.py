"""
Rate Limiting Diagnostic Test
Tests rate limiting directly to see what's happening
"""

from fastapi.testclient import TestClient
import sys

# Try to import the app
try:
    from app.main import app
    print("✅ App imported successfully")
except Exception as e:
    print(f"❌ Failed to import app: {e}")
    sys.exit(1)

client = TestClient(app)

print("\n" + "="*70)
print("TESTING RATE LIMITING")
print("="*70)

# Test 1: Login rate limiting
print("\n1. Testing LOGIN endpoint rate limiting (5/minute limit)...")
print("-" * 70)
responses = []

for i in range(7):
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword123"
    })
    responses.append(response.status_code)
    print(f"   Attempt {i+1}: Status {response.status_code}")
    
    # Print response body for first failure
    if i == 0:
        print(f"   Response: {response.json()}")

print(f"\nResults: {responses}")
if 429 in responses:
    print("✅ Login rate limiting is working!")
else:
    print("❌ Login rate limiting NOT working")
    print(f"   Expected 429 somewhere in: {responses}")

# Test 2: Register rate limiting  
print("\n2. Testing REGISTER endpoint rate limiting (3/hour limit)...")
print("-" * 70)
responses = []

for i in range(5):
    response = client.post("/api/v1/auth/register", json={
        "email": f"unique_test_{i}@example.com",
        "password": "Password123!",
        "phone": "08012345678"
    })
    responses.append(response.status_code)
    print(f"   Attempt {i+1}: Status {response.status_code}")
    
    # Print response for debugging
    try:
        print(f"   Response: {response.json()}")
    except:
        print(f"   Response: {response.text[:100]}")

print(f"\nResults: {responses}")
if 429 in responses:
    print("✅ Register rate limiting is working!")
else:
    print("❌ Register rate limiting NOT working")
    print(f"   Expected 429 somewhere in: {responses}")

# Test 3: Check if limiter is properly attached
print("\n3. Checking app configuration...")
print("-" * 70)
print(f"   App type: {type(app)}")
print(f"   App state: {dir(app.state)}")

# Check for rate limiter in app
if hasattr(app.state, "_state"):
    print(f"   App state dict: {app.state._state}")

# Check middleware
print(f"   Middleware count: {len(app.user_middleware)}")
for i, middleware in enumerate(app.user_middleware):
    print(f"   Middleware {i}: {middleware}")

print("\n" + "="*70)
print("DIAGNOSTIC COMPLETE")
print("="*70)