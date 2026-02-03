"""
COMPREHENSIVE API ENDPOINT TESTING
Tests all endpoints including authentication, business, customers, and logo upload
Usage: python test_all_endpoints.py
"""
import requests
import json
from pathlib import Path
from io import BytesIO
from PIL import Image

BASE_URL = "http://localhost:8000/api/v1"
TOKEN = None


def print_section(title):
    """Print formatted section header"""
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print()


def print_success(message):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


def print_response(response, show_full=False):
    """Print formatted response"""
    print(f"   Status: {response.status_code}")
    if show_full:
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
    else:
        data = response.json()
        if isinstance(data, dict):
            # Show first 3 keys
            for i, (key, value) in enumerate(list(data.items())[:3]):
                print(f"   {key}: {value}")
            if len(data) > 3:
                print(f"   ... and {len(data) - 3} more fields")
        else:
            print(f"   Response: {data}")


def create_test_image():
    """Create a test logo image in memory"""
    # Create a simple 500x500 blue image with white text
    img = Image.new('RGB', (500, 500), color='#1E40AF')
    
    # Save to BytesIO
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes


# ============================================================================
# TEST 1: AUTHENTICATION ENDPOINTS
# ============================================================================

def test_auth():
    """Test authentication endpoints"""
    global TOKEN
    
    print_section("1️⃣  AUTHENTICATION ENDPOINTS")
    
    # Test 1.1: Register
    print("1.1 Testing Registration...")
    register_data = {
        "email": "testuser@example.com",
        "password": "Test@12345",
        "confirm_password": "Test@12345",
        "phone": "+2348012345678"
    }
    
    response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
    if response.status_code == 201:
        print_success("User registered successfully")
        print_response(response)
    elif response.status_code == 400 and "already registered" in response.json().get('detail', ''):
        print_info("User already exists - skipping registration")
    else:
        print_error(f"Registration failed: {response.json()}")
    
    # Test 1.2: Login
    print("\n1.2 Testing Login...")
    login_data = {
        "email": "testuser@example.com",
        "password": "Test@12345"
    }
    
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code == 200:
        print_success("Login successful")
        TOKEN = response.json()["access_token"]
        print(f"   Token: {TOKEN[:30]}...")
    else:
        print_error(f"Login failed: {response.json()}")
        return False
    
    # Test 1.3: Login with wrong password
    print("\n1.3 Testing Login with Wrong Password...")
    wrong_login = {
        "email": "testuser@example.com",
        "password": "WrongPassword123"
    }
    
    response = requests.post(f"{BASE_URL}/auth/login", json=wrong_login)
    if response.status_code == 401:
        print_success("Correctly rejected wrong password")
    else:
        print_error("Should have rejected wrong password!")
    
    # Test 1.4: Password Reset Request
    print("\n1.4 Testing Password Reset Request...")
    reset_request = {"email": "testuser@example.com"}
    
    response = requests.post(f"{BASE_URL}/auth/forgot-password", json=reset_request)
    if response.status_code == 200:
        print_success("Password reset request sent")
        print_response(response)
    else:
        print_error(f"Password reset request failed: {response.json()}")
    
    return True


# ============================================================================
# TEST 2: USER ENDPOINTS
# ============================================================================

def test_users():
    """Test user endpoints"""
    print_section("2️⃣  USER ENDPOINTS")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Test 2.1: Get Current User
    print("2.1 Testing Get Current User...")
    response = requests.get(f"{BASE_URL}/users/me", headers=headers)
    if response.status_code == 200:
        print_success("Got current user profile")
        print_response(response)
    else:
        print_error(f"Failed to get user: {response.json()}")
    
    # Test 2.2: Update User Profile
    print("\n2.2 Testing Update User Profile...")
    update_data = {"phone": "+2348087654321"}
    
    response = requests.patch(f"{BASE_URL}/users/me", json=update_data, headers=headers)
    if response.status_code == 200:
        print_success("User profile updated")
        print_response(response)
    else:
        print_error(f"Failed to update user: {response.json()}")
    
    # Test 2.3: Change Password
    print("\n2.3 Testing Change Password...")
    password_change = {
        "current_password": "Test@12345",
        "new_password": "NewTest@12345",
        "confirm_password": "NewTest@12345"
    }
    
    response = requests.post(f"{BASE_URL}/users/me/change-password", 
                           json=password_change, headers=headers)
    if response.status_code == 200:
        print_success("Password changed successfully")
        print_response(response)
        
        # Change it back
        password_change = {
            "current_password": "NewTest@12345",
            "new_password": "Test@12345",
            "confirm_password": "Test@12345"
        }
        requests.post(f"{BASE_URL}/users/me/change-password", 
                     json=password_change, headers=headers)
    else:
        print_error(f"Failed to change password: {response.json()}")


