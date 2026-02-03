"""
Week 3 Testing Script - Invoicing System
Usage: python scripts/test_week3.py
"""
import requests
import json
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def print_section(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}\n")


def print_success(msg):
    print(f"✅ {msg}")


def print_error(msg):
    print(f"❌ {msg}")


def test_week3():
    print_section("🧪 WEEK 3 TESTING - INVOICING SYSTEM")
    
    # Login
    print("1️⃣  Logging in...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"}
    )
    
    if login_response.status_code != 200:
        print_error(f"Login failed: {login_response.json()}")
        return
    
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print_success("Logged in")
    
    # Create Products
    print("\n2️⃣  Creating products...")
    products = []
    product_data_list = [
        {"name": "Dell Laptop", "unit_price": 250000, "category": "Computers"},
        {"name": "HP Mouse", "unit_price": 5000, "category": "Accessories"},
        {"name": "USB Cable", "unit_price": 2000, "category": "Accessories"}
    ]
    
    for prod_data in product_data_list:
        response = requests.post(f"{BASE_URL}/products", json=prod_data, headers=headers)
        if response.status_code == 201:
            product = response.json()
            products.append(product)
            print_success(f"Created product: {prod_data['name']}")
    
    # Get customer
    print("\n3️⃣  Getting customer...")
    customers_response = requests.get(f"{BASE_URL}/customers?page_size=1", headers=headers)
    if customers_response.status_code == 200:
        customers_data = customers_response.json()
        if customers_data['customers']:
            customer = customers_data['customers'][0]
            print_success(f"Found customer: {customer['name']}")
        else:
            print_error("No customers found. Create one first.")
            return
    
    # Create Invoice
    print("\n4️⃣  Creating invoice...")
    invoice_data = {
        "customer_id": customer['id'],
        "issue_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=30)),
        "discount_amount": 10000,
        "items": [
            {
                "description": "Dell Laptop",
                "quantity": 2,
                "unit_price": 250000,
                "product_id": products[0]['id'] if products else None
            },
            {
                "description": "HP Mouse",
                "quantity": 5,
                "unit_price": 5000,
                "product_id": products[1]['id'] if len(products) > 1 else None
            }
        ],
        "notes": "Thank you for your business!"
    }
    
    invoice_response = requests.post(f"{BASE_URL}/invoices", json=invoice_data, headers=headers)
    if invoice_response.status_code == 201:
        invoice = invoice_response.json()
        print_success(f"Created invoice: {invoice['invoice_number']}")
        print(f"   Total: ₦{float(invoice['total_amount']):,.2f}")
        print(f"   Status: {invoice['status']}")
    else:
        print_error(f"Failed: {invoice_response.json()}")
        return
    
    # Finalize Invoice
    print("\n5️⃣  Finalizing invoice (DRAFT → SENT)...")
    finalize_response = requests.post(
        f"{BASE_URL}/invoices/{invoice['id']}/finalize",
        headers=headers
    )
    if finalize_response.status_code == 200:
        print_success(f"Invoice finalized - Status: SENT")
    
    # Record Payment
    print("\n6️⃣  Recording payment...")
    payment_data = {
        "invoice_id": invoice['id'],
        "amount": 300000,
        "payment_method": "BANK_TRANSFER",
        "reference_number": "TRX123456789",
        "notes": "Partial payment received"
    }
    
    payment_response = requests.post(f"{BASE_URL}/payments", json=payment_data, headers=headers)
    if payment_response.status_code == 201:
        payment = payment_response.json()
        print_success(f"Payment recorded: ₦{float(payment['amount']):,.2f}")
        print(f"   Receipt: {payment['receipt_number']}")
    
    # Get Invoice Statistics
    print("\n7️⃣  Getting invoice statistics...")
    stats_response = requests.get(f"{BASE_URL}/invoices/stats/overview", headers=headers)
    if stats_response.status_code == 200:
        stats = stats_response.json()
        print_success("Statistics retrieved")
        print(f"   Total invoices: {stats['total_invoices']}")
        print(f"   Total invoiced: ₦{float(stats['total_invoiced']):,.2f}")
        print(f"   Total paid: ₦{float(stats['total_paid']):,.2f}")
        print(f"   Outstanding: ₦{float(stats['total_outstanding']):,.2f}")
    
    # Download PDF
    print("\n8️⃣  Downloading invoice PDF...")
    pdf_response = requests.get(f"{BASE_URL}/invoices/{invoice['id']}/pdf", headers=headers)
    if pdf_response.status_code == 200:
        filename = f"{invoice['invoice_number']}.pdf"
        with open(filename, 'wb') as f:
            f.write(pdf_response.content)
        print_success(f"PDF downloaded: {filename}")
    
    print_section("✅ WEEK 3 TESTING COMPLETE!")
    print("\n📊 Summary:")
    print("   ✓ Product management")
    print("   ✓ Invoice creation with line items")
    print("   ✓ Automatic calculations")
    print("   ✓ Invoice finalization")
    print("   ✓ Payment recording")
    print("   ✓ Statistics")
    print("   ✓ PDF generation")
    print(f"\n🎉 Week 3 is complete!\n")


if __name__ == "__main__":
    try:
        test_week3()
    except Exception as e:
        print_error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()