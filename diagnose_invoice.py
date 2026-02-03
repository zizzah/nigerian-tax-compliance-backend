"""
Diagnostic Script for Invoice Creation Issues
This will help identify what's wrong with the invoice endpoint
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"


def diagnose():
    print("=" * 70)
    print("  INVOICE CREATION DIAGNOSTIC")
    print("=" * 70)
    print()
    
    # Login
    print("1. Logging in...")
    try:
        login_response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "admin@example.com", "password": "Admin@123"}
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Logged in successfully")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Check business exists
    print("\n2. Checking business profile...")
    try:
        business_response = requests.get(f"{BASE_URL}/businesses/me", headers=headers)
        if business_response.status_code == 200:
            business = business_response.json()
            print(f"✅ Business found: {business['business_name']}")
            print(f"   Invoice prefix: {business['invoice_prefix']}")
            print(f"   Invoice counter: {business['invoice_counter']}")
        else:
            print(f"❌ No business profile: {business_response.status_code}")
            print("   Create one first!")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Check customers exist
    print("\n3. Checking customers...")
    try:
        customers_response = requests.get(f"{BASE_URL}/customers?page_size=1", headers=headers)
        if customers_response.status_code == 200:
            customers_data = customers_response.json()
            if customers_data['customers']:
                customer = customers_data['customers'][0]
                print(f"✅ Customer found: {customer['name']}")
                print(f"   Customer ID: {customer['id']}")
            else:
                print("❌ No customers found")
                print("   Create customers first!")
                return
        else:
            print(f"❌ Failed to get customers: {customers_response.status_code}")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Check products exist
    print("\n4. Checking products...")
    try:
        products_response = requests.get(f"{BASE_URL}/products?page_size=5", headers=headers)
        if products_response.status_code == 200:
            products_data = products_response.json()
            if products_data['products']:
                print(f"✅ Found {len(products_data['products'])} product(s)")
                for prod in products_data['products'][:3]:
                    print(f"   - {prod['name']}: ₦{float(prod['unit_price']):,.2f}")
                product = products_data['products'][0]
            else:
                print("⚠️  No products found (optional)")
                product = None
        else:
            print(f"❌ Failed to get products: {products_response.status_code}")
            product = None
    except Exception as e:
        print(f"⚠️  Error getting products: {e}")
        product = None
    
    # Try minimal invoice creation
    print("\n5. Testing minimal invoice creation...")
    
    minimal_invoice = {
        "customer_id": customer['id'],
        "issue_date": "2026-02-03",
        "due_date": "2026-03-05",
        "discount_amount": 0,
        "items": [
            {
                "description": "Test Product",
                "quantity": 1,
                "unit_price": 10000,
                "discount_percent": 0,
                "tax_rate": 7.5,
                "sort_order": 0
            }
        ]
    }
    
    print(f"\nSending invoice data:")
    print(json.dumps(minimal_invoice, indent=2))
    print()
    
    try:
        invoice_response = requests.post(
            f"{BASE_URL}/invoices",
            json=minimal_invoice,
            headers=headers,
            timeout=10
        )
        
        print(f"Response status code: {invoice_response.status_code}")
        print(f"Response headers: {dict(invoice_response.headers)}")
        print()
        
        if invoice_response.status_code == 201:
            invoice = invoice_response.json()
            print("✅ Invoice created successfully!")
            print(f"   Invoice number: {invoice['invoice_number']}")
            print(f"   Total: ₦{float(invoice['total_amount']):,.2f}")
            print(f"   Status: {invoice['status']}")
        else:
            print(f"❌ Invoice creation failed")
            print(f"\nRaw response text:")
            print(invoice_response.text[:1000])  # First 1000 chars
            print()
            
            # Try to parse as JSON
            try:
                error_data = invoice_response.json()
                print("Error JSON:")
                print(json.dumps(error_data, indent=2))
            except:
                print("Response is not JSON")
                
    except requests.exceptions.Timeout:
        print("❌ Request timed out after 10 seconds")
        print("   Check server logs for errors")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 70)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print()
    print("If you see errors above, check:")
    print("1. Server logs for stack traces")
    print("2. Database migrations are up to date")
    print("3. All required fields are present")
    print("4. Relationships are properly configured")
    print()


if __name__ == "__main__":
    diagnose()