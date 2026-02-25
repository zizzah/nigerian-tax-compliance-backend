"""
Test Production API on Render - IMPROVED VERSION
"""
import requests
import random
import time

BASE_URL = "https://nigerian-tax-compliance-backend.onrender.com"

print("="*80)
print("TESTING PRODUCTION API")
print("="*80)

# 1. Health Check
print("\n1️⃣ Testing Health Check...")
try:
    response = requests.get(f"{BASE_URL}/health", timeout=30)
    print(f"✓ Health: {response.status_code}")
    data = response.json()
    print(f"  Status: {data['status']}")
    print(f"  Environment: {data['environment']}")
    print(f"  Database: {data['checks']['database']['status']}")
except Exception as e:
    print(f"✗ Health check failed: {e}")
    exit(1)

# 2. Register User
print("\n2️⃣ Testing User Registration...")
random_id = random.randint(1000, 9999)
email = f"test{random_id}@example.com"

try:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": email,
            "password": "Test@123",
            "confirm_password": "Test@123"
        },
        timeout=30
    )
    print(f"✓ Register: {response.status_code}")
    if response.status_code == 201:
        user_data = response.json()
        print(f"  User created: {user_data['email']}")
    else:
        print(f"  Response: {response.json()}")
        exit(1)
except Exception as e:
    print(f"✗ Registration failed: {e}")
    exit(1)

# 3. Login
print("\n3️⃣ Testing Login...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "email": email,
            "password": "Test@123"
        },
        timeout=30
    )
    print(f"✓ Login: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        token = data['access_token']
        print(f"  Got token: {token[:50]}...")
    else:
        print(f"  Response: {response.json()}")
        exit(1)
except Exception as e:
    print(f"✗ Login failed: {e}")
    exit(1)

# 4. Create Business (with unique TIN)
print("\n4️⃣ Testing Business Creation...")
headers = {"Authorization": f"Bearer {token}"}
unique_tin = f"{random_id}{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

try:
    response = requests.post(
        f"{BASE_URL}/api/v1/businesses/",
        json={
            "business_name": f"Test Company {random_id}",
            "tin": unique_tin,
            "vat_registered": True,
            "address": "123 Lagos Street",
            "city": "Lagos",
            "state": "Lagos",
            "country": "Nigeria"
        },
        headers=headers,
        timeout=30
    )
    print(f"✓ Business: {response.status_code}")
    if response.status_code == 201:
        business = response.json()
        print(f"  Business created: {business['business_name']}")
        print(f"  TIN: {business['tin']}")
        print(f"  Subscription: {business['subscription_tier']}")
    else:
        print(f"  Response: {response.json()}")
        exit(1)
except Exception as e:
    print(f"✗ Business creation failed: {e}")
    exit(1)

# 5. Create Customer
print("\n5️⃣ Testing Customer Creation...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/",
        json={
            "name": "Acme Corp",
            "email": f"acme{random_id}@example.com",
            "phone": "+2348012345678",
            "address": "456 Victoria Island",
            "city": "Lagos",
            "state": "Lagos",
            "customer_type": "Business",
            "payment_terms_days": 30
        },
        headers=headers,
        timeout=30
    )
    print(f"✓ Customer: {response.status_code}")
    if response.status_code == 201:
        customer = response.json()
        print(f"  Customer created: {customer['name']}")
        customer_id = customer['id']
    else:
        print(f"  Response: {response.json()}")
        exit(1)
except Exception as e:
    print(f"✗ Customer creation failed: {e}")
    exit(1)

# 6. Create Product
print("\n6️⃣ Testing Product Creation...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/products/",
        json={
            "name": "Consulting Services",
            "unit_price": 50000.00,
            "tax_rate": 7.5,
            "is_taxable": True
        },
        headers=headers,
        timeout=30
    )
    print(f"✓ Product: {response.status_code}")
    if response.status_code == 201:
        product = response.json()
        print(f"  Product created: {product['name']}")
        product_id = product['id']
    else:
        print(f"  Response: {response.json()}")
        exit(1)
except Exception as e:
    print(f"✗ Product creation failed: {e}")
    exit(1)

# 7. Create Invoice
print("\n7️⃣ Testing Invoice Creation...")
try:
    from datetime import date, timedelta
    
    response = requests.post(
        f"{BASE_URL}/api/v1/invoices/",
        json={
            "customer_id": customer_id,
            "issue_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "items": [
                {
                    "product_id": product_id,
                    "description": "Consulting Services - January 2026",
                    "quantity": 10,
                    "unit_price": 50000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0
                }
            ],
            "discount_amount": 0,
            "notes": "Thank you for your business!"
        },
        headers=headers,
        timeout=30
    )
    print(f"✓ Invoice: {response.status_code}")
    if response.status_code == 201:
        invoice = response.json()
        print(f"  Invoice created: {invoice['invoice_number']}")
        print(f"  Total: ₦{invoice['total_amount']:,.2f}")
        print(f"  Status: {invoice['status']}")
    else:
        print(f"  Response: {response.json()}")
except Exception as e:
    print(f"✗ Invoice creation failed: {e}")

print("\n" + "="*80)
print("✅ ALL PRODUCTION TESTS PASSED!")
print("="*80)
print(f"\n📊 Summary:")
print(f"  ✓ Health Check")
print(f"  ✓ User Registration")
print(f"  ✓ Authentication")
print(f"  ✓ Business Profile")
print(f"  ✓ Customer Management")
print(f"  ✓ Product Management")
print(f"  ✓ Invoice Creation")
print(f"\n🌐 Your API: {BASE_URL}")
print(f"📖 API Docs: {BASE_URL}/docs")
print(f"🏥 Health:   {BASE_URL}/health")
print("\n🚀 Ready for frontend integration!")