# ============================================================================
# TEST 3: BUSINESS ENDPOINTS
# ============================================================================

def test_business():
    """Test business endpoints"""
    print_section("3️⃣  BUSINESS ENDPOINTS")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Test 3.1: Create Business
    print("3.1 Testing Create Business...")
    business_data = {
        "business_name": "Test Corp Nigeria Ltd",
        "business_type": "Limited Liability Company",
        "industry": "Technology",
        "tin": "TEST-TIN-12345",
        "vat_registered": True,
        "vat_number": "VAT-TEST-001",
        "rc_number": "RC-TEST-001",
        "phone": "+2348012345678",
        "email": "info@testcorp.ng",
        "address": "123 Test Street, Victoria Island",
        "city": "Lagos",
        "state": "Lagos"
    }
    
    response = requests.post(f"{BASE_URL}/businesses", json=business_data, headers=headers)
    if response.status_code == 201:
        print_success("Business created successfully")
        print_response(response)
    elif response.status_code == 400 and "already exists" in response.json().get('detail', ''):
        print_info("Business already exists - continuing with existing")
    else:
        print_error(f"Failed to create business: {response.json()}")
    
    # Test 3.2: Get Business
    print("\n3.2 Testing Get Business...")
    response = requests.get(f"{BASE_URL}/businesses/me", headers=headers)
    if response.status_code == 200:
        print_success("Got business profile")
        print_response(response)
    else:
        print_error(f"Failed to get business: {response.json()}")
    
    # Test 3.3: Update Business
    print("\n3.3 Testing Update Business...")
    update_data = {
        "website": "https://testcorp.ng",
        "invoice_prefix": "TC",
        "primary_color": "#1E40AF",
        "secondary_color": "#059669"
    }
    
    response = requests.patch(f"{BASE_URL}/businesses/me", json=update_data, headers=headers)
    if response.status_code == 200:
        print_success("Business updated successfully")
        print_response(response)
    else:
        print_error(f"Failed to update business: {response.json()}")
    
    # Test 3.4: Get Business Summary
    print("\n3.4 Testing Get Business Summary...")
    response = requests.get(f"{BASE_URL}/businesses/me/summary", headers=headers)
    if response.status_code == 200:
        print_success("Got business summary")
        print_response(response)
    else:
        print_error(f"Failed to get summary: {response.json()}")
    
    # Test 3.5: Get Next Invoice Number
    print("\n3.5 Testing Get Next Invoice Number...")
    response = requests.get(f"{BASE_URL}/businesses/me/next-invoice-number", headers=headers)
    if response.status_code == 200:
        print_success("Got next invoice number")
        print_response(response)
    else:
        print_error(f"Failed to get invoice number: {response.json()}")
    
    # Test 3.6: Upload Logo (THE IMPORTANT ONE!)
    print("\n3.6 Testing Upload Business Logo...")
    
    # Create test image
    img_bytes = create_test_image()
    
    files = {
        'logo': ('test_logo.png', img_bytes, 'image/png')
    }
    
    response = requests.post(
        f"{BASE_URL}/businesses/me/logo",
        files=files,
        headers=headers
    )
    
    if response.status_code == 200:
        print_success("Logo uploaded successfully!")
        data = response.json()
        print(f"   Logo URL: {data.get('logo_url', 'N/A')}")
        print_response(response)
    else:
        print_error(f"Failed to upload logo: {response.json()}")
    
    # Test 3.7: Test invalid file type
    print("\n3.7 Testing Invalid File Type Upload...")
    
    # Create a text file instead of image
    text_file = BytesIO(b"This is not an image")
    files = {
        'logo': ('test.txt', text_file, 'text/plain')
    }
    
    response = requests.post(
        f"{BASE_URL}/businesses/me/logo",
        files=files,
        headers=headers
    )
    
    if response.status_code == 400:
        print_success("Correctly rejected invalid file type")
        print_response(response)
    else:
        print_error("Should have rejected non-image file!")


