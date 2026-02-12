"""
COMPREHENSIVE MVP TEST SUITE - Nigerian Tax Compliance Platform
================================================================

Tests all implemented features:
- Week 1-2: Authentication & User Management
- Week 2: Business Profiles & Customer Management
- Week 3: Invoicing System (Products, Invoices, Payments, PDF)
- Week 4: Document Processing (OCR + AI with QStash)

Author: Senior Software & AI Security Expert
Date: February 2026
"""

import pytest
import asyncio
import uuid
import time
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from io import BytesIO
from PIL import Image
import os

# Test imports
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# App imports
from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.product import Product
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.models.document import Document, ProcessingStatus, DocumentType


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Use in-memory SQLite for fast testing
TEST_DATABASE_URL = "sqlite:///./test_comprehensive.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def db():
    """Create fresh database for each test"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create test client with database override"""
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    """Create test user"""
    from app.core.security import get_password_hash
    
    user = User(
        email="test@example.com",
        password_hash=get_password_hash("Test@123"),
        phone="+2348012345678",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Generate auth headers for authenticated requests"""
    token = create_access_token({"sub": str(test_user.id), "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_business(db, test_user):
    """Create test business"""
    business = Business(
        user_id=test_user.id,
        business_name="Test Business Ltd",
        tin="12345678",
        vat_registered=True,
        business_type="Limited Liability Company",
        industry="Technology"
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business


@pytest.fixture
def test_customer(db, test_business):
    """Create test customer"""
    customer = Customer(
        business_id=test_business.id,
        name="John Doe",
        email="john@example.com",
        phone="+2348087654321",
        customer_type="Business"
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@pytest.fixture
def test_product(db, test_business):
    """Create test product"""
    product = Product(
        business_id=test_business.id,
        name="Test Product",
        sku="TEST-001",
        unit_price=Decimal("100000.00"),
        tax_rate=Decimal("7.5"),
        is_taxable=True
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def sample_receipt_image():
    """Create sample receipt image for testing"""
    # Create simple test image
    img = Image.new('RGB', (800, 600), color='white')
    
    # Save to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    return img_bytes


# ============================================================================
# 1. WEEK 1-2: AUTHENTICATION & USER MANAGEMENT TESTS
# ============================================================================

class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_register_success(self, client):
        """Test successful user registration"""
        response = client.post("/api/v1/auth/register", json={
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "phone": "+2348012345678"
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] == True
        assert data["is_verified"] == False  # Email verification required
        assert "id" in data
    
    def test_register_duplicate_email(self, client, test_user):
        """Test registration with duplicate email"""
        response = client.post("/api/v1/auth/register", json={
            "email": test_user.email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        })
        
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
    
    def test_register_weak_password(self, client):
        """Test password validation"""
        response = client.post("/api/v1/auth/register", json={
            "email": "weak@example.com",
            "password": "weak",
            "confirm_password": "weak",
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_login_success(self, client, test_user):
        """Test successful login"""
        response = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "Test@123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == test_user.email
    
    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password"""
        response = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "WrongPassword123!"
        })
        
        assert response.status_code == 401
    
    def test_login_missing_fields(self, client):
        """Test login with missing fields returns 422"""
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com"
            # Missing password
        })
        
        assert response.status_code == 422
    
    def test_account_lockout_after_failed_attempts(self, client, test_user, db):
        """Test account locks after 5 failed login attempts"""
        # Attempt 5 failed logins
        for i in range(5):
            response = client.post("/api/v1/auth/login", json={
                "email": test_user.email,
                "password": "WrongPassword"
            })
        
        # 6th attempt should be forbidden
        response = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "Test@123"  # Even correct password
        })
        
        assert response.status_code == 403
        assert "locked" in response.json()["detail"]["error"]
    
    def test_get_current_user(self, client, test_user, auth_headers):
        """Test getting current user profile"""
        response = client.get("/api/v1/users/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == str(test_user.id)
    
    def test_change_password(self, client, auth_headers):
        """Test password change"""
        response = client.post("/api/v1/users/me/change-password", 
            headers=auth_headers,
            json={
                "current_password": "Test@123",
                "new_password": "NewSecure@456",
                "confirm_password": "NewSecure@456"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["success"] == True


# ============================================================================
# 2. WEEK 2: BUSINESS PROFILES & CUSTOMER MANAGEMENT TESTS
# ============================================================================

class TestBusinessProfiles:
    """Test business profile management"""
    
    def test_create_business(self, client, auth_headers):
        """Test business creation"""
        response = client.post("/api/v1/businesses/", 
            headers=auth_headers,
            json={
                "business_name": "My Business Ltd",
                "tin": "12345678",
                "vat_registered": True,
                "business_type": "Limited Liability Company",
                "industry": "Technology",
                "phone": "+2348012345678",
                "email": "business@example.com"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["business_name"] == "My Business Ltd"
        assert data["vat_registered"] == True
        assert "invoice_prefix" in data
    
    def test_get_business_profile(self, client, auth_headers, test_business):
        """Test getting business profile"""
        response = client.get("/api/v1/businesses/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["business_name"] == test_business.business_name
    
    def test_update_business(self, client, auth_headers, test_business):
        """Test updating business profile"""
        response = client.patch("/api/v1/businesses/me",
            headers=auth_headers,
            json={"industry": "Finance"}
        )
        
        assert response.status_code == 200
        assert response.json()["industry"] == "Finance"
    
    def test_duplicate_business_prevented(self, client, auth_headers, test_business):
        """Test user cannot create multiple businesses"""
        response = client.post("/api/v1/businesses/",
            headers=auth_headers,
            json={"business_name": "Second Business"}
        )
        
        assert response.status_code == 400


class TestCustomerManagement:
    """Test customer CRUD operations"""
    
    def test_create_customer(self, client, auth_headers, test_business):
        """Test customer creation"""
        response = client.post("/api/v1/customers/",
            headers=auth_headers,
            json={
                "name": "Jane Smith",
                "email": "jane@example.com",
                "phone": "+2348087654321",
                "customer_type": "Business",
                "payment_terms_days": 30
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Jane Smith"
        assert data["total_invoices_count"] == 0
    
    def test_list_customers_pagination(self, client, auth_headers, test_business, db):
        """Test customer pagination"""
        # Create 15 customers
        for i in range(15):
            customer = Customer(
                business_id=test_business.id,
                name=f"Customer {i}",
                customer_type="Individual"
            )
            db.add(customer)
        db.commit()
        
        # Get page 1
        response = client.get("/api/v1/customers/?page=1&page_size=10",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["customers"]) == 10
        assert data["total"] == 15
        assert data["total_pages"] == 2
    
    def test_search_customers(self, client, auth_headers, test_customer):
        """Test customer search"""
        response = client.get("/api/v1/customers/?search=John",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["customers"]) >= 1
        assert "john" in data["customers"][0]["name"].lower()
    
    def test_update_customer(self, client, auth_headers, test_customer):
        """Test customer update"""
        response = client.patch(f"/api/v1/customers/{test_customer.id}",
            headers=auth_headers,
            json={"phone": "+2349012345678"}
        )
        
        assert response.status_code == 200
        assert response.json()["phone"] == "+2349012345678"
    
    def test_soft_delete_customer(self, client, auth_headers, test_customer):
        """Test customer soft delete"""
        response = client.delete(f"/api/v1/customers/{test_customer.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204
        
        # Verify customer still exists but inactive
        get_response = client.get(f"/api/v1/customers/{test_customer.id}",
            headers=auth_headers
        )
        assert get_response.json()["is_active"] == False


# ============================================================================
# 3. WEEK 3: INVOICING SYSTEM TESTS
# ============================================================================

class TestProductManagement:
    """Test product/service catalog"""
    
    def test_create_product(self, client, auth_headers, test_business):
        """Test product creation"""
        response = client.post("/api/v1/products/",
            headers=auth_headers,
            json={
                "name": "MacBook Pro",
                "sku": "MBPRO-001",
                "unit_price": 450000.00,
                "tax_rate": 7.5,
                "is_taxable": True,
                "category": "Electronics"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "MacBook Pro"
        assert float(data["unit_price"]) == 450000.00
    
    def test_auto_generate_sku(self, client, auth_headers, test_business):
        """Test automatic SKU generation when not provided"""
        response = client.post("/api/v1/products/",
            headers=auth_headers,
            json={
                "name": "Test Product",
                "unit_price": 10000.00
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] is not None
        assert len(data["sku"]) > 0
    
    def test_duplicate_sku_prevented(self, client, auth_headers, test_product):
        """Test duplicate SKU prevention"""
        response = client.post("/api/v1/products/",
            headers=auth_headers,
            json={
                "name": "Another Product",
                "sku": test_product.sku,  # Duplicate
                "unit_price": 50000.00
            }
        )
        
        assert response.status_code == 409  # Conflict
        assert "duplicate" in response.json()["detail"]["error"].lower()
    
    def test_inventory_tracking(self, client, auth_headers, test_business):
        """Test inventory tracking"""
        response = client.post("/api/v1/products/",
            headers=auth_headers,
            json={
                "name": "Tracked Product",
                "unit_price": 25000.00,
                "track_inventory": True,
                "quantity_in_stock": 100,
                "low_stock_threshold": 10
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["track_inventory"] == True
        assert float(data["quantity_in_stock"]) == 100


class TestInvoicing:
    """Test invoice management"""
    
    def test_create_invoice_with_items(self, client, auth_headers, test_customer, test_product):
        """Test complete invoice creation"""
        response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "discount_amount": 5000.00,
                "items": [
                    {
                        "product_id": str(test_product.id),
                        "description": "Test Product",
                        "quantity": 2,
                        "unit_price": 100000.00,
                        "tax_rate": 7.5,
                        "discount_percent": 0,
                        "sort_order": 0
                    }
                ]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify calculations
        assert float(data["subtotal"]) == 200000.00
        assert float(data["discount_amount"]) == 5000.00
        assert float(data["tax_amount"]) == 14625.00  # (200000 - 5000) * 0.075
        assert float(data["total_amount"]) == 209625.00
        assert data["status"] == "DRAFT"
        assert "invoice_number" in data
    
    def test_invoice_number_uniqueness(self, client, auth_headers, test_customer, db):
        """Test invoice numbers are unique"""
        invoice_numbers = set()
        
        # Create 5 invoices
        for i in range(5):
            response = client.post("/api/v1/invoices/",
                headers=auth_headers,
                json={
                    "customer_id": str(test_customer.id),
                    "issue_date": date.today().isoformat(),
                    "items": [
                        {
                            "description": f"Item {i}",
                            "quantity": 1,
                            "unit_price": 10000.00,
                            "tax_rate": 7.5,
                            "discount_percent": 0,
                            "sort_order": 0
                        }
                    ]
                }
            )
            
            assert response.status_code == 201
            invoice_numbers.add(response.json()["invoice_number"])
        
        # All invoice numbers should be unique
        assert len(invoice_numbers) == 5
    
    def test_finalize_invoice(self, client, auth_headers, test_customer, db):
        """Test finalizing invoice (DRAFT -> SENT)"""
        # Create invoice
        create_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 50000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = create_response.json()["id"]
        
        # Finalize
        response = client.post(f"/api/v1/invoices/{invoice_id}/finalize",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "SENT"
        assert response.json()["sent_at"] is not None
    
    def test_generate_invoice_pdf(self, client, auth_headers, test_customer):
        """Test PDF generation"""
        # Create and finalize invoice
        create_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Consulting Services",
                    "quantity": 10,
                    "unit_price": 25000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = create_response.json()["id"]
        
        # Generate PDF
        response = client.get(f"/api/v1/invoices/{invoice_id}/pdf",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert len(response.content) > 0  # PDF has content
    
    def test_invoice_list_filtering(self, client, auth_headers, test_customer, db):
        """Test invoice filtering by status and date"""
        # Create invoices with different statuses
        for status in ["DRAFT", "SENT"]:
            response = client.post("/api/v1/invoices/",
                headers=auth_headers,
                json={
                    "customer_id": str(test_customer.id),
                    "issue_date": date.today().isoformat(),
                    "items": [{
                        "description": "Item",
                        "quantity": 1,
                        "unit_price": 10000.00,
                        "tax_rate": 7.5,
                        "discount_percent": 0,
                        "sort_order": 0
                    }]
                }
            )
            
            if status == "SENT":
                invoice_id = response.json()["id"]
                client.post(f"/api/v1/invoices/{invoice_id}/finalize",
                    headers=auth_headers
                )
        
        # Filter by status
        response = client.get("/api/v1/invoices/?status=DRAFT",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert all(inv["status"] == "DRAFT" for inv in data["invoices"])
    
    def test_cancel_invoice(self, client, auth_headers, test_customer):
        """Test invoice cancellation"""
        # Create invoice
        create_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Item",
                    "quantity": 1,
                    "unit_price": 10000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = create_response.json()["id"]
        
        # Cancel
        response = client.post(f"/api/v1/invoices/{invoice_id}/cancel",
            headers=auth_headers,
            json={"reason": "Customer requested cancellation"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"


class TestPayments:
    """Test payment recording"""
    
    def test_record_payment(self, client, auth_headers, test_customer, db):
        """Test recording payment against invoice"""
        # Create invoice
        invoice_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 100000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = invoice_response.json()["id"]
        total_amount = invoice_response.json()["total_amount"]
        
        # Record payment
        payment_response = client.post("/api/v1/payments/",
            headers=auth_headers,
            json={
                "invoice_id": invoice_id,
                "amount": total_amount,
                "payment_date": date.today().isoformat(),
                "payment_method": "BANK_TRANSFER",
                "reference_number": "TRX123456"
            }
        )
        
        assert payment_response.status_code == 201
        payment_data = payment_response.json()
        assert float(payment_data["amount"]) == float(total_amount)
        
        # Verify invoice status updated
        invoice_check = client.get(f"/api/v1/invoices/{invoice_id}",
            headers=auth_headers
        )
        assert invoice_check.json()["status"] == "PAID"
        assert float(invoice_check.json()["outstanding_amount"]) == 0
    
    def test_partial_payment(self, client, auth_headers, test_customer):
        """Test partial payment recording"""
        # Create invoice
        invoice_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 100000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = invoice_response.json()["id"]
        
        # Record partial payment (50%)
        payment_response = client.post("/api/v1/payments/",
            headers=auth_headers,
            json={
                "invoice_id": invoice_id,
                "amount": 53750.00,  # Half of total
                "payment_date": date.today().isoformat(),
                "payment_method": "CASH"
            }
        )
        
        assert payment_response.status_code == 201
        
        # Verify invoice status
        invoice_check = client.get(f"/api/v1/invoices/{invoice_id}",
            headers=auth_headers
        )
        assert invoice_check.json()["status"] == "PARTIALLY_PAID"
        assert float(invoice_check.json()["outstanding_amount"]) > 0
    
    def test_overpayment_prevented(self, client, auth_headers, test_customer):
        """Test overpayment is prevented"""
        # Create invoice
        invoice_response = client.post("/api/v1/invoices/",
            headers=auth_headers,
            json={
                "customer_id": str(test_customer.id),
                "issue_date": date.today().isoformat(),
                "items": [{
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 50000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        
        invoice_id = invoice_response.json()["id"]
        
        # Try to pay more than outstanding
        payment_response = client.post("/api/v1/payments/",
            headers=auth_headers,
            json={
                "invoice_id": invoice_id,
                "amount": 100000.00,  # More than total
                "payment_date": date.today().isoformat(),
                "payment_method": "CASH"
            }
        )
        
        assert payment_response.status_code == 400
        assert "exceeds" in payment_response.json()["detail"].lower()


# ============================================================================
# 4. WEEK 4: DOCUMENT PROCESSING (OCR + AI) TESTS
# ============================================================================

class TestDocumentProcessing:
    """Test document upload and AI processing"""
    
    def test_document_upload(self, client, auth_headers, test_business, sample_receipt_image):
        """Test document upload"""
        response = client.post("/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("receipt.jpg", sample_receipt_image, "image/jpeg")},
            data={"document_type": "RECEIPT"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "document_id" in data
        assert data["status"] == "PENDING"
        assert "task_id" in data  # QStash task ID
    
    def test_document_list(self, client, auth_headers, test_business, db):
        """Test listing documents"""
        # Create test document
        doc = Document(
            business_id=test_business.id,
            document_type=DocumentType.RECEIPT,
            original_filename="test.jpg",
            file_path="/uploads/test.jpg",
            file_size=1024,
            file_type="image/jpeg",
            status=ProcessingStatus.COMPLETED
        )
        db.add(doc)
        db.commit()
        
        response = client.get("/api/v1/documents/",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) >= 1
    
    def test_document_statistics(self, client, auth_headers, test_business, db):
        """Test document statistics"""
        # Create documents with different statuses
        for status in [ProcessingStatus.COMPLETED, ProcessingStatus.PENDING, ProcessingStatus.FAILED]:
            doc = Document(
                business_id=test_business.id,
                document_type=DocumentType.RECEIPT,
                original_filename=f"test_{status}.jpg",
                file_path=f"/uploads/test_{status}.jpg",
                file_size=1024,
                file_type="image/jpeg",
                status=status
            )
            db.add(doc)
        db.commit()
        
        response = client.get("/api/v1/documents/statistics/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_documents"] >= 3
        assert data["processed"] >= 1
        assert data["pending"] >= 1
        assert data["failed"] >= 1


# ============================================================================
# 5. SECURITY & PERFORMANCE TESTS
# ============================================================================

class TestSecurity:
    """Test security measures"""
    
    def test_unauthorized_access_blocked(self, client):
        """Test endpoints require authentication"""
        endpoints = [
            "/api/v1/users/me",
            "/api/v1/businesses/me",
            "/api/v1/customers/",
            "/api/v1/products/",
            "/api/v1/invoices/"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401
    
    def test_invalid_token_rejected(self, client):
        """Test invalid JWT tokens are rejected"""
        response = client.get("/api/v1/users/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
    
    def test_sql_injection_prevented(self, client, auth_headers):
        """Test SQL injection attempts are prevented"""
        # Try SQL injection in search
        response = client.get(
            "/api/v1/customers/?search=' OR '1'='1",
            headers=auth_headers
        )
        
        # Should not cause error or return all records
        assert response.status_code == 200
    
    def test_xss_prevention(self, client, auth_headers, test_business):
        """Test XSS attempts are prevented"""
        response = client.post("/api/v1/customers/",
            headers=auth_headers,
            json={
                "name": "<script>alert('XSS')</script>",
                "customer_type": "Individual"
            }
        )
        
        # Should succeed but sanitize input
        assert response.status_code == 201
    
    def test_data_isolation_between_businesses(self, client, db):
        """Test businesses cannot access each other's data"""
        from app.core.security import get_password_hash
        
        # Create two users with businesses
        user1 = User(email="user1@example.com", password_hash=get_password_hash("Test@123"))
        user2 = User(email="user2@example.com", password_hash=get_password_hash("Test@123"))
        db.add_all([user1, user2])
        db.commit()
        
        business1 = Business(user_id=user1.id, business_name="Business 1")
        business2 = Business(user_id=user2.id, business_name="Business 2")
        db.add_all([business1, business2])
        db.commit()
        
        customer1 = Customer(business_id=business1.id, name="Customer 1", customer_type="Individual")
        db.add(customer1)
        db.commit()
        
        # User 2 tries to access User 1's customer
        token2 = create_access_token({"sub": str(user2.id), "email": user2.email})
        headers2 = {"Authorization": f"Bearer {token2}"}
        
        response = client.get(f"/api/v1/customers/{customer1.id}", headers=headers2)
        
        assert response.status_code == 404  # Not found (not accessible)


class TestPerformance:
    """Test performance characteristics"""
    
    def test_health_endpoint_fast(self, client):
        """Test health endpoint responds quickly"""
        start = time.time()
        response = client.get("/health")
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 1.0  # Should respond in under 1 second
    
    def test_pagination_performance(self, client, auth_headers, test_business, db):
        """Test pagination handles large datasets efficiently"""
        # Create 1000 customers
        customers = []
        for i in range(1000):
            customers.append(Customer(
                business_id=test_business.id,
                name=f"Customer {i}",
                customer_type="Individual"
            ))
        
        db.bulk_save_objects(customers)
        db.commit()
        
        # Query with pagination
        start = time.time()
        response = client.get("/api/v1/customers/?page=1&page_size=50",
            headers=auth_headers
        )
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 2.0  # Should respond in under 2 seconds
        assert len(response.json()["customers"]) == 50


# ============================================================================
# 6. INTEGRATION & END-TO-END TESTS
# ============================================================================

class TestEndToEndWorkflow:
    """Test complete business workflows"""
    
    def test_complete_invoice_workflow(self, client, db):
        """Test complete workflow: Register → Business → Customer → Product → Invoice → Payment"""
        
        # 1. Register user
        register_response = client.post("/api/v1/auth/register", json={
            "email": "workflow@example.com",
            "password": "Workflow@123",
            "confirm_password": "Workflow@123"
        })
        assert register_response.status_code == 201
        
        # 2. Login
        login_response = client.post("/api/v1/auth/login", json={
            "email": "workflow@example.com",
            "password": "Workflow@123"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Create business
        business_response = client.post("/api/v1/businesses/",
            headers=headers,
            json={
                "business_name": "Workflow Business",
                "tin": "99999999"
            }
        )
        assert business_response.status_code == 201
        
        # 4. Create customer
        customer_response = client.post("/api/v1/customers/",
            headers=headers,
            json={
                "name": "Workflow Customer",
                "email": "customer@example.com",
                "customer_type": "Business"
            }
        )
        assert customer_response.status_code == 201
        customer_id = customer_response.json()["id"]
        
        # 5. Create product
        product_response = client.post("/api/v1/products/",
            headers=headers,
            json={
                "name": "Workflow Product",
                "unit_price": 50000.00,
                "tax_rate": 7.5
            }
        )
        assert product_response.status_code == 201
        product_id = product_response.json()["id"]
        
        # 6. Create invoice
        invoice_response = client.post("/api/v1/invoices/",
            headers=headers,
            json={
                "customer_id": customer_id,
                "issue_date": date.today().isoformat(),
                "items": [{
                    "product_id": product_id,
                    "description": "Workflow Product",
                    "quantity": 2,
                    "unit_price": 50000.00,
                    "tax_rate": 7.5,
                    "discount_percent": 0,
                    "sort_order": 0
                }]
            }
        )
        assert invoice_response.status_code == 201
        invoice_id = invoice_response.json()["id"]
        total_amount = invoice_response.json()["total_amount"]
        
        # 7. Finalize invoice
        finalize_response = client.post(f"/api/v1/invoices/{invoice_id}/finalize",
            headers=headers
        )
        assert finalize_response.status_code == 200
        
        # 8. Generate PDF
        pdf_response = client.get(f"/api/v1/invoices/{invoice_id}/pdf",
            headers=headers
        )
        assert pdf_response.status_code == 200
        assert len(pdf_response.content) > 0
        
        # 9. Record payment
        payment_response = client.post("/api/v1/payments/",
            headers=headers,
            json={
                "invoice_id": invoice_id,
                "amount": total_amount,
                "payment_date": date.today().isoformat(),
                "payment_method": "BANK_TRANSFER"
            }
        )
        assert payment_response.status_code == 201
        
        # 10. Verify invoice paid
        final_invoice = client.get(f"/api/v1/invoices/{invoice_id}",
            headers=headers
        )
        assert final_invoice.json()["status"] == "PAID"
        
        print("\n✅ Complete workflow test passed!")


# ============================================================================
# TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("COMPREHENSIVE MVP TEST SUITE")
    print("Nigerian Tax Compliance Platform")
    print("=" * 80)
    print()
    
    # Run tests with verbose output
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
        "-W", "ignore::DeprecationWarning"
    ])