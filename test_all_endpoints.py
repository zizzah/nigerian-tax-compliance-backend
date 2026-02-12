"""
Comprehensive API Endpoint Testing Script
==========================================

This script tests ALL endpoints before production deployment.

Run with: python test_all_endpoints.py

CRITICAL: Review all FAILED tests before going live!
"""

import requests
import json
import time
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
import uuid
from pathlib import Path


class Colors:
    """Terminal colors for output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class APITester:
    """Comprehensive API testing framework"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.business_id: Optional[str] = None
        self.customer_id: Optional[str] = None
        self.product_id: Optional[str] = None
        self.invoice_id: Optional[str] = None
        self.payment_id: Optional[str] = None
        self.document_id: Optional[str] = None
        
        self.test_results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        
    def print_header(self, text: str):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")
    
    def print_test(self, name: str, status: str, message: str = ""):
        """Print test result"""
        if status == "PASS":
            icon = "✓"
            color = Colors.GREEN
            self.passed += 1
        elif status == "FAIL":
            icon = "✗"
            color = Colors.RED
            self.failed += 1
        elif status == "WARN":
            icon = "⚠"
            color = Colors.YELLOW
            self.warnings += 1
        else:
            icon = "•"
            color = Colors.BLUE
        
        print(f"{color}{icon} {name}{Colors.END}")
        if message:
            print(f"  {message}")
        
        self.test_results.append({
            "name": name,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> requests.Response:
        """Make HTTP request with authentication"""
        url = f"{self.base_url}{endpoint}"
        
        headers = kwargs.get('headers', {})
        if self.access_token and 'Authorization' not in headers:
            headers['Authorization'] = f"Bearer {self.access_token}"
        kwargs['headers'] = headers
        
        return requests.request(method, url, **kwargs)
    
    # ========================================================================
    # SYSTEM HEALTH TESTS
    # ========================================================================
    
    def test_system_health(self):
        """Test system health endpoints"""
        self.print_header("SYSTEM HEALTH TESTS")
        
        # Test 1: Root endpoint
        try:
            resp = requests.get(f"{self.base_url}/")
            if resp.status_code == 200:
                self.print_test("Root endpoint", "PASS", f"Version: {resp.json().get('version')}")
            else:
                self.print_test("Root endpoint", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Root endpoint", "FAIL", str(e))
        
        # Test 2: Alive probe
        try:
            resp = requests.get(f"{self.base_url}/alive")
            if resp.status_code == 200:
                self.print_test("Liveness probe", "PASS")
            else:
                self.print_test("Liveness probe", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Liveness probe", "FAIL", str(e))
        
        # Test 3: Health check
        try:
            resp = requests.get(f"{self.base_url}/health")
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'healthy':
                    self.print_test("Health check", "PASS", "All systems healthy")
                else:
                    self.print_test("Health check", "WARN", "Some systems unhealthy")
            else:
                self.print_test("Health check", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Health check", "FAIL", str(e))
        
        # Test 4: Readiness probe
        try:
            resp = requests.get(f"{self.base_url}/ready")
            if resp.status_code == 200:
                self.print_test("Readiness probe", "PASS")
            else:
                self.print_test("Readiness probe", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Readiness probe", "FAIL", str(e))
    
    # ========================================================================
    # AUTHENTICATION TESTS
    # ========================================================================
    
    def test_authentication(self):
        """Test authentication endpoints"""
        self.print_header("AUTHENTICATION TESTS")
        
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPass123!"
        
        # Test 1: User registration
        try:
            resp = self.make_request('POST', '/api/v1/auth/register', json={
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
                "phone": "+2348012345678"
            })
            
            if resp.status_code == 201:
                data = resp.json()
                self.user_id = data.get('id')
                self.print_test("User registration", "PASS", f"User ID: {self.user_id}")
            else:
                self.print_test("User registration", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("User registration", "FAIL", str(e))
            return
        
        # Test 2: Login with correct credentials
        try:
            resp = self.make_request('POST', '/api/v1/auth/login', json={
                "email": test_email,
                "password": test_password
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get('access_token')
                self.print_test("Login (valid credentials)", "PASS", "Token received")
            else:
                self.print_test("Login (valid credentials)", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("Login (valid credentials)", "FAIL", str(e))
            return
        
        # Test 3: Login with wrong password
        try:
            resp = self.make_request('POST', '/api/v1/auth/login', json={
                "email": test_email,
                "password": "WrongPassword123!"
            })
            
            if resp.status_code == 401:
                self.print_test("Login (wrong password)", "PASS", "Correctly rejected")
            else:
                self.print_test("Login (wrong password)", "WARN", 
                              f"Expected 401, got {resp.status_code}")
        except Exception as e:
            self.print_test("Login (wrong password)", "FAIL", str(e))
        
        # Test 4: Login with missing fields
        try:
            resp = self.make_request('POST', '/api/v1/auth/login', json={
                "email": test_email
            })
            
            if resp.status_code == 422:
                self.print_test("Login (missing password)", "PASS", "Validation error returned")
            else:
                self.print_test("Login (missing password)", "WARN", 
                              f"Expected 422, got {resp.status_code}")
        except Exception as e:
            self.print_test("Login (missing password)", "FAIL", str(e))
        
        # Test 5: Protected endpoint without token
        try:
            # Temporarily clear token
            temp_token = self.access_token
            self.access_token = None
            
            resp = self.make_request('GET', '/api/v1/users/me')
            
            self.access_token = temp_token
            
            if resp.status_code == 401 or resp.status_code == 403:
                self.print_test("Protected endpoint (no token)", "PASS", "Correctly rejected")
            else:
                self.print_test("Protected endpoint (no token)", "FAIL", 
                              f"Expected 401/403, got {resp.status_code}")
        except Exception as e:
            self.print_test("Protected endpoint (no token)", "FAIL", str(e))
    
    # ========================================================================
    # USER MANAGEMENT TESTS
    # ========================================================================
    
    def test_user_management(self):
        """Test user management endpoints"""
        self.print_header("USER MANAGEMENT TESTS")
        
        # Test 1: Get current user profile
        try:
            resp = self.make_request('GET', '/api/v1/users/me')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get user profile", "PASS", f"Email: {data.get('email')}")
            else:
                self.print_test("Get user profile", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get user profile", "FAIL", str(e))
        
        # Test 2: Update user profile
        try:
            resp = self.make_request('PATCH', '/api/v1/users/me', json={
                "phone": "+2348098765432"
            })
            
            if resp.status_code == 200:
                self.print_test("Update user profile", "PASS")
            else:
                self.print_test("Update user profile", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Update user profile", "FAIL", str(e))
    
    # ========================================================================
    # BUSINESS PROFILE TESTS
    # ========================================================================
    
    def test_business_profile(self):
        """Test business profile endpoints"""
        self.print_header("BUSINESS PROFILE TESTS")
        
        # Test 1: Create business profile (or get existing)
        try:
            # First, try to get existing business
            resp = self.make_request('GET', '/api/v1/businesses/me')
            
            if resp.status_code == 200:
                # Business already exists
                data = resp.json()
                self.business_id = data.get('id')
                self.print_test("Get existing business profile", "PASS", 
                              f"Business ID: {self.business_id} (already exists)")
            else:
                # Create new business with unique TIN
                unique_tin = f"{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:4]}"
                resp = self.make_request('POST', '/api/v1/businesses/', json={
                    "business_name": "Test Business Ltd",
                    "business_type": "Limited Liability Company",
                    "industry": "Technology",
                    "tin": unique_tin,
                    "vat_registered": True,
                    "vat_number": f"VAT-{uuid.uuid4().hex[:6]}",
                    "phone": "+2348012345678",
                    "email": f"business_{uuid.uuid4().hex[:8]}@test.com",
                    "address": "123 Test Street",
                    "city": "Lagos",
                    "state": "Lagos"
                })
                
                if resp.status_code == 201:
                    data = resp.json()
                    self.business_id = data.get('id')
                    self.print_test("Create business profile", "PASS", 
                                  f"Business ID: {self.business_id}")
                elif resp.status_code == 400 and "already exists" in resp.text:
                    # User already has a business, get it
                    resp = self.make_request('GET', '/api/v1/businesses/me')
                    if resp.status_code == 200:
                        data = resp.json()
                        self.business_id = data.get('id')
                        self.print_test("Get business profile", "PASS", 
                                      f"Business ID: {self.business_id} (already exists)")
                    else:
                        self.print_test("Create business profile", "FAIL", 
                                      f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                        return
                else:
                    self.print_test("Create business profile", "FAIL", 
                                  f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                    return
        except Exception as e:
            self.print_test("Create business profile", "FAIL", str(e))
            return
        
        # Test 2: Get business profile
        try:
            resp = self.make_request('GET', '/api/v1/businesses/me')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get business profile", "PASS", 
                              f"Name: {data.get('business_name')}")
            else:
                self.print_test("Get business profile", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get business profile", "FAIL", str(e))
        
        # Test 3: Update business profile
        try:
            resp = self.make_request('PATCH', '/api/v1/businesses/me', json={
                "website": "https://testbusiness.com",
                "primary_color": "#1E40AF",
                "secondary_color": "#3B82F6"
            })
            
            if resp.status_code == 200:
                self.print_test("Update business profile", "PASS")
            else:
                self.print_test("Update business profile", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Update business profile", "FAIL", str(e))
        
        # Test 4: Get next invoice number
        try:
            resp = self.make_request('GET', '/api/v1/businesses/me/next-invoice-number')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get next invoice number", "PASS", 
                              f"Next: {data.get('next_invoice_number')}")
            else:
                self.print_test("Get next invoice number", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get next invoice number", "FAIL", str(e))
    
    # ========================================================================
    # CUSTOMER TESTS
    # ========================================================================
    
    def test_customers(self):
        """Test customer endpoints"""
        self.print_header("CUSTOMER MANAGEMENT TESTS")
        
        # Test 1: Create customer
        try:
            unique_email = f"customer_{uuid.uuid4().hex[:8]}@test.com"
            unique_tin = f"{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:4]}"
            
            resp = self.make_request('POST', '/api/v1/customers/', json={
                "name": "Test Customer Inc",
                "email": unique_email,
                "phone": "+2348012345678",
                "address": "456 Customer Street",
                "city": "Lagos",
                "state": "Lagos",
                "tin": unique_tin,
                "customer_type": "Business",
                "payment_terms_days": 30,
                "notes": "Test customer for API testing"
            })
            
            if resp.status_code == 201:
                data = resp.json()
                self.customer_id = data.get('id')
                self.print_test("Create customer", "PASS", f"Customer ID: {self.customer_id}")
            else:
                self.print_test("Create customer", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("Create customer", "FAIL", str(e))
            return
        
        # Test 2: List customers
        try:
            resp = self.make_request('GET', '/api/v1/customers/', params={
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("List customers", "PASS", 
                              f"Total: {data.get('total')}")
            else:
                self.print_test("List customers", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("List customers", "FAIL", str(e))
        
        # Test 3: Get specific customer
        try:
            resp = self.make_request('GET', f'/api/v1/customers/{self.customer_id}')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get customer", "PASS", f"Name: {data.get('name')}")
            else:
                self.print_test("Get customer", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get customer", "FAIL", str(e))
        
        # Test 4: Update customer
        try:
            resp = self.make_request('PATCH', f'/api/v1/customers/{self.customer_id}', json={
                "credit_limit": 1000000.00,
                "notes": "Updated notes"
            })
            
            if resp.status_code == 200:
                self.print_test("Update customer", "PASS")
            else:
                self.print_test("Update customer", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Update customer", "FAIL", str(e))
        
        # Test 5: Search customers
        try:
            resp = self.make_request('GET', '/api/v1/customers/', params={
                "search": "Test Customer",
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                self.print_test("Search customers", "PASS")
            else:
                self.print_test("Search customers", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Search customers", "FAIL", str(e))
        
        # Test 6: Get customer statistics
        try:
            resp = self.make_request('GET', '/api/v1/customers/stats/overview')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get customer statistics", "PASS", 
                              f"Total customers: {data.get('total_customers')}")
            else:
                self.print_test("Get customer statistics", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get customer statistics", "FAIL", str(e))
    
    # ========================================================================
    # PRODUCT TESTS
    # ========================================================================
    
    def test_products(self):
        """Test product endpoints"""
        self.print_header("PRODUCT MANAGEMENT TESTS")
        
        # Test 1: Create product
        try:
            resp = self.make_request('POST', '/api/v1/products/', json={
                "name": "Test Product",
                "description": "A test product for API testing",
                "unit_price": 50000.00,
                "cost_price": 30000.00,
                "tax_rate": 7.5,
                "is_taxable": True,
                "category": "Electronics",
                "track_inventory": True,
                "quantity_in_stock": 100,
                "low_stock_threshold": 10
            })
            
            if resp.status_code == 201:
                data = resp.json()
                self.product_id = data.get('id')
                self.print_test("Create product", "PASS", 
                              f"Product ID: {self.product_id}, SKU: {data.get('sku')}")
            else:
                self.print_test("Create product", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("Create product", "FAIL", str(e))
            return
        
        # Test 2: List products
        try:
            resp = self.make_request('GET', '/api/v1/products/', params={
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("List products", "PASS", f"Total: {data.get('total')}")
            else:
                self.print_test("List products", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("List products", "FAIL", str(e))
        
        # Test 3: Get specific product
        try:
            resp = self.make_request('GET', f'/api/v1/products/{self.product_id}')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get product", "PASS", f"Name: {data.get('name')}")
            else:
                self.print_test("Get product", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get product", "FAIL", str(e))
        
        # Test 4: Update product
        try:
            resp = self.make_request('PATCH', f'/api/v1/products/{self.product_id}', json={
                "unit_price": 55000.00,
                "quantity_in_stock": 95
            })
            
            if resp.status_code == 200:
                self.print_test("Update product", "PASS")
            else:
                self.print_test("Update product", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Update product", "FAIL", str(e))
        
        # Test 5: Search products
        try:
            resp = self.make_request('GET', '/api/v1/products/', params={
                "search": "Test Product",
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                self.print_test("Search products", "PASS")
            else:
                self.print_test("Search products", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Search products", "FAIL", str(e))
        
        # Test 6: Get product categories
        try:
            resp = self.make_request('GET', '/api/v1/products/categories/list')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get product categories", "PASS", 
                              f"Categories: {len(data.get('categories', []))}")
            else:
                self.print_test("Get product categories", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get product categories", "FAIL", str(e))
    
    # ========================================================================
    # INVOICE TESTS
    # ========================================================================
    
    def test_invoices(self):
        """Test invoice endpoints"""
        self.print_header("INVOICE MANAGEMENT TESTS")
        
        if not self.customer_id or not self.product_id:
            self.print_test("Invoice tests", "FAIL", 
                          "Missing customer_id or product_id. Run customer and product tests first.")
            return
        
        # Test 1: Create invoice
        try:
            issue_date = date.today()
            due_date = issue_date + timedelta(days=30)
            
            resp = self.make_request('POST', '/api/v1/invoices/', json={
                "customer_id": self.customer_id,
                "issue_date": issue_date.isoformat(),
                "due_date": due_date.isoformat(),
                "discount_amount": 0,
                "payment_terms": "Payment due within 30 days",
                "notes": "Test invoice created via API",
                "items": [
                    {
                        "product_id": self.product_id,
                        "description": "Test Product",
                        "quantity": 2,
                        "unit_price": 55000.00,
                        "discount_percent": 0,
                        "tax_rate": 7.5,
                        "sort_order": 0
                    }
                ]
            })
            
            if resp.status_code == 201:
                data = resp.json()
                self.invoice_id = data.get('id')
                self.print_test("Create invoice", "PASS", 
                              f"Invoice: {data.get('invoice_number')}, Total: ₦{data.get('total_amount')}")
            else:
                self.print_test("Create invoice", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("Create invoice", "FAIL", str(e))
            return
        
        # Test 2: List invoices
        try:
            resp = self.make_request('GET', '/api/v1/invoices/', params={
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("List invoices", "PASS", f"Total: {data.get('total')}")
            else:
                self.print_test("List invoices", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("List invoices", "FAIL", str(e))
        
        # Test 3: Get specific invoice
        try:
            resp = self.make_request('GET', f'/api/v1/invoices/{self.invoice_id}')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get invoice", "PASS", 
                              f"Number: {data.get('invoice_number')}")
            else:
                self.print_test("Get invoice", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get invoice", "FAIL", str(e))
        
        # Test 4: Update invoice
        try:
            resp = self.make_request('PATCH', f'/api/v1/invoices/{self.invoice_id}', json={
                "notes": "Updated invoice notes"
            })
            
            if resp.status_code == 200:
                self.print_test("Update invoice", "PASS")
            else:
                self.print_test("Update invoice", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Update invoice", "FAIL", str(e))
        
        # Test 5: Finalize invoice
        try:
            resp = self.make_request('POST', f'/api/v1/invoices/{self.invoice_id}/finalize')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Finalize invoice", "PASS", 
                              f"Status: {data.get('status')}")
            else:
                self.print_test("Finalize invoice", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Finalize invoice", "FAIL", str(e))
        
        # Test 6: Download invoice PDF
        try:
            resp = self.make_request('GET', f'/api/v1/invoices/{self.invoice_id}/pdf')
            
            if resp.status_code == 200:
                pdf_size = len(resp.content)
                self.print_test("Download invoice PDF", "PASS", 
                              f"PDF size: {pdf_size / 1024:.1f} KB")
            else:
                self.print_test("Download invoice PDF", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Download invoice PDF", "FAIL", str(e))
        
        # Test 7: Get invoice statistics
        try:
            resp = self.make_request('GET', '/api/v1/invoices/stats/overview')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get invoice statistics", "PASS", 
                              f"Total invoices: {data.get('total_invoices')}")
            else:
                self.print_test("Get invoice statistics", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get invoice statistics", "FAIL", str(e))
    
    # ========================================================================
    # PAYMENT TESTS
    # ========================================================================
    
    def test_payments(self):
        """Test payment endpoints"""
        self.print_header("PAYMENT MANAGEMENT TESTS")
        
        if not self.invoice_id:
            self.print_test("Payment tests", "FAIL", 
                          "Missing invoice_id. Run invoice tests first.")
            return
        
        # Test 1: Create payment
        try:
            resp = self.make_request('POST', '/api/v1/payments/', json={
                "invoice_id": self.invoice_id,
                "amount": 50000.00,
                "payment_date": date.today().isoformat(),
                "payment_method": "BANK_TRANSFER",
                "reference_number": "REF-12345",
                "transaction_id": "TXN-67890",
                "bank_name": "Test Bank",
                "notes": "Partial payment"
            })
            
            if resp.status_code == 201:
                data = resp.json()
                self.payment_id = data.get('id')
                self.print_test("Create payment", "PASS", 
                              f"Payment ID: {self.payment_id}, Receipt: {data.get('receipt_number')}")
            else:
                self.print_test("Create payment", "FAIL", 
                              f"Status: {resp.status_code}, Response: {resp.text[:200]}")
                return
        except Exception as e:
            self.print_test("Create payment", "FAIL", str(e))
            return
        
        # Test 2: List payments
        try:
            resp = self.make_request('GET', '/api/v1/payments/', params={
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("List payments", "PASS", f"Total: {data.get('total')}")
            else:
                self.print_test("List payments", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("List payments", "FAIL", str(e))
        
        # Test 3: Get specific payment
        try:
            resp = self.make_request('GET', f'/api/v1/payments/{self.payment_id}')
            
            if resp.status_code == 200:
                data = resp.json()
                self.print_test("Get payment", "PASS", 
                              f"Amount: ₦{data.get('amount')}")
            else:
                self.print_test("Get payment", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Get payment", "FAIL", str(e))
        
        # Test 4: Filter payments by invoice
        try:
            resp = self.make_request('GET', '/api/v1/payments/', params={
                "invoice_id": self.invoice_id,
                "page": 1,
                "page_size": 10
            })
            
            if resp.status_code == 200:
                self.print_test("Filter payments by invoice", "PASS")
            else:
                self.print_test("Filter payments by invoice", "FAIL", f"Status: {resp.status_code}")
        except Exception as e:
            self.print_test("Filter payments by invoice", "FAIL", str(e))
    
    # ========================================================================
    # SECURITY TESTS
    # ========================================================================
    
    def test_security(self):
        """Test security features"""
        self.print_header("SECURITY TESTS")
        
        # Test 1: Rate limiting (login endpoint)
        print(f"{Colors.BLUE}Testing rate limiting (this may take a few seconds)...{Colors.END}")
        rate_limit_triggered = False
        
        for i in range(10):  # Try 10 login attempts
            try:
                resp = self.make_request('POST', '/api/v1/auth/login', json={
                    "email": "nonexistent@test.com",
                    "password": "wrongpass"
                })
                
                if resp.status_code == 429:
                    rate_limit_triggered = True
                    break
                
                time.sleep(0.1)  # Small delay between requests
            except:
                pass
        
        if rate_limit_triggered:
            self.print_test("Rate limiting", "PASS", "Rate limit correctly enforced")
        else:
            self.print_test("Rate limiting", "WARN", 
                          "Rate limit not triggered in 10 attempts (may need adjustment)")
        
        # Test 2: XSS protection (input sanitization)
        try:
            xss_payload = "<script>alert('XSS')</script>"
            resp = self.make_request('POST', '/api/v1/customers/', json={
                "name": xss_payload,
                "email": "xss@test.com",
                "customer_type": "Individual",
                "payment_terms_days": 30
            })
            
            if resp.status_code in [201, 400, 422]:
                # Check if script tags were stripped in response
                if resp.status_code == 201:
                    data = resp.json()
                    if "<script>" not in data.get('name', ''):
                        self.print_test("XSS protection", "PASS", "Script tags stripped")
                        # Clean up
                        self.make_request('DELETE', f'/api/v1/customers/{data.get("id")}/permanent')
                    else:
                        self.print_test("XSS protection", "FAIL", 
                                      "Script tags NOT stripped from input")
                else:
                    self.print_test("XSS protection", "PASS", "Malicious input rejected")
            else:
                self.print_test("XSS protection", "WARN", f"Unexpected status: {resp.status_code}")
        except Exception as e:
            self.print_test("XSS protection", "FAIL", str(e))
        
        # Test 3: SQL injection protection
        try:
            sql_payload = "'; DROP TABLE users; --"
            resp = self.make_request('GET', '/api/v1/customers/', params={
                "search": sql_payload
            })
            
            if resp.status_code == 200:
                self.print_test("SQL injection protection", "PASS", 
                              "SQL injection attempt handled safely")
            else:
                self.print_test("SQL injection protection", "WARN", 
                              f"Unexpected response: {resp.status_code}")
        except Exception as e:
            self.print_test("SQL injection protection", "FAIL", str(e))
        
        # Test 4: Authorization (accessing other user's data)
        try:
            # Try to access a random UUID (simulating other user's data)
            fake_customer_id = str(uuid.uuid4())
            resp = self.make_request('GET', f'/api/v1/customers/{fake_customer_id}')
            
            if resp.status_code == 404:
                self.print_test("Authorization check", "PASS", 
                              "Cannot access non-existent/unauthorized resources")
            elif resp.status_code == 403:
                self.print_test("Authorization check", "PASS", 
                              "Correctly rejected unauthorized access")
            else:
                self.print_test("Authorization check", "WARN", 
                              f"Unexpected status: {resp.status_code}")
        except Exception as e:
            self.print_test("Authorization check", "FAIL", str(e))
    
    # ========================================================================
    # PERFORMANCE TESTS
    # ========================================================================
    
    def test_performance(self):
        """Test API performance"""
        self.print_header("PERFORMANCE TESTS")
        
        # Test 1: Response time for list endpoint
        try:
            start = time.time()
            resp = self.make_request('GET', '/api/v1/customers/', params={
                "page": 1,
                "page_size": 50
            })
            duration = time.time() - start
            
            if resp.status_code == 200:
                if duration < 1.0:
                    self.print_test("List endpoint response time", "PASS", 
                                  f"{duration*1000:.0f}ms (< 1s)")
                elif duration < 3.0:
                    self.print_test("List endpoint response time", "WARN", 
                                  f"{duration*1000:.0f}ms (acceptable but could be faster)")
                else:
                    self.print_test("List endpoint response time", "FAIL", 
                                  f"{duration*1000:.0f}ms (too slow for production)")
            else:
                self.print_test("List endpoint response time", "FAIL", 
                              f"Request failed: {resp.status_code}")
        except Exception as e:
            self.print_test("List endpoint response time", "FAIL", str(e))
        
        # Test 2: Database connection pool health
        try:
            resp = self.make_request('GET', '/health')
            
            if resp.status_code == 200:
                data = resp.json()
                db_status = data.get('checks', {}).get('database', {}).get('status')
                
                if db_status == 'healthy':
                    self.print_test("Database connection pool", "PASS", "Healthy")
                else:
                    self.print_test("Database connection pool", "WARN", 
                                  f"Status: {db_status}")
            else:
                self.print_test("Database connection pool", "FAIL", 
                              f"Health check failed: {resp.status_code}")
        except Exception as e:
            self.print_test("Database connection pool", "FAIL", str(e))
    
    # ========================================================================
    # DATA VALIDATION TESTS
    # ========================================================================
    
    def test_data_validation(self):
        """Test data validation"""
        self.print_header("DATA VALIDATION TESTS")
        
        # Test 1: Invalid email format
        try:
            resp = self.make_request('POST', '/api/v1/customers/', json={
                "name": "Test Customer",
                "email": "invalid-email",  # Invalid email
                "customer_type": "Individual",
                "payment_terms_days": 30
            })
            
            if resp.status_code == 422:
                self.print_test("Email validation", "PASS", "Invalid email rejected")
            else:
                self.print_test("Email validation", "FAIL", 
                              f"Invalid email accepted (status: {resp.status_code})")
        except Exception as e:
            self.print_test("Email validation", "FAIL", str(e))
        
        # Test 2: Negative price validation
        try:
            resp = self.make_request('POST', '/api/v1/products/', json={
                "name": "Invalid Product",
                "unit_price": -1000.00,  # Negative price
                "tax_rate": 7.5,
                "is_taxable": True
            })
            
            if resp.status_code == 422:
                self.print_test("Price validation", "PASS", "Negative price rejected")
            else:
                self.print_test("Price validation", "FAIL", 
                              f"Negative price accepted (status: {resp.status_code})")
        except Exception as e:
            self.print_test("Price validation", "FAIL", str(e))
        
        # Test 3: Required fields validation
        try:
            resp = self.make_request('POST', '/api/v1/customers/', json={
                # Missing required 'name' field
                "email": "test@example.com",
                "customer_type": "Individual"
            })
            
            if resp.status_code == 422:
                self.print_test("Required fields validation", "PASS", 
                              "Missing required field rejected")
            else:
                self.print_test("Required fields validation", "FAIL", 
                              f"Missing field accepted (status: {resp.status_code})")
        except Exception as e:
            self.print_test("Required fields validation", "FAIL", str(e))
    
    # ========================================================================
    # REPORT GENERATION
    # ========================================================================
    
    def generate_report(self):
        """Generate comprehensive test report"""
        self.print_header("TEST SUMMARY")
        
        total_tests = self.passed + self.failed + self.warnings
        pass_rate = (self.passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n{Colors.BOLD}Total Tests:{Colors.END} {total_tests}")
        print(f"{Colors.GREEN}✓ Passed:{Colors.END} {self.passed}")
        print(f"{Colors.RED}✗ Failed:{Colors.END} {self.failed}")
        print(f"{Colors.YELLOW}⚠ Warnings:{Colors.END} {self.warnings}")
        print(f"\n{Colors.BOLD}Pass Rate:{Colors.END} {pass_rate:.1f}%\n")
        
        # Production readiness assessment
        print(f"\n{Colors.BOLD}{Colors.CYAN}PRODUCTION READINESS ASSESSMENT{Colors.END}\n")
        
        if self.failed == 0 and self.warnings <= 2:
            status = f"{Colors.GREEN}READY FOR PRODUCTION{Colors.END}"
            recommendation = "All critical tests passed. Minor warnings are acceptable."
        elif self.failed == 0 and self.warnings <= 5:
            status = f"{Colors.YELLOW}CAUTION - REVIEW WARNINGS{Colors.END}"
            recommendation = "No critical failures, but review warnings before deployment."
        elif self.failed <= 3:
            status = f"{Colors.YELLOW}NOT READY - FIX FAILURES{Colors.END}"
            recommendation = "Fix all failed tests before production deployment."
        else:
            status = f"{Colors.RED}NOT READY - CRITICAL ISSUES{Colors.END}"
            recommendation = "Multiple critical failures detected. DO NOT DEPLOY."
        
        print(f"{Colors.BOLD}Status:{Colors.END} {status}")
        print(f"{Colors.BOLD}Recommendation:{Colors.END} {recommendation}\n")
        
        # Critical issues
        if self.failed > 0:
            print(f"{Colors.RED}{Colors.BOLD}CRITICAL ISSUES TO FIX:{Colors.END}\n")
            for result in self.test_results:
                if result['status'] == 'FAIL':
                    print(f"  ✗ {result['name']}")
                    if result['message']:
                        print(f"    → {result['message']}")
            print()
        
        # Warnings to review
        if self.warnings > 0:
            print(f"{Colors.YELLOW}{Colors.BOLD}WARNINGS TO REVIEW:{Colors.END}\n")
            for result in self.test_results:
                if result['status'] == 'WARN':
                    print(f"  ⚠ {result['name']}")
                    if result['message']:
                        print(f"    → {result['message']}")
            print()
        
        # Save detailed report
        report_file = f"api_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
                "pass_rate": pass_rate
            },
            "results": self.test_results
        }
        
        try:
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            print(f"{Colors.BOLD}Detailed report saved:{Colors.END} {report_file}\n")
        except Exception as e:
            print(f"{Colors.RED}Failed to save report: {e}{Colors.END}\n")
    
    # ========================================================================
    # MAIN TEST RUNNER
    # ========================================================================
    
    def run_all_tests(self):
        """Run all test suites"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}")
        print("=" * 80)
        print("COMPREHENSIVE API ENDPOINT TESTING".center(80))
        print("Nigerian Tax Compliance Platform".center(80))
        print("=" * 80)
        print(f"{Colors.END}\n")
        
        print(f"{Colors.BOLD}Base URL:{Colors.END} {self.base_url}")
        print(f"{Colors.BOLD}Start Time:{Colors.END} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Run test suites
        self.test_system_health()
        self.test_authentication()
        self.test_user_management()
        self.test_business_profile()
        self.test_customers()
        self.test_products()
        self.test_invoices()
        self.test_payments()
        self.test_security()
        self.test_performance()
        self.test_data_validation()
        
        # Generate report
        self.generate_report()
        
        print(f"{Colors.BOLD}End Time:{Colors.END} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Exit code based on results
        if self.failed > 0:
            sys.exit(1)
        else:
            sys.exit(0)


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test all API endpoints')
    parser.add_argument('--url', default='http://localhost:8000',
                       help='Base URL of the API (default: http://localhost:8000)')
    
    args = parser.parse_args()
    
    tester = APITester(base_url=args.url)
    tester.run_all_tests()


if __name__ == "__main__":
    main()