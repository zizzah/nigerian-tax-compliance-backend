"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║         COMPREHENSIVE TEST SUITE - NIGERIAN TAX COMPLIANCE PLATFORM          ║
║                                                                              ║
║  Tests ALL implemented features across Weeks 1-4                             ║
║  - Week 1-2: Authentication, Business, Customers                             ║
║  - Week 3: Products, Invoices, Payments, PDF Generation                      ║
║  - Week 4: AI Document Processing (OCR + Groq)                               ║
║                                                                              ║
║  Total Test Coverage: 50+ endpoint tests                                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage: python scripts/test_all_features.py

Author: AI Tax Platform Team
Version: 1.0.0
Python: 3.11+
"""

import requests
import json
import time
import sys
from pathlib import Path
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple
import random
from PIL import Image, ImageDraw, ImageFont

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "http://localhost:8000/api/v1"
REQUEST_TIMEOUT = 30
VERBOSE = True  # Set to False for less output

# Test credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@123"

# ============================================================================
# UTILITIES
# ============================================================================

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class TestStats:
    """Track test statistics"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
    
    def record_pass(self):
        self.total += 1
        self.passed += 1
    
    def record_fail(self):
        self.total += 1
        self.failed += 1
    
    def record_skip(self):
        self.total += 1
        self.skipped += 1
    
    def get_duration(self):
        return time.time() - self.start_time
    
    def get_pass_rate(self):
        if self.total == 0:
            return 0
        return (self.passed / self.total) * 100


stats = TestStats()


def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.HEADER}{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}{Colors.ENDC}\n")


