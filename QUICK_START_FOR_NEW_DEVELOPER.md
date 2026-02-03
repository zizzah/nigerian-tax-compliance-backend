# 🚀 Quick Start Guide for New Developer

**Project:** Nigerian Tax Compliance Platform Backend  
**Current Status:** Week 2 Complete  
**Next Task:** Week 3 - Invoicing System

---

## ⚡ 5-Minute Setup

### 1. Environment Setup
```bash
# Activate virtual environment
cd nigerian-tax-compliance-backend
venv\Scripts\activate  # Windows
# OR
source venv/bin/activate  # Mac/Linux

# Install dependencies (if not already done)
pip install -r requirements.txt
```

### 2. Database Setup
```bash
# Check .env file has correct DATABASE_URL
# Example: DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Run migrations
alembic upgrade head

# Verify database
python scripts/check_db.py
# Should show: users, businesses, customers
```

### 3. Start Server
```bash
uvicorn app.main:app --reload
```

### 4. Test Everything
```bash
# Visit API docs
# http://localhost:8000/docs

# Login with admin user
# Email: admin@example.com
# Password: Admin@123

# OR run automated tests
python scripts/test_week2.py
```

---

## 📊 What's Working Right Now

### ✅ Completed Features
- User registration and login (JWT auth)
- Business profile management
- Customer management with pagination
- Logo upload
- Customer analytics
- Multi-tenant data isolation

### 🔢 Current Stats
- **3 Database Tables:** users, businesses, customers
- **22 API Endpoints:** All tested and working
- **File Upload:** Logo upload to `uploads/logos/`
- **Authentication:** JWT with access & refresh tokens

---

## 🎯 Your First Task: Week 3 - Invoicing

### What to Build (5 Days)

**Day 11-12: Invoice Model**
- Create Invoice and InvoiceItem models
- Set up relationships with Business and Customer
- Create database migrations

**Day 13: Invoice Endpoints**
- CRUD operations for invoices
- Automatic calculations (subtotal, tax, total)
- Invoice number auto-generation

**Day 14: PDF Generation**
- Install ReportLab: `pip install reportlab`
- Create invoice template with branding
- PDF download endpoint

**Day 15: Payment Tracking**
- Create Payment model
- Record payment endpoint
- Update customer analytics automatically

---

## 📁 Key Files to Know

### Where Everything Lives
```
app/
├── main.py                    # FastAPI app - register new routers here
├── core/
│   ├── database.py           # DB connection
│   ├── security.py           # JWT & password hashing
│   └── dependencies.py       # get_current_user
├── models/                    # SQLAlchemy models
│   ├── user.py               ✅ Done
│   ├── business.py           ✅ Done
│   ├── customer.py           ✅ Done
│   ├── invoice.py            ⬜ TODO (Week 3)
│   └── product.py            ⬜ TODO (Week 3)
├── schemas/                   # Pydantic validation
│   ├── business.py           ✅ Done
│   ├── customer.py           ✅ Done
│   └── invoice.py            ⬜ TODO (Week 3)
└── api/v1/endpoints/         # API routes
    ├── auth.py               ✅ Done
    ├── users.py              ✅ Done
    ├── businesses.py         ✅ Done
    ├── customers.py          ✅ Done
    └── invoices.py           ⬜ TODO (Week 3)
```

### Important Files to Update for Week 3
1. **`app/models/__init__.py`** - Add new model imports
2. **`alembic/env.py`** - Add new model imports
3. **`app/main.py`** - Register new routers
4. **`requirements.txt`** - Add reportlab

---

## 🔧 Common Commands You'll Need

### Database
```bash
# Create migration after adding model
alembic revision --autogenerate -m "Add invoices table"

# Apply migration
alembic upgrade head

# Check current version
alembic current

# Rollback last migration
alembic downgrade -1
```

### Development
```bash
# Start server with auto-reload
uvicorn app.main:app --reload

# Check what's in database
python scripts/check_db.py

# Run tests
python scripts/test_week2.py
```

---

## 🎨 Code Templates

### 1. Create a New Model (e.g., Invoice)

**File:** `app/models/invoice.py`
```python
from sqlalchemy import Column, String, Integer, Date, Numeric, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.core.database import Base
import enum

class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    
    invoice_number = Column(String(50), unique=True, nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    
    subtotal = Column(Numeric(15, 2), default=0)
    tax_amount = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), default=0)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 2. Create Pydantic Schema

**File:** `app/schemas/invoice.py`
```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
import uuid

class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    issue_date: date
    due_date: date
    # ... other fields

class InvoiceResponse(BaseModel):
    id: uuid.UUID
    invoice_number: str
    status: str
    total_amount: float
    # ... other fields
    
    class Config:
        from_attributes = True
