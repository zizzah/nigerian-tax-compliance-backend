# 🇳🇬 Nigerian Tax Compliance Platform - Project Status & Handover Document

**Last Updated:** February 3, 2026  
**Project Status:** Week 2 Complete ✅  
**Next Phase:** Week 3 - Invoicing System

---

## 📊 Executive Summary

This document provides a complete overview of the Nigerian Tax Compliance Platform backend development progress. The project is being built in a phased approach over 8 weeks, with Weeks 1 and 2 now fully implemented and tested.

### Current Status
- ✅ **Week 1 Complete:** Authentication & User Management
- ✅ **Week 2 Complete:** Business Profiles & Customer Management
- 🔜 **Week 3 Next:** Invoicing System
- 📅 **Weeks 4-8:** Advanced Features

---

## 🏗️ Technology Stack

### Backend Framework
- **FastAPI** - Modern Python web framework
- **Python 3.12+** - Programming language
- **Uvicorn** - ASGI server

### Database
- **PostgreSQL** - Primary database
- **SQLAlchemy 2.0** - ORM (Object-Relational Mapping)
- **Alembic** - Database migrations

### Authentication & Security
- **JWT (JSON Web Tokens)** - Token-based authentication
- **Passlib + Bcrypt** - Password hashing
- **Python-Jose** - JWT encoding/decoding

### Validation & Serialization
- **Pydantic v2** - Data validation and settings management

### Development Tools
- **Git** - Version control
- **Virtual Environment (venv)** - Python dependency isolation

---

## 📁 Project Structure

```
nigerian-tax-compliance-backend/
├── app/
│   ├── main.py                      # FastAPI application entry point
│   ├── core/
│   │   ├── config.py                # Application settings
│   │   ├── database.py              # Database connection
│   │   ├── security.py              # Password hashing, JWT
│   │   └── dependencies.py          # Dependency injection
│   ├── models/
│   │   ├── __init__.py             # Model imports
│   │   ├── user.py                 # User model ✅
│   │   ├── business.py             # Business model ✅
│   │   └── customer.py             # Customer model ✅
│   ├── schemas/
│   │   ├── user.py                 # User schemas ✅
│   │   ├── auth.py                 # Auth schemas ✅
│   │   ├── business.py             # Business schemas ✅
│   │   └── customer.py             # Customer schemas ✅
│   └── api/
│       └── v1/
│           └── endpoints/
│               ├── auth.py          # Authentication endpoints ✅
│               ├── users.py         # User management ✅
│               ├── businesses.py    # Business endpoints ✅
│               └── customers.py     # Customer endpoints ✅
├── alembic/
│   ├── versions/                    # Migration files
│   └── env.py                       # Alembic configuration
├── scripts/
│   ├── create_admin.py             # Admin user creation script
│   ├── check_db.py                 # Database verification script
│   └── test_week2.py               # Week 2 testing script ✅
├── uploads/
│   └── logos/                       # Business logo storage
├── .env                             # Environment variables
├── requirements.txt                 # Python dependencies
└── README.md                        # Project documentation
```

---

## ✅ COMPLETED FEATURES

### Week 1: Authentication & User Management

#### 1. User Model & Database
- ✅ User table with UUID primary keys
- ✅ Email validation (unique constraint)
- ✅ Password hashing with bcrypt
- ✅ Account status tracking (active/inactive)
- ✅ Email verification system (structure in place)
- ✅ Password reset system (structure in place)
- ✅ Account locking after failed login attempts
- ✅ Role-based access (user/admin)
- ✅ Timestamps (created_at, updated_at)

#### 2. Authentication Endpoints
- ✅ `POST /api/v1/auth/register` - User registration
- ✅ `POST /api/v1/auth/login` - User login with JWT
- ✅ `POST /api/v1/auth/refresh` - Token refresh
- ✅ Password strength validation
- ✅ Failed login tracking
- ✅ JWT token generation and validation

#### 3. User Management Endpoints
- ✅ `GET /api/v1/users/me` - Get current user profile
- ✅ `PATCH /api/v1/users/me` - Update user profile
- ✅ `DELETE /api/v1/users/me` - Delete user account
- ✅ `POST /api/v1/users/change-password` - Change password
- ✅ Protected routes with JWT authentication