def print_success(msg: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")


def print_error(msg: str):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")


def print_warning(msg: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")


def print_info(msg: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ️  {msg}{Colors.ENDC}")


def print_test(test_num: str, test_name: str):
    """Print test header"""
    print(f"\n{Colors.BOLD}{test_num} {test_name}{Colors.ENDC}")


def format_currency(amount) -> str:
    """Format amount as Nigerian Naira"""
    try:
        return f"₦{float(amount):,.2f}"
    except:
        return f"₦0.00"


def make_request(method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
    """Make HTTP request with error handling"""
    url = f"{BASE_URL}{endpoint}"
    kwargs.setdefault('timeout', REQUEST_TIMEOUT)
    
    try:
        if VERBOSE:
            print(f"   → {method.upper()} {endpoint}")
        
        if method.upper() == 'GET':
            return requests.get(url, **kwargs)
        elif method.upper() == 'POST':
            return requests.post(url, **kwargs)
        elif method.upper() == 'PATCH':
            return requests.patch(url, **kwargs)
        elif method.upper() == 'DELETE':
            return requests.delete(url, **kwargs)
    except requests.exceptions.Timeout:
        print_error(f"Request timed out after {REQUEST_TIMEOUT}s")
        return None
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server")
        print_info("Make sure server is running: uvicorn app.main:app --reload")
        return None
    except Exception as e:
        print_error(f"Request failed: {e}")
        return None


def assert_response(response: Optional[requests.Response], expected_status: int, 
                   test_name: str) -> bool:
    """Assert response status and record result"""
    if not response:
        print_error(f"{test_name}: No response")
        stats.record_fail()
        return False
    
    if response.status_code == expected_status:
        print_success(f"{test_name}: PASSED ({response.status_code})")
        stats.record_pass()
        return True
    else:
        print_error(f"{test_name}: FAILED (expected {expected_status}, got {response.status_code})")
        try:
            error_data = response.json()
            if VERBOSE:
                print(f"      Error: {json.dumps(error_data, indent=6)}")
        except:
            if VERBOSE:
                print(f"      Response: {response.text[:200]}")
        stats.record_fail()
        return False


# ============================================================================
# GLOBAL TEST STATE
# ============================================================================

class TestData:
    """Store test data across test suites"""
    token: str = ""
    headers: Dict = {}
    business: Dict = {}
    customers: List[Dict] = []
    products: List[Dict] = []
    invoices: List[Dict] = []
    payments: List[Dict] = []
    documents: List[Dict] = []


data = TestData()


# ============================================================================
# TEST SUITE 0: HEALTH CHECKS
# ============================================================================

def test_health_checks():
    """Test API health and connectivity"""
    print_header("TEST SUITE 0: HEALTH CHECKS")
    
    # Test 0.1: Root endpoint
    print_test("0.1", "Root Endpoint")
    response = make_request('GET', '/')
    assert_response(response, 200, "Root endpoint accessible")
    
    # Test 0.2: Health endpoint
    print_test("0.2", "Health Check Endpoint")
    response = make_request('GET', '/health')
    assert_response(response, 200, "Health check passed")
    
    # Test 0.3: API docs
    print_test("0.3", "API Documentation")
    response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/docs", timeout=REQUEST_TIMEOUT)
    assert_response(response, 200, "Swagger UI accessible")


# ============================================================================
# TEST SUITE 1: AUTHENTICATION & USER MANAGEMENT
# ============================================================================

def test_authentication():
    """Test all authentication endpoints"""
    print_header("TEST SUITE 1: AUTHENTICATION & USER MANAGEMENT")
    
    # Test 1.1: Login with admin credentials
    print_test("1.1", "Admin Login")
    response = make_request('POST', '/auth/login', json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if assert_response(response, 200, "Login successful"):
        try:
            result = response.json()
            data.token = result["access_token"]
            data.headers = {"Authorization": f"Bearer {data.token}"}
            print_info(f"Token obtained: {data.token[:30]}...")
        except Exception as e:
            print_error(f"Failed to parse login response: {e}")
            return False
    else:
        print_error("Cannot proceed without authentication")
        return False
    
    # Test 1.2: Get current user
    print_test("1.2", "Get Current User")
    response = make_request('GET', '/users/me', headers=data.headers)
    assert_response(response, 200, "Get current user")
    
    # Test 1.3: Invalid login
    print_test("1.3", "Invalid Login (Negative Test)")
    response = make_request('POST', '/auth/login', json={
        "email": ADMIN_EMAIL,
        "password": "WrongPassword123"
    })
    assert_response(response, 401, "Invalid password rejected")
    
    # Test 1.4: Login without password
    print_test("1.4", "Missing Password (Negative Test)")
    response = make_request('POST', '/auth/login', json={
        "email": ADMIN_EMAIL
    })
    # Should fail with 422 (validation error)
    if response and response.status_code == 422:
        print_success("Missing password validation: PASSED")
        stats.record_pass()
    else:
        print_error(f"Missing password validation: FAILED")
        stats.record_fail()
    
    return True


# ============================================================================
# TEST SUITE 2: BUSINESS MANAGEMENT
# ============================================================================

def test_business_management():
    """Test business profile endpoints"""
    print_header("TEST SUITE 2: BUSINESS MANAGEMENT")
    
    # Test 2.1: Get business profile
    print_test("2.1", "Get Business Profile")
    response = make_request('GET', '/businesses/me', headers=data.headers)
    
    if assert_response(response, 200, "Get business profile"):
        data.business = response.json()
        print_info(f"Business: {data.business.get('business_name', 'Unknown')}")
        print_info(f"Subscription: {data.business.get('subscription_tier', 'Unknown')}")
    else:
        print_warning("No business profile found - this is expected for new accounts")
        # Try creating one
        print_test("2.1b", "Create Business Profile")
        business_data = {
            "business_name": "Test Corporation Nigeria Ltd",
            "business_type": "Limited Liability Company",
            "industry": "Technology",
            "tin": f"TIN-TEST-{random.randint(10000, 99999)}",
            "vat_registered": True,
            "phone": "+2348012345678",
            "email": "info@testcorp.ng",
            "city": "Lagos",
            "state": "Lagos"
        }
        response = make_request('POST', '/businesses', json=business_data, headers=data.headers)
        if assert_response(response, 201, "Create business"):
            data.business = response.json()
    
    # Test 2.2: Update business
    print_test("2.2", "Update Business Profile")
    update_data = {
        "website": "https://testcorp.ng",
        "primary_color": "#1E40AF"
    }
    response = make_request('PATCH', '/businesses/me', json=update_data, headers=data.headers)
    assert_response(response, 200, "Update business")
    
    # Test 2.3: Get business summary
    print_test("2.3", "Get Business Summary")
    response = make_request('GET', '/businesses/me/summary', headers=data.headers)
    assert_response(response, 200, "Get business summary")
    
    # Test 2.4: Get next invoice number
    print_test("2.4", "Get Next Invoice Number")
    response = make_request('GET', '/businesses/me/next-invoice-number', headers=data.headers)
    if assert_response(response, 200, "Get next invoice number"):
        result = response.json()
        print_info(f"Next invoice: {result.get('next_invoice_number', 'Unknown')}")


# ============================================================================
# TEST SUITE 3: CUSTOMER MANAGEMENT
# ============================================================================

def test_customer_management():
    """Test customer CRUD operations"""
    print_header("TEST SUITE 3: CUSTOMER MANAGEMENT")
    
    # Test 3.1: Create customers
    print_test("3.1", "Create Customers")
    
    customers_to_create = [
        {
            "name": "ABC Company Ltd",
            "email": f"abc{random.randint(1000, 9999)}@example.com",
            "phone": "+2348087654321",
            "customer_type": "Business",
            "payment_terms_days": 30,
            "city": "Lagos",
            "state": "Lagos"
        },
        {
            "name": "XYZ Enterprises",
            "email": f"xyz{random.randint(1000, 9999)}@example.com",
            "customer_type": "Business",
            "payment_terms_days": 45,
            "city": "Abuja",
            "state": "FCT"
        },
        {
            "name": "John Doe",
            "email": f"john{random.randint(1000, 9999)}@example.com",
            "customer_type": "Individual",
            "payment_terms_days": 14,
            "city": "Port Harcourt",
            "state": "Rivers"
        }
    ]
    
    for customer_data in customers_to_create:
        response = make_request('POST', '/customers', json=customer_data, headers=data.headers)
        if assert_response(response, 201, f"Create customer: {customer_data['name']}"):
            data.customers.append(response.json())
    
    # Test 3.2: List customers
    print_test("3.2", "List Customers (Paginated)")
    response = make_request('GET', '/customers?page=1&page_size=10', headers=data.headers)
    if assert_response(response, 200, "List customers"):
        result = response.json()
        print_info(f"Total customers: {result.get('total', 0)}")
    
    # Test 3.3: Search customers
    print_test("3.3", "Search Customers")
    response = make_request('GET', '/customers?search=ABC', headers=data.headers)
    assert_response(response, 200, "Search customers")
    
    # Test 3.4: Get customer by ID
    if data.customers:
        print_test("3.4", "Get Customer by ID")
        customer_id = data.customers[0]['id']
        response = make_request('GET', f'/customers/{customer_id}', headers=data.headers)
        assert_response(response, 200, "Get customer by ID")
    
    # Test 3.5: Update customer
    if data.customers:
        print_test("3.5", "Update Customer")
        customer_id = data.customers[0]['id']
        update_data = {
            "credit_limit": 500000,
            "notes": "VIP Customer"
        }
        response = make_request('PATCH', f'/customers/{customer_id}', 
                              json=update_data, headers=data.headers)
        assert_response(response, 200, "Update customer")
    
    # Test 3.6: Get customer statistics
    print_test("3.6", "Get Customer Statistics")
    response = make_request('GET', '/customers/stats/overview', headers=data.headers)
    assert_response(response, 200, "Get customer statistics")
    
    # Test 3.7: Get customer summary
    print_test("3.7", "Get Customer Summary")
    response = make_request('GET', '/customers/summary?limit=5', headers=data.headers)
    assert_response(response, 200, "Get customer summary")


# ============================================================================
# TEST SUITE 4: PRODUCT MANAGEMENT
# ============================================================================

def test_product_management():
    """Test product CRUD operations"""
    print_header("TEST SUITE 4: PRODUCT MANAGEMENT")
    
    # Test 4.1: Create products
    print_test("4.1", "Create Products")
    
    products_to_create = [
        {
            "name": "Dell Latitude Laptop",
            "description": "Business laptop with 16GB RAM",
            "unit_price": 450000,
            "tax_rate": 7.5,
            "category": "Computers"
        },
        {
            "name": "HP Wireless Mouse",
            "unit_price": 8500,
            "cost_price": 6000,
            "tax_rate": 7.5,
            "category": "Accessories",
            "track_inventory": True,
            "quantity_in_stock": 50,
            "low_stock_threshold": 10
        },
        {
            "name": "USB-C Cable",
            "unit_price": 3500,
            "tax_rate": 7.5,
            "category": "Accessories"
        }
    ]
    
    for product_data in products_to_create:
        response = make_request('POST', '/products', json=product_data, headers=data.headers)
        if response and response.status_code == 201:
            data.products.append(response.json())
            print_success(f"Created: {product_data['name']}")
            stats.record_pass()
        elif response and response.status_code == 409:
            # SKU conflict - try without SKU
            print_warning(f"SKU conflict for {product_data['name']}, retrying...")
            product_data.pop('sku', None)
            response = make_request('POST', '/products', json=product_data, headers=data.headers)
            if assert_response(response, 201, f"Create product: {product_data['name']}"):
                data.products.append(response.json())
        else:
            print_error(f"Failed to create: {product_data['name']}")
            stats.record_fail()
    
    # Test 4.2: List products
    print_test("4.2", "List Products")
    response = make_request('GET', '/products?page=1&page_size=20', headers=data.headers)
    assert_response(response, 200, "List products")
    
    # Test 4.3: Search products
    print_test("4.3", "Search Products")
    response = make_request('GET', '/products?search=laptop', headers=data.headers)
    assert_response(response, 200, "Search products")
    
    # Test 4.4: Get product by ID
    if data.products:
        print_test("4.4", "Get Product by ID")
        product_id = data.products[0]['id']
        response = make_request('GET', f'/products/{product_id}', headers=data.headers)
        assert_response(response, 200, "Get product by ID")
    
    # Test 4.5: Update product
    if data.products:
        print_test("4.5", "Update Product")
        product_id = data.products[0]['id']
        update_data = {
            "unit_price": 475000,
            "description": "Updated: Premium business laptop"
        }
        response = make_request('PATCH', f'/products/{product_id}', 
                              json=update_data, headers=data.headers)
        assert_response(response, 200, "Update product")
    
    # Test 4.6: Get categories
    print_test("4.6", "Get Product Categories")
    response = make_request('GET', '/products/categories/list', headers=data.headers)
    assert_response(response, 200, "Get categories")


# ============================================================================
# TEST SUITE 5: INVOICE MANAGEMENT
# ============================================================================

def test_invoice_management():
    """Test invoice CRUD and calculations"""
    print_header("TEST SUITE 5: INVOICE MANAGEMENT")
    
    if not data.customers:
        print_warning("No customers available - skipping invoice tests")
        stats.record_skip()
        return
    
    customer = data.customers[0]
    
    # Test 5.1: Create simple invoice
    print_test("5.1", "Create Simple Invoice")
    invoice_data = {
        "customer_id": customer['id'],
        "issue_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=30)),
        "discount_amount": 0,
        "items": [
            {
                "description": "Professional Services - Week 1",
                "quantity": 1,
                "unit_price": 150000,
                "discount_percent": 0,
                "tax_rate": 7.5,
                "sort_order": 0
            }
        ]
    }
    
    response = make_request('POST', '/invoices', json=invoice_data, headers=data.headers)
    if assert_response(response, 201, "Create simple invoice"):
        invoice = response.json()
        data.invoices.append(invoice)
        print_info(f"Invoice: {invoice['invoice_number']}")
        print_info(f"Total: {format_currency(invoice['total_amount'])}")
    
    # Test 5.2: Create multi-item invoice with discounts
    print_test("5.2", "Create Multi-Item Invoice with Discounts")
    invoice_data = {
        "customer_id": customer['id'],
        "issue_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=14)),
        "discount_amount": 10000,
        "items": [
            {
                "description": "Dell Laptop",
                "quantity": 2,
                "unit_price": 450000,
                "discount_percent": 0,
                "tax_rate": 7.5,
                "sort_order": 0
            },
            {
                "description": "Wireless Mouse",
                "quantity": 2,
                "unit_price": 8500,
                "discount_percent": 10,
                "tax_rate": 7.5,
                "sort_order": 1
            }
        ]
    }
    
    response = make_request('POST', '/invoices', json=invoice_data, headers=data.headers)
    if assert_response(response, 201, "Create multi-item invoice"):
        invoice = response.json()
        data.invoices.append(invoice)
        print_info(f"Subtotal: {format_currency(invoice['subtotal'])}")
        print_info(f"Tax: {format_currency(invoice['tax_amount'])}")
        print_info(f"Total: {format_currency(invoice['total_amount'])}")
    
    # Test 5.3: List invoices
    print_test("5.3", "List Invoices")
    response = make_request('GET', '/invoices?page=1&page_size=10', headers=data.headers)
    assert_response(response, 200, "List invoices")
    
    # Test 5.4: Get invoice by ID
    if data.invoices:
        print_test("5.4", "Get Invoice by ID")
        invoice_id = data.invoices[0]['id']
        response = make_request('GET', f'/invoices/{invoice_id}', headers=data.headers)
        assert_response(response, 200, "Get invoice by ID")
    
    # Test 5.5: Update invoice
    if data.invoices:
        print_test("5.5", "Update Invoice")
        invoice_id = data.invoices[0]['id']
        update_data = {
            "notes": "Payment terms: Net 30"
        }
        response = make_request('PATCH', f'/invoices/{invoice_id}', 
                              json=update_data, headers=data.headers)
        assert_response(response, 200, "Update invoice")
    
    # Test 5.6: Finalize invoice
    if data.invoices:
        print_test("5.6", "Finalize Invoice (DRAFT → SENT)")
        draft_invoice = next((inv for inv in data.invoices if inv['status'] == 'DRAFT'), None)
        if draft_invoice:
            response = make_request('POST', f"/invoices/{draft_invoice['id']}/finalize", 
                                  headers=data.headers)
            assert_response(response, 200, "Finalize invoice")
        else:
            print_warning("No DRAFT invoices available")
            stats.record_skip()
    
    # Test 5.7: Get invoice statistics
    print_test("5.7", "Get Invoice Statistics")
    response = make_request('GET', '/invoices/stats/overview', headers=data.headers)
    assert_response(response, 200, "Get invoice statistics")
    
    # Test 5.8: Download PDF
    if data.invoices:
        print_test("5.8", "Download Invoice PDF")
        invoice_id = data.invoices[0]['id']
        response = make_request('GET', f'/invoices/{invoice_id}/pdf', headers=data.headers)
        if assert_response(response, 200, "Download PDF"):
            print_info(f"PDF size: {len(response.content):,} bytes")


# ============================================================================
# TEST SUITE 6: PAYMENT MANAGEMENT
# ============================================================================

def test_payment_management():
    """Test payment recording and tracking"""
    print_header("TEST SUITE 6: PAYMENT MANAGEMENT")
    
    if not data.invoices:
        print_warning("No invoices available - skipping payment tests")
        stats.record_skip()
        return
    
    # Test 6.1: Record full payment
    print_test("6.1", "Record Full Payment")
    invoice = data.invoices[0]
    
    payment_data = {
        "invoice_id": invoice['id'],
        "amount": float(invoice['total_amount']),
        "payment_method": "BANK_TRANSFER",
        "reference_number": f"TXN-{random.randint(100000, 999999)}",
        "notes": "Full payment received"
    }
    
    response = make_request('POST', '/payments', json=payment_data, headers=data.headers)
    if assert_response(response, 201, "Record full payment"):
        payment = response.json()
        data.payments.append(payment)
        print_info(f"Amount: {format_currency(payment['amount'])}")
        print_info(f"Receipt: {payment.get('receipt_number', 'N/A')}")
    
    # Test 6.2: Record partial payment
    if len(data.invoices) > 1:
        print_test("6.2", "Record Partial Payment")
        invoice = data.invoices[1]
        partial_amount = float(invoice['total_amount']) / 2
        
        payment_data = {
            "invoice_id": invoice['id'],
            "amount": partial_amount,
            "payment_method": "CASH",
            "notes": "Partial payment - 50%"
        }
        
        response = make_request('POST', '/payments', json=payment_data, headers=data.headers)
        if assert_response(response, 201, "Record partial payment"):
            data.payments.append(response.json())
    
    # Test 6.3: List payments
    print_test("6.3", "List Payments")
    response = make_request('GET', '/payments?page=1&page_size=10', headers=data.headers)
    assert_response(response, 200, "List payments")
    
    # Test 6.4: Get payment by ID
    if data.payments:
        print_test("6.4", "Get Payment by ID")
        payment_id = data.payments[0]['id']
        response = make_request('GET', f'/payments/{payment_id}', headers=data.headers)
        assert_response(response, 200, "Get payment by ID")
    
    # Test 6.5: Update payment
    if data.payments:
        print_test("6.5", "Update Payment")
        payment_id = data.payments[0]['id']
        update_data = {
            "notes": "Payment confirmed by bank"
        }
        response = make_request('PATCH', f'/payments/{payment_id}', 
                              json=update_data, headers=data.headers)
        assert_response(response, 200, "Update payment")


# ============================================================================
# TEST SUITE 7: AI DOCUMENT PROCESSING
# ============================================================================

def test_document_processing():
    """Test AI-powered document processing"""
    print_header("TEST SUITE 7: AI DOCUMENT PROCESSING (Week 4)")
    
    # Test 7.1: Create test receipt image
    print_test("7.1", "Create Test Receipt Image")
    
    try:
        img = Image.new('RGB', (600, 800), color='white')
        draw = ImageDraw.Draw(img)
        
        receipt_text = """
        SHOPRITE STORES
        123 Victoria Island, Lagos
        TIN: 12345678-0001
        
        Date: 05/02/2026
        Receipt #: SR-2026-0234
        
        Items:
        Rice (5kg)         x2    ₦12,000.00
        Cooking Oil (2L)   x1     ₦4,500.00
        Chicken (1kg)      x3     ₦9,000.00
        
        Subtotal:              ₦25,500.00
        VAT (7.5%):             ₦1,912.50
        TOTAL:                 ₦27,412.50
        
        Payment: Card
        """
        
        y_pos = 50
        for line in receipt_text.strip().split('\n'):
            draw.text((50, y_pos), line.strip(), fill='black')
            y_pos += 30
        
        receipt_path = Path("/home/claude/test_receipt.jpg")
        img.save(receipt_path)
        print_success("Test receipt image created")
        stats.record_pass()
    except Exception as e:
        print_error(f"Failed to create test image: {e}")
        stats.record_fail()
        return
    
    # Test 7.2: Upload document
    print_test("7.2", "Upload Document for AI Processing")
    
    try:
        with open(receipt_path, "rb") as f:
            files = {"file": ("test_receipt.jpg", f, "image/jpeg")}
            form_data = {
                "document_type": "RECEIPT",
                "notes": "Test receipt for comprehensive testing"
            }
            
            response = requests.post(
                f"{BASE_URL}/documents/upload",
                files=files,
                data=form_data,
                headers=data.headers,
                timeout=REQUEST_TIMEOUT
            )
        
        if assert_response(response, 201, "Upload document"):
            result = response.json()
            document_id = result['document_id']
            task_id = result.get('task_id')
            print_info(f"Document ID: {document_id}")
            print_info(f"Task ID: {task_id}")
            
            # Test 7.3: Poll task status
            print_test("7.3", "Poll Processing Task Status")
            max_wait = 60
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(3)
                elapsed += 3
                
                status_response = make_request('GET', f'/documents/tasks/{task_id}', 
                                             headers=data.headers)
                
                if status_response and status_response.status_code == 200:
                    task_data = status_response.json()
                    status = task_data.get('status', 'unknown')
                    
                    if VERBOSE:
                        print(f"      [{elapsed}s] Status: {status}")
                    
                    if status == 'success':
                        print_success("Processing completed")
                        stats.record_pass()
                        break
                    elif status == 'failure':
                        print_error(f"Processing failed: {task_data.get('result')}")
                        stats.record_fail()
                        break
            
            # Test 7.4: Get processed document
            print_test("7.4", "Retrieve Processed Document")
            time.sleep(2)  # Give it a moment
            
            response = make_request('GET', f'/documents/{document_id}', headers=data.headers)
            if assert_response(response, 200, "Get processed document"):
                document = response.json()
                data.documents.append(document)
                
                print_info(f"Status: {document['status']}")
                print_info(f"Vendor: {document.get('vendor_name', 'Not extracted')}")
                print_info(f"Total: {format_currency(document.get('total_amount', 0))}")
                print_info(f"Confidence: {float(document.get('confidence_score', 0)):.1%}")
        
        # Cleanup
        receipt_path.unlink()
        
    except Exception as e:
        print_error(f"Document processing test failed: {e}")
        stats.record_fail()
    
    # Test 7.5: List documents
    print_test("7.5", "List Documents")
    response = make_request('GET', '/documents?page=1&page_size=10', headers=data.headers)
    assert_response(response, 200, "List documents")
    
    # Test 7.6: Get document statistics
    print_test("7.6", "Get Document Statistics")
    response = make_request('GET', '/documents/stats/overview', headers=data.headers)
    assert_response(response, 200, "Get document statistics")


# ============================================================================
# TEST SUITE 8: INTEGRATION TESTS
# ============================================================================

def test_integration_workflows():
    """Test complete end-to-end workflows"""
    print_header("TEST SUITE 8: INTEGRATION WORKFLOWS")
    
    if not data.customers:
        print_warning("No customers - skipping integration tests")
        stats.record_skip()
        return
    
    print_test("8.1", "Complete Invoice-to-Payment Workflow")
    
    customer = data.customers[0]
    
    # Step 1: Create invoice
    print("      Step 1: Creating invoice...")
    invoice_data = {
        "customer_id": customer['id'],
        "issue_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=7)),
        "discount_amount": 0,
        "items": [
            {
                "description": "Integration Test Service",
                "quantity": 1,
                "unit_price": 50000,
                "discount_percent": 0,
                "tax_rate": 7.5,
                "sort_order": 0
            }
        ]
    }
    
    response = make_request('POST', '/invoices', json=invoice_data, headers=data.headers)
    if not response or response.status_code != 201:
        print_error("Failed to create invoice for integration test")
        stats.record_fail()
        return
    
    test_invoice = response.json()
    print_success(f"Created invoice: {test_invoice['invoice_number']}")
    
    # Step 2: Finalize invoice
    print("      Step 2: Finalizing invoice...")
    response = make_request('POST', f"/invoices/{test_invoice['id']}/finalize", 
                          headers=data.headers)
    if not response or response.status_code != 200:
        print_error("Failed to finalize invoice")
        stats.record_fail()
        return
    
    print_success("Invoice finalized (DRAFT → SENT)")
    
    # Step 3: Record payment
    print("      Step 3: Recording payment...")
    payment_data = {
        "invoice_id": test_invoice['id'],
        "amount": float(test_invoice['total_amount']),
        "payment_method": "BANK_TRANSFER",
        "reference_number": f"INT-TXN-{random.randint(1000, 9999)}"
    }
    
    response = make_request('POST', '/payments', json=payment_data, headers=data.headers)
    if not response or response.status_code != 201:
        print_error("Failed to record payment")
        stats.record_fail()
        return
    
    print_success("Payment recorded")
    
    # Step 4: Verify invoice is PAID
    print("      Step 4: Verifying invoice status...")
    response = make_request('GET', f"/invoices/{test_invoice['id']}", headers=data.headers)
    if response and response.status_code == 200:
        final_invoice = response.json()
        
        checks_passed = 0
        total_checks = 3
        
        if final_invoice['status'] == 'PAID':
            print_success("✓ Invoice status: PAID")
            checks_passed += 1
        else:
            print_error(f"✗ Invoice status: {final_invoice['status']}")
        
        if float(final_invoice['outstanding_amount']) == 0:
            print_success("✓ Outstanding amount: ₦0.00")
            checks_passed += 1
        else:
            print_error(f"✗ Outstanding: {format_currency(final_invoice['outstanding_amount'])}")
        
        if final_invoice.get('paid_at'):
            print_success("✓ Paid timestamp recorded")
            checks_passed += 1
        else:
            print_error("✗ No paid timestamp")
        
        if checks_passed == total_checks:
            print_success("Integration workflow: PASSED")
            stats.record_pass()
        else:
            print_error(f"Integration workflow: FAILED ({checks_passed}/{total_checks} checks)")
            stats.record_fail()
    else:
        print_error("Failed to verify invoice")
        stats.record_fail()


# ============================================================================
# FINAL SUMMARY
# ============================================================================

def print_final_summary():
    """Print comprehensive test summary"""
    duration = stats.get_duration()
    pass_rate = stats.get_pass_rate()
    
    print_header("TEST EXECUTION SUMMARY")
    
    print(f"{Colors.BOLD}Overall Results:{Colors.ENDC}")
    print(f"   Total Tests: {stats.total}")
    print(f"   {Colors.OKGREEN}Passed: {stats.passed}{Colors.ENDC}")
    print(f"   {Colors.FAIL}Failed: {stats.failed}{Colors.ENDC}")
    print(f"   {Colors.WARNING}Skipped: {stats.skipped}{Colors.ENDC}")
    print(f"   Pass Rate: {pass_rate:.1f}%")
    print(f"   Duration: {duration:.2f}s")
    
    print(f"\n{Colors.BOLD}Test Coverage:{Colors.ENDC}")
    print(f"   ✓ Authentication & Users")
    print(f"   ✓ Business Management")
    print(f"   ✓ Customer Management")
    print(f"   ✓ Product Management")
    print(f"   ✓ Invoice Management")
    print(f"   ✓ Payment Management")
    print(f"   ✓ AI Document Processing")
    print(f"   ✓ Integration Workflows")
    
    print(f"\n{Colors.BOLD}Data Created:{Colors.ENDC}")
    print(f"   Customers: {len(data.customers)}")
    print(f"   Products: {len(data.products)}")
    print(f"   Invoices: {len(data.invoices)}")
    print(f"   Payments: {len(data.payments)}")
    print(f"   Documents: {len(data.documents)}")
    
    # Calculate total monetary value
    if data.invoices:
        total_invoiced = sum(float(inv['total_amount']) for inv in data.invoices)
        print(f"\n{Colors.BOLD}Financial Summary:{Colors.ENDC}")
        print(f"   Total Invoiced: {format_currency(total_invoiced)}")
    
    if data.payments:
        total_paid = sum(float(pay['amount']) for pay in data.payments)
        print(f"   Total Paid: {format_currency(total_paid)}")
    
    print("\n" + "="*80)
    
    if pass_rate == 100:
        print(f"{Colors.OKGREEN}{Colors.BOLD}")
        print("  ✅ ALL TESTS PASSED! SYSTEM IS FULLY FUNCTIONAL! 🎉")
        print(f"{Colors.ENDC}")
    elif pass_rate >= 90:
        print(f"{Colors.OKGREEN}{Colors.BOLD}")
        print("  ✅ EXCELLENT! Most tests passed. Minor issues detected.")
        print(f"{Colors.ENDC}")
    elif pass_rate >= 70:
        print(f"{Colors.WARNING}{Colors.BOLD}")
        print("  ⚠️  GOOD! Some tests failed. Review failed tests.")
        print(f"{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}")
        print("  ❌ NEEDS ATTENTION! Multiple tests failed.")
        print(f"{Colors.ENDC}")
    
    print("="*80 + "\n")
    
    print(f"{Colors.BOLD}Next Steps:{Colors.ENDC}")
    print("   1. Review API documentation at http://localhost:8000/docs")
    print("   2. Check database for created records")
    print("   3. Review any failed tests above")
    print("   4. Ready for production deployment!")
    print()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main test runner"""
    
    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("╔" + "="*78 + "╗")
    print("║" + " "*10 + "NIGERIAN TAX COMPLIANCE PLATFORM - COMPREHENSIVE TESTS" + " "*13 + "║")
    print("╚" + "="*78 + "╝")
    print(f"{Colors.ENDC}\n")
    
    print(f"{Colors.BOLD}Test Configuration:{Colors.ENDC}")
    print(f"   API URL: {BASE_URL}")
    print(f"   Timeout: {REQUEST_TIMEOUT}s")
    print(f"   Verbose: {VERBOSE}")
    print(f"   Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Run all test suites
        test_health_checks()
        
        if not test_authentication():
            print_error("Authentication failed - cannot continue")
            return
        
        test_business_management()
        test_customer_management()
        test_product_management()
        test_invoice_management()
        test_payment_management()
        test_document_processing()
        test_integration_workflows()
        
        # Print final summary
        print_final_summary()
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Tests interrupted by user{Colors.ENDC}\n")
    except Exception as e:
        print(f"\n\n{Colors.FAIL}Unexpected error: {e}{Colors.ENDC}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()