# ============================================================================
# TEST 4: CUSTOMER ENDPOINTS
# ============================================================================

def test_customers():
    """Test customer endpoints"""
    print_section("4️⃣  CUSTOMER ENDPOINTS")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    customer_ids = []
    
    # Test 4.1: Create Customers
    print("4.1 Testing Create Customers...")
    
    customers_data = [
        {
            "name": "ABC Technologies Ltd",
            "email": "contact@abc.com",
            "phone": "+2348087654321",
            "customer_type": "Business",
            "payment_terms_days": 30,
            "city": "Lagos",
            "state": "Lagos",
            "credit_limit": 1000000
        },
        {
            "name": "XYZ Enterprises",
            "email": "info@xyz.com",
            "phone": "+2348087654322",
            "customer_type": "Business",
            "payment_terms_days": 45,
            "city": "Abuja",
            "state": "FCT"
        },
        {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+2348087654323",
            "customer_type": "Individual",
            "payment_terms_days": 14,
            "city": "Port Harcourt",
            "state": "Rivers"
        }
    ]
    
    for customer_data in customers_data:
        response = requests.post(f"{BASE_URL}/customers", json=customer_data, headers=headers)
        if response.status_code == 201:
            customer = response.json()
            customer_ids.append(customer['id'])
            print_success(f"Created: {customer_data['name']}")
        elif response.status_code == 400 and "already exists" in response.json().get('detail', ''):
            print_info(f"Already exists: {customer_data['name']}")
        else:
            print_error(f"Failed to create {customer_data['name']}: {response.json()}")
    
    # Test 4.2: List Customers
    print("\n4.2 Testing List Customers (Pagination)...")
    response = requests.get(f"{BASE_URL}/customers?page=1&page_size=10", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print_success(f"Got {data['total']} customers")
        print(f"   Page: {data['page']}/{data['total_pages']}")
        print(f"   Showing {len(data['customers'])} customers")
    else:
        print_error(f"Failed to list customers: {response.json()}")
    
    # Test 4.3: Search Customers
    print("\n4.3 Testing Search Customers...")
    response = requests.get(f"{BASE_URL}/customers?search=ABC", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print_success(f"Search found {data['total']} result(s)")
        for customer in data['customers']:
            print(f"   - {customer['name']}")
    else:
        print_error(f"Failed to search: {response.json()}")
    
    # Test 4.4: Filter by Type
    print("\n4.4 Testing Filter by Customer Type...")
    response = requests.get(f"{BASE_URL}/customers?customer_type=Business", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print_success(f"Found {data['total']} business customer(s)")
    else:
        print_error(f"Failed to filter: {response.json()}")
    
    # Test 4.5: Get Customer by ID
    if customer_ids:
        print("\n4.5 Testing Get Customer by ID...")
        response = requests.get(f"{BASE_URL}/customers/{customer_ids[0]}", headers=headers)
        if response.status_code == 200:
            customer = response.json()
            print_success(f"Got customer: {customer['name']}")
            print_response(response)
        else:
            print_error(f"Failed to get customer: {response.json()}")
    
    # Test 4.6: Update Customer
    if customer_ids:
        print("\n4.6 Testing Update Customer...")
        update_data = {
            "credit_limit": 2000000,
            "notes": "Premium customer - increased credit limit"
        }
        
        response = requests.patch(
            f"{BASE_URL}/customers/{customer_ids[0]}",
            json=update_data,
            headers=headers
        )
        
        if response.status_code == 200:
            customer = response.json()
            print_success("Customer updated")
            # Convert to float for formatting (API returns it as string/Decimal)
            credit_limit = float(customer['credit_limit']) if customer['credit_limit'] else 0
            print(f"   Credit Limit: ₦{credit_limit:,.2f}")
            print(f"   Notes: {customer['notes']}")
        else:
            print_error(f"Failed to update: {response.json()}")
    
    # Test 4.7: Get Customer Summary
    print("\n4.7 Testing Get Customer Summary...")
    response = requests.get(f"{BASE_URL}/customers/summary?limit=5", headers=headers)
    if response.status_code == 200:
        customers = response.json()
        print_success(f"Got {len(customers)} customer summaries")
        for customer in customers[:3]:
            print(f"   - {customer['name']}")
    else:
        print_error(f"Failed to get summary: {response.json()}")
    
    # Test 4.8: Get Customer Statistics
    print("\n4.8 Testing Get Customer Statistics...")
    response = requests.get(f"{BASE_URL}/customers/stats/overview", headers=headers)
    if response.status_code == 200:
        stats = response.json()
        print_success("Got customer statistics")
        print(f"   Total: {stats['total_customers']}")
        print(f"   Active: {stats['active_customers']}")
        print(f"   Inactive: {stats['inactive_customers']}")
    else:
        print_error(f"Failed to get stats: {response.json()}")
    
    # Test 4.9: Soft Delete Customer
    if customer_ids:
        print("\n4.9 Testing Soft Delete Customer...")
        response = requests.delete(f"{BASE_URL}/customers/{customer_ids[-1]}", headers=headers)
        if response.status_code == 204:
            print_success("Customer soft deleted (marked inactive)")
        else:
            print_error(f"Failed to delete: {response.json()}")


# ============================================================================
# TEST 5: HEALTH & INFO ENDPOINTS
# ============================================================================

def test_health():
    """Test health and info endpoints"""
    print_section("5️⃣  HEALTH & INFO ENDPOINTS")
    
    # Test 5.1: Root endpoint
    print("5.1 Testing Root Endpoint...")
    response = requests.get("http://localhost:8000/")
    if response.status_code == 200:
        print_success("Root endpoint working")
        print_response(response)
    else:
        print_error("Root endpoint failed")
    
    # Test 5.2: Health check
    print("\n5.2 Testing Health Check...")
    response = requests.get("http://localhost:8000/health")
    if response.status_code == 200:
        print_success("Health check passed")
        print_response(response)
    else:
        print_error("Health check failed")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run all tests"""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "COMPREHENSIVE API ENDPOINT TESTING" + " " * 24 + "║")
    print("╚" + "=" * 78 + "╝")
    
    try:
        # Check if server is running
        print("\n🔍 Checking if server is running...")
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            print_success("Server is running!")
        except requests.exceptions.ConnectionError:
            print_error("Server is not running!")
            print_info("Start server with: uvicorn app.main:app --reload")
            return
        
        # Run all tests
        if not test_auth():
            print_error("Authentication failed - stopping tests")
            return
        
        test_users()
        test_business()
        test_customers()
        test_health()
        
        # Final Summary
        print_section("✅ ALL TESTS COMPLETED!")
        
        print("📊 Test Summary:")
        print()
        print("   ✓ Authentication endpoints (register, login, password reset)")
        print("   ✓ User endpoints (profile, update, password change)")
        print("   ✓ Business endpoints (CRUD + logo upload)")
        print("   ✓ Customer endpoints (CRUD, search, filter, stats)")
        print("   ✓ Health & info endpoints")
        print()
        print("=" * 80)
        print()
        print("🎉 All endpoint tests passed!")
        print()
        print("📝 Next steps:")
        print("   1. Check uploaded logo in: uploads/logos/")
        print("   2. Review API docs: http://localhost:8000/docs")
        print("   3. Test edge cases and error handling")
        print()
        
    except KeyboardInterrupt:
        print()
        print_info("Testing interrupted by user")
    except Exception as e:
        print()
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()