#### 4. Admin Features
- ✅ Admin user creation script
- ✅ Test user seeding
- ✅ Database verification script

---

### Week 2: Business Profiles & Customer Management

#### 1. Business Model & Features
- ✅ Business profile table
- ✅ One-to-one relationship with users (one business per user)
- ✅ Tax information (TIN, VAT, RC number)
- ✅ Contact details (phone, email, address, city, state)
- ✅ Branding (logo, primary color, secondary color)
- ✅ Invoice settings (prefix, counter)
- ✅ Subscription tiers (FREE, BASIC, PROFESSIONAL, ENTERPRISE)
- ✅ Monthly quotas (invoice quota, document quota)

#### 2. Business Endpoints
- ✅ `POST /api/v1/businesses` - Create business profile
- ✅ `GET /api/v1/businesses/me` - Get business profile
- ✅ `PATCH /api/v1/businesses/me` - Update business
- ✅ `DELETE /api/v1/businesses/me` - Delete business
- ✅ `GET /api/v1/businesses/me/summary` - Get business summary
- ✅ `POST /api/v1/businesses/me/logo` - Upload logo (PNG/JPG, max 5MB)
- ✅ `GET /api/v1/businesses/me/next-invoice-number` - Preview next invoice number

#### 3. Customer Model & Features
- ✅ Customer table with business relationship
- ✅ Basic info (name, email, phone)
- ✅ Address details (address, city, state, country)
- ✅ Tax information (TIN)
- ✅ Customer type (Individual/Business)
- ✅ Payment terms (default: 30 days)
- ✅ Credit limit tracking
- ✅ Auto-calculated analytics:
  - Total invoices count
  - Total invoiced amount
  - Total paid amount
  - Average payment days
  - Last invoice date
- ✅ Active/inactive status
- ✅ Notes field

#### 4. Customer Endpoints
- ✅ `POST /api/v1/customers` - Create customer
- ✅ `GET /api/v1/customers` - List customers (paginated)
  - Pagination (page, page_size)
  - Search (by name, email, phone)
  - Filter by customer type
  - Filter by active status
- ✅ `GET /api/v1/customers/summary` - Get lightweight customer list
- ✅ `GET /api/v1/customers/{id}` - Get customer by ID
- ✅ `PATCH /api/v1/customers/{id}` - Update customer
- ✅ `DELETE /api/v1/customers/{id}` - Soft delete (mark inactive)
- ✅ `DELETE /api/v1/customers/{id}/permanent` - Hard delete (with safety checks)
- ✅ `GET /api/v1/customers/stats/overview` - Customer statistics

#### 5. Multi-Tenant Architecture
- ✅ Business-scoped data isolation
- ✅ Users can only access their own business and customers
- ✅ Automatic business association on customer creation
- ✅ Data security through business_id filtering

---

## 🗄️ Database Schema

### Current Tables (3)

#### **users**
```sql
- id (UUID, PK)
- email (VARCHAR, UNIQUE, NOT NULL)
- hashed_password (VARCHAR, NOT NULL)
- full_name (VARCHAR)
- is_active (BOOLEAN, DEFAULT TRUE)
- is_admin (BOOLEAN, DEFAULT FALSE)
- email_verified (BOOLEAN, DEFAULT FALSE)
- failed_login_attempts (INTEGER, DEFAULT 0)
- account_locked_until (TIMESTAMP)
- last_login (TIMESTAMP)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

#### **businesses**
```sql
- id (UUID, PK)
- user_id (UUID, UNIQUE, FK -> users.id)
- business_name (VARCHAR, NOT NULL)
- business_type (VARCHAR)
- industry (VARCHAR)
- tin (VARCHAR, UNIQUE)
- vat_registered (BOOLEAN, DEFAULT FALSE)
- vat_number (VARCHAR)
- rc_number (VARCHAR)
- phone (VARCHAR)
- email (VARCHAR)
- website (VARCHAR)
- address (TEXT)
- city (VARCHAR)
- state (VARCHAR)
- country (VARCHAR, DEFAULT 'Nigeria')
- logo_url (VARCHAR)
- primary_color (VARCHAR, DEFAULT '#3B82F6')
- secondary_color (VARCHAR, DEFAULT '#10B981')
- invoice_prefix (VARCHAR, DEFAULT 'INV')
- invoice_counter (INTEGER, DEFAULT 1)
- subscription_tier (ENUM: FREE/BASIC/PROFESSIONAL/ENTERPRISE)
- monthly_invoice_quota (INTEGER, DEFAULT 10)
- monthly_document_quota (INTEGER, DEFAULT 20)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