```

### 3. Create Endpoint

**File:** `app/api/v1/endpoints/invoices.py`
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.invoice import Invoice
from app.schemas.invoice import InvoiceCreate, InvoiceResponse

router = APIRouter(prefix="/invoices", tags=["Invoices"])

@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new invoice"""
    # Get user's business
    business = db.query(Business).filter(Business.user_id == current_user.id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Generate invoice number
    invoice_number = business.get_next_invoice_number()
    
    # Create invoice
    invoice = Invoice(
        **invoice_data.model_dump(),
        business_id=business.id,
        invoice_number=invoice_number
    )
    
    db.add(invoice)
    
    # Increment counter
    business.invoice_counter += 1
    
    db.commit()
    db.refresh(invoice)
    
    return invoice
```

### 4. Register Router in main.py

**File:** `app/main.py`
```python
from app.api.v1.endpoints import auth, users, businesses, customers, invoices

# ... existing code ...

app.include_router(invoices.router, prefix=settings.API_V1_PREFIX)
```

### 5. Update Model Imports

**File:** `app/models/__init__.py`
```python
from app.core.database import Base
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice  # ADD THIS
from app.models.product import Product  # ADD THIS
```

**File:** `alembic/env.py` (add to imports section)
```python
from app.models.invoice import Invoice
from app.models.product import Product
```

---

## 💡 Pro Tips

### 1. Always Get User's Business First
```python
business = db.query(Business).filter(Business.user_id == current_user.id).first()
if not business:
    raise HTTPException(status_code=404, detail="Business not found")
```

### 2. Use UUID for All IDs
```python
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
```

### 3. Always Add Timestamps
```python
created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 4. Pydantic v2 Syntax
```python
# Use pattern, not regex
color: str = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')

# Use field_validator, not validator
from pydantic import field_validator

@field_validator('field_name')
@classmethod
def validate_field(cls, v):
    return v

# Use model_dump(), not dict()
data = invoice_data.model_dump()
```

### 5. Testing Your New Endpoint
```python
# Visit http://localhost:8000/docs
# Find your endpoint
# Click "Try it out"
# Fill in the example data
# Click "Execute"
```

---

## 🐛 Common Issues & Fixes

### Error: "Business not found"
```python
# Always create business first for test users
POST /api/v1/businesses
```

### Error: "Unauthorized"
```python
# Login and get token
POST /api/v1/auth/login

# Click "Authorize" in Swagger UI
# Paste the access_token
```

### Error: Migration issues
```bash
# Check what migrations exist
alembic history

# Check current migration
alembic current

# If stuck, rollback and re-run
alembic downgrade -1
alembic upgrade head
```

### Error: Import errors
```python
# Make sure to update:
# 1. app/models/__init__.py
# 2. alembic/env.py
# 3. Restart server
```

---

## 📚 Reference Documents

### Essential Reading
1. **PROJECT_STATUS_AND_HANDOVER.md** - Complete project overview
2. **WEEK_2_IMPLEMENTATION_GUIDE.md** - How Week 2 was built
3. **WEEK_2_QUICK_REFERENCE.md** - API endpoints reference

### API Documentation
- **Local:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### External Docs
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy: https://docs.sqlalchemy.org/en/20/
- Pydantic: https://docs.pydantic.dev/latest/

---

## ✅ Pre-Work Checklist

Before starting Week 3, make sure:
- [ ] Server starts without errors
- [ ] Can login and get JWT token
- [ ] Can create business profile
- [ ] Can create customers
- [ ] All 22 endpoints work in `/docs`
- [ ] Database has 3 tables (users, businesses, customers)
- [ ] Migrations are up to date: `alembic current`
- [ ] Have reviewed existing code patterns

---

## 🎯 Week 3 Success Criteria

By end of Week 3, you should have:
- [ ] Invoice model created and migrated
- [ ] InvoiceItem model created
- [ ] Product model created (optional but recommended)
- [ ] Can create invoices with line items
- [ ] Automatic calculation of totals
- [ ] Invoice number auto-generation working
- [ ] PDF generation working
- [ ] Payment tracking working
- [ ] Customer analytics updating automatically
- [ ] All endpoints tested
- [ ] Test script created: `scripts/test_week3.py`

---

## 🚀 Ready to Start?

1. **Read** the PROJECT_STATUS_AND_HANDOVER.md
2. **Review** existing code in `app/models/` and `app/api/v1/endpoints/`
3. **Plan** your Week 3 implementation
4. **Start** with Day 11: Invoice model
5. **Test** each feature as you build it
6. **Document** any changes or decisions

**Good luck! You've got a solid foundation to build on! 💪**

---

**Questions?** Review the handover document or check existing code for patterns.