#### **customers**
```sql
- id (UUID, PK)
- business_id (UUID, FK -> businesses.id)
- name (VARCHAR, NOT NULL)
- email (VARCHAR)
- phone (VARCHAR)
- address (TEXT)
- city (VARCHAR)
- state (VARCHAR)
- country (VARCHAR, DEFAULT 'Nigeria')
- tin (VARCHAR)
- total_invoices_count (INTEGER, DEFAULT 0)
- total_invoiced_amount (NUMERIC(15,2), DEFAULT 0)
- total_paid_amount (NUMERIC(15,2), DEFAULT 0)
- average_payment_days (INTEGER)
- last_invoice_date (DATE)
- customer_type (VARCHAR, DEFAULT 'Individual')
- credit_limit (NUMERIC(15,2))
- payment_terms_days (INTEGER, DEFAULT 30)
- is_active (BOOLEAN, DEFAULT TRUE)
- notes (TEXT)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

### Relationships
```
users (1) ───── (1) businesses
                     │
                     └───── (many) customers
```

---

## 🔐 Security Features Implemented

### Authentication
- ✅ JWT-based token authentication
- ✅ Access tokens with configurable expiration
- ✅ Refresh tokens for extended sessions
- ✅ Password hashing with bcrypt (cost factor: 12)
- ✅ Password strength requirements

### Authorization
- ✅ Protected routes (require valid JWT)
- ✅ Role-based access control (admin vs. user)
- ✅ Multi-tenant data isolation
- ✅ User can only access their own data

### Account Security
- ✅ Failed login attempt tracking
- ✅ Account locking after 5 failed attempts
- ✅ Automatic unlock after configurable time
- ✅ Email verification structure (ready for implementation)
- ✅ Password reset structure (ready for implementation)

### File Upload Security
- ✅ File type validation (images only)
- ✅ File size limits (5MB max)
- ✅ Unique filename generation (prevents overwrites)
- ✅ Sanitized file paths

---

## 📡 API Endpoints Summary

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication Endpoints (3)
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/auth/register` | Register new user | No |
| POST | `/auth/login` | Login and get JWT | No |
| POST | `/auth/refresh` | Refresh access token | Yes |

### User Endpoints (4)
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/users/me` | Get current user | Yes |
| PATCH | `/users/me` | Update user profile | Yes |
| DELETE | `/users/me` | Delete user account | Yes |
| POST | `/users/change-password` | Change password | Yes |

### Business Endpoints (7)
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/businesses` | Create business | Yes |
| GET | `/businesses/me` | Get business | Yes |
| PATCH | `/businesses/me` | Update business | Yes |
| DELETE | `/businesses/me` | Delete business | Yes |
| GET | `/businesses/me/summary` | Get summary | Yes |
| POST | `/businesses/me/logo` | Upload logo | Yes |
| GET | `/businesses/me/next-invoice-number` | Preview invoice # | Yes |

### Customer Endpoints (8)
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/customers` | Create customer | Yes |
| GET | `/customers` | List customers (paginated) | Yes |
| GET | `/customers/summary` | Get summaries | Yes |
| GET | `/customers/{id}` | Get by ID | Yes |
| PATCH | `/customers/{id}` | Update customer | Yes |
| DELETE | `/customers/{id}` | Soft delete | Yes |
| DELETE | `/customers/{id}/permanent` | Hard delete | Yes |
| GET | `/customers/stats/overview` | Get statistics | Yes |

**Total Endpoints:** 22

---

## 🧪 Testing Status

### Automated Tests
- ✅ Week 1 auth flow tested
- ✅ Week 2 business & customer CRUD tested
- ✅ Pagination tested
- ✅ Search/filter tested
- ✅ Statistics tested
- ✅ All endpoints returning correct status codes
- ✅ Data validation working
- ✅ Multi-tenant isolation verified

### Test Script
```bash
# Run comprehensive test suite
python scripts/test_week2.py
```

### Manual Testing
- ✅ Swagger UI documentation functional
- ✅ All endpoints accessible at `/docs`
- ✅ Request/response schemas validated
- ✅ Error handling tested
- ✅ Edge cases tested (duplicates, invalid data, etc.)

---

## 🔧 Configuration

### Environment Variables (.env)
```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application
APP_NAME=Nigerian Tax Compliance Platform
APP_VERSION=1.0.0
DEBUG=True
API_V1_PREFIX=/api/v1

# CORS
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]

# File Upload
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=5

# Nigerian Tax Settings
NIGERIAN_VAT_RATE=7.5
VAT_REGISTRATION_THRESHOLD=25000000
```

### Dependencies (requirements.txt)
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
alembic==1.12.1
psycopg2-binary==2.9.9
pydantic==2.5.0
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
email-validator==2.1.0
```

---

## 🚀 NEXT PHASE: Week 3 - Invoicing System

### Overview
Build a comprehensive invoicing system with automatic calculations, PDF generation, and payment tracking.

### Features to Implement

#### 1. Invoice Model (Day 11-12)
- [ ] Create Invoice table
  - Invoice metadata (number, date, due date, status)
  - Customer relationship (FK to customers)
  - Business relationship (FK to businesses)
  - Financial totals (subtotal, tax, total)
  - Payment information
  - Notes and terms

- [ ] Create InvoiceItem table
  - Line items for each invoice
  - Product/service description
  - Quantity, unit price
  - Discount
  - Tax rate
  - Line total calculation

- [ ] Invoice Status Enum
  - DRAFT
  - SENT
  - PAID
  - OVERDUE
  - CANCELLED

#### 2. Product/Service Catalog (Day 12)
- [ ] Create Product table
  - Product/service name
  - Description
  - Unit price
  - Tax rate
  - Active status
  - Business relationship

#### 3. Invoice Endpoints (Day 13)
- [ ] `POST /api/v1/invoices` - Create invoice
- [ ] `GET /api/v1/invoices` - List invoices (paginated)
- [ ] `GET /api/v1/invoices/{id}` - Get invoice by ID
- [ ] `PATCH /api/v1/invoices/{id}` - Update invoice
- [ ] `DELETE /api/v1/invoices/{id}` - Delete invoice (draft only)
- [ ] `POST /api/v1/invoices/{id}/send` - Mark as sent
- [ ] `POST /api/v1/invoices/{id}/finalize` - Convert draft to final
- [ ] Automatic calculations:
  - Line item totals
  - Subtotal
  - VAT/Tax calculation
  - Grand total
  - Outstanding amount

#### 4. PDF Generation (Day 14)
- [ ] Install ReportLab or WeasyPrint
- [ ] Create professional invoice template
- [ ] Include business branding (logo, colors)
- [ ] Add QR code for payment
- [ ] `GET /api/v1/invoices/{id}/pdf` - Download PDF
- [ ] Auto-increment invoice counter on finalization

#### 5. Payment Tracking (Day 15)
- [ ] Create Payment table
  - Payment amount
  - Payment date
  - Payment method
  - Reference number
  - Invoice relationship

- [ ] Payment endpoints:
  - `POST /api/v1/invoices/{id}/payments` - Record payment
  - `GET /api/v1/invoices/{id}/payments` - List payments
  - `DELETE /api/v1/payments/{id}` - Delete payment

- [ ] Auto-update customer analytics:
  - Update total_paid_amount
  - Update average_payment_days
  - Update last_invoice_date

#### 6. Invoice Analytics
- [ ] Dashboard endpoint with:
  - Total revenue
  - Outstanding amount
  - Overdue invoices
  - Payment trends
  - Top customers by revenue
  - Monthly revenue chart data

---

## 📋 Week 3 Database Schema (Planned)

### **invoices** table
```sql
- id (UUID, PK)
- business_id (UUID, FK -> businesses.id)
- customer_id (UUID, FK -> customers.id)
- invoice_number (VARCHAR, UNIQUE)
- issue_date (DATE)
- due_date (DATE)
- status (ENUM: DRAFT/SENT/PAID/OVERDUE/CANCELLED)
- subtotal (NUMERIC(15,2))
- tax_amount (NUMERIC(15,2))
- discount_amount (NUMERIC(15,2))
- total_amount (NUMERIC(15,2))
- paid_amount (NUMERIC(15,2))
- outstanding_amount (NUMERIC(15,2))
- payment_terms (TEXT)
- notes (TEXT)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- sent_at (TIMESTAMP)
- paid_at (TIMESTAMP)
```

### **invoice_items** table
```sql
- id (UUID, PK)
- invoice_id (UUID, FK -> invoices.id)
- product_id (UUID, FK -> products.id, NULL allowed)
- description (VARCHAR)
- quantity (NUMERIC(10,2))
- unit_price (NUMERIC(15,2))
- discount_percent (NUMERIC(5,2))
- tax_rate (NUMERIC(5,2))
- line_total (NUMERIC(15,2))
- created_at (TIMESTAMP)
```

### **products** table
```sql
- id (UUID, PK)
- business_id (UUID, FK -> businesses.id)
- name (VARCHAR)
- description (TEXT)
- unit_price (NUMERIC(15,2))
- tax_rate (NUMERIC(5,2))
- is_active (BOOLEAN)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

### **payments** table
```sql
- id (UUID, PK)
- invoice_id (UUID, FK -> invoices.id)
- amount (NUMERIC(15,2))
- payment_date (DATE)
- payment_method (VARCHAR)
- reference_number (VARCHAR)
- notes (TEXT)
- created_at (TIMESTAMP)
```

---

## 🎯 Week 3 Implementation Checklist

### Day 11: Invoice & InvoiceItem Models
- [ ] Create `app/models/invoice.py`
- [ ] Create `app/models/invoice_item.py`
- [ ] Create `app/schemas/invoice.py`
- [ ] Update `app/models/__init__.py`
- [ ] Update `alembic/env.py`
- [ ] Create migration: `alembic revision --autogenerate -m "Add invoices and invoice_items"`
- [ ] Apply migration: `alembic upgrade head`
- [ ] Test models in database

### Day 12: Product Model
- [ ] Create `app/models/product.py`
- [ ] Create `app/schemas/product.py`
- [ ] Create migration
- [ ] Create product endpoints: `app/api/v1/endpoints/products.py`
- [ ] Test CRUD operations

### Day 13: Invoice Endpoints
- [ ] Create `app/api/v1/endpoints/invoices.py`
- [ ] Implement calculation logic
- [ ] Add automatic invoice number generation
- [ ] Test all invoice CRUD operations
- [ ] Test automatic calculations

### Day 14: PDF Generation
- [ ] Install PDF library: `pip install reportlab`
- [ ] Create invoice template
- [ ] Add branding (use business logo and colors)
- [ ] Test PDF generation
- [ ] Add download endpoint

### Day 15: Payment Tracking
- [ ] Create `app/models/payment.py`
- [ ] Create payment endpoints
- [ ] Implement customer analytics updates
- [ ] Create invoice analytics dashboard
- [ ] Test complete invoice workflow
- [ ] Write `scripts/test_week3.py`

---

## 📚 Future Weeks Overview

### Week 4: Document Processing (AI/OCR)
- Receipt upload and storage
- AI-powered OCR (Optical Character Recognition)
- Automatic data extraction from receipts
- Receipt categorization
- Document management system

### Week 5: VAT & Tax Compliance
- VAT calculation automation
- Tax reports generation
- FIRS compliance features
- Expense categorization
- Tax deadline tracking

### Week 6: Reports & Analytics
- Financial reports
- Tax summary reports
- Customer insights
- Revenue analytics
- Export to PDF/Excel

### Week 7: Notifications & Email
- Email service integration
- Invoice email sending
- Payment reminders
- Due date notifications
- Weekly/monthly reports

### Week 8: Final Polish & Deployment
- API optimization
- Error handling improvements
- Comprehensive testing
- Documentation finalization
- Deployment preparation
- Production environment setup

---

## 🛠️ Development Commands

### Database Operations
```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration
alembic current

# View migration history
alembic history

# Check database tables
python scripts/check_db.py
```

### Server Operations
```bash
# Start development server
uvicorn app.main:app --reload

# Start with specific host/port
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start without reload (production-like)
uvicorn app.main:app
```

### Testing
```bash
# Run Week 2 tests
python scripts/test_week2.py

# Create admin user
python scripts/create_admin.py

# Check database
python scripts/check_db.py
```

### Dependency Management
```bash
# Install dependencies
pip install -r requirements.txt

# Update requirements
pip freeze > requirements.txt

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\Scripts\activate

# Activate virtual environment (Mac/Linux)
source venv/bin/activate
```

---

## 🐛 Known Issues & Solutions

### Issue 1: Pydantic v2 `regex` Error
**Error:** `'regex' is removed. use 'pattern' instead`

**Solution:** Replace `regex=` with `pattern=` in Pydantic Field definitions

### Issue 2: Import Errors After Adding Models
**Error:** ModuleNotFoundError or circular imports

**Solution:** 
1. Update `app/models/__init__.py` with new model imports
2. Update `alembic/env.py` with new model imports
3. Restart server

### Issue 3: Migration Conflicts
**Error:** Multiple heads or conflicts

**Solution:**
```bash
alembic heads  # Check for multiple heads
alembic merge heads  # Merge if needed
```

### Issue 4: File Upload Not Working
**Error:** Files not saving

**Solution:**
1. Create uploads directory: `mkdir -p uploads/logos`
2. Check file permissions
3. Verify MAX_UPLOAD_SIZE_MB in .env

---

## 📖 Documentation Resources

### API Documentation
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### External Documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)

### Project Documentation Files
- `README_WEEK_2.md` - Week 2 overview
- `WEEK_2_IMPLEMENTATION_GUIDE.md` - Detailed implementation steps
- `WEEK_2_QUICK_REFERENCE.md` - API reference

---

## 👥 Handover Notes for Next Developer

### Getting Started
1. **Clone the repository** (if not already done)
2. **Set up virtual environment:** `python -m venv venv`
3. **Activate environment:** `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
4. **Install dependencies:** `pip install -r requirements.txt`
5. **Set up .env file** with database credentials
6. **Run migrations:** `alembic upgrade head`
7. **Create admin user:** `python scripts/create_admin.py`
8. **Start server:** `uvicorn app.main:app --reload`
9. **Test endpoints:** Visit http://localhost:8000/docs

### Important Code Patterns

#### Creating a New Model
```python
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.core.database import Base

class YourModel(Base):
    __tablename__ = "your_table"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ... other columns
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Creating a New Endpoint
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/your-resource", tags=["YourResource"])

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: YourSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Your logic here
    pass
```

#### Getting User's Business
```python
def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business
```

### Coding Standards
- Use **type hints** everywhere
- Write **docstrings** for all functions
- Follow **PEP 8** style guide
- Use **async/await** for endpoints
- Always use **dependency injection** for database sessions
- **Validate input** with Pydantic schemas
- **Handle errors** with appropriate HTTP status codes
- Use **UUID** for all primary keys
- Always include **timestamps** (created_at, updated_at)

### Git Workflow
```bash
# Create feature branch
git checkout -b feature/week3-invoicing

# Make changes and commit
git add .
git commit -m "feat: add invoice model and endpoints"

# Push to remote
git push origin feature/week3-invoicing
```

---

## 📞 Support & Questions

### For Technical Issues
- Check the troubleshooting section
- Review error messages in console
- Check database with `scripts/check_db.py`
- Verify migrations with `alembic current`

### For Implementation Questions
- Review the implementation guides
- Check existing code patterns
- Refer to API documentation at `/docs`
- Look at test scripts for usage examples

---

## ✅ Final Checklist Before Starting Week 3

- [ ] All Week 1 & 2 features working
- [ ] All tests passing
- [ ] Database migrations applied
- [ ] Admin user exists
- [ ] API documentation accessible
- [ ] .env file configured correctly
- [ ] Virtual environment activated
- [ ] Dependencies installed
- [ ] Git repository up to date
- [ ] Documentation reviewed

---

## 🎉 Summary

**Completed:**
- ✅ 3 database tables (users, businesses, customers)
- ✅ 22 API endpoints
- ✅ JWT authentication
- ✅ Multi-tenant architecture
- ✅ File upload functionality
- ✅ Comprehensive testing
- ✅ Full API documentation

**Next Up:**
- 🔜 Invoice management system
- 🔜 PDF generation
- 🔜 Payment tracking
- 🔜 Product catalog
- 🔜 Analytics dashboard

**Project is on track and ready for Week 3 implementation! 🚀**

---

**Document Version:** 1.0  
**Last Updated:** February 3, 2026  
**Next Review:** After Week 3 completion