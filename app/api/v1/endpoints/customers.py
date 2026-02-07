"""
Customer API Endpoints
Location: app/api/v1/endpoints/customers.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query # type: ignore
from sqlalchemy.orm import Session # type: ignore
from typing import Optional
import uuid
import math

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User # type: ignore
from app.models.business import Business
from app.models.customer import Customer
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
    CustomerSummary
)

router = APIRouter(prefix="/customers", tags=["Customers"])


# ============================================================================
# Helper Function
# ============================================================================

def get_user_business(db: Session, user_id: uuid.UUID) -> Business:
    """Get user's business or raise 404"""
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found. Create one first at POST /businesses"
        )
    return business


# ============================================================================
# Customer CRUD Endpoints
# ============================================================================

@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new customer for your business.
    
    **Required:**
    - **name**: Customer name (2-255 chars)
    
    **Optional:**
    - **email**: Customer email
    - **phone**: Customer phone number
    - **address**: Full address
    - **city, state**: Location details
    - **tin**: Customer's Tax Identification Number
    - **customer_type**: "Individual" or "Business"
    - **credit_limit**: Maximum credit allowed
    - **payment_terms_days**: Payment terms (default: 30 days)
    - **notes**: Additional notes
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Check for duplicate email (if provided)
    if customer_data.email:
        existing = db.query(Customer).filter(
            Customer.business_id == business.id,
            Customer.email == customer_data.email
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer with email {customer_data.email} already exists"
            )
    
    # Create customer
    customer = Customer(
        **customer_data.model_dump(),
        business_id=business.id
    )
    
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    return customer


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    customer_type: Optional[str] = Query(None, description="Filter by customer type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a paginated list of customers.
    
    **Query Parameters:**
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (max: 100, default: 50)
    - **search**: Search in name, email, or phone
    - **customer_type**: Filter by "Individual" or "Business"
    - **is_active**: Filter by active status
    
    **Returns**: Paginated list with metadata
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Base query
    query = db.query(Customer).filter(Customer.business_id == business.id)
    
    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(search_term)) |
            (Customer.email.ilike(search_term)) |
            (Customer.phone.ilike(search_term))
        )
    
    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)
    
    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)
    
    # Get total count
    total = query.count()
    
    # Calculate pagination
    total_pages = math.ceil(total / page_size)
    offset = (page - 1) * page_size
    
    # Get paginated results
    customers = query.order_by(Customer.created_at.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    return {
        "customers": customers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/summary", response_model=list[CustomerSummary])
async def list_customers_summary(
    limit: int = Query(10, ge=1, le=100, description="Max items to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a lightweight summary of customers (for dropdowns, autocomplete, etc.)
    
    Returns only essential fields for better performance.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    customers = db.query(Customer)\
        .filter(Customer.business_id == business.id)\
        .filter(Customer.is_active == True)\
        .order_by(Customer.name)\
        .limit(limit)\
        .all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "total_invoices_count": c.total_invoices_count,
            "outstanding_amount": c.outstanding_amount,
            "is_active": c.is_active
        }
        for c in customers
    ]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific customer by ID.
    
    Returns complete customer details including analytics.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business.id
    ).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    customer_data: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a customer's information.
    
    All fields are optional - only provided fields will be updated.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business.id
    ).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Check for email conflict (if email is being updated)
    if customer_data.email and customer_data.email != customer.email:
        existing = db.query(Customer).filter(
            Customer.business_id == business.id,
            Customer.email == customer_data.email,
            Customer.id != customer_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer with email {customer_data.email} already exists"
            )
    
    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    db.commit()
    db.refresh(customer)
    
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a customer (soft delete - marks as inactive).
    
    The customer is not permanently removed, just marked as inactive.
    This preserves historical invoice data.
    
    To permanently delete, use DELETE /customers/{id}/permanent
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business.id
    ).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Soft delete
    customer.is_active = False # type: ignore
    db.commit()
    
    return None


@router.delete("/{customer_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a customer.
    
    **Warning**: This will permanently remove the customer and may affect:
    - Invoice history
    - Analytics
    - Reports
    
    Use with caution! Consider soft delete instead.
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business.id
    ).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Check if customer has invoices
    if customer.total_invoices_count > 0: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete customer with {customer.total_invoices_count} invoice(s). "
                   "Use soft delete instead or delete all invoices first."
        )
    
    # Permanent delete
    db.delete(customer)
    db.commit()
    
    return None


# ============================================================================
# Customer Statistics
# ============================================================================

@router.get("/stats/overview")
async def get_customer_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get overview statistics about customers.
    
    Returns:
    - Total customers
    - Active customers
    - Top customers by revenue
    - Average payment days
    """
    business = get_user_business(db, current_user.id) # type: ignore
    
    # Get all customers
    customers = db.query(Customer).filter(
        Customer.business_id == business.id
    ).all()
    
    # Calculate stats
    total_customers = len(customers)
    active_customers = len([c for c in customers if c.is_active]) # type: ignore
    
    # Top customers by total invoiced amount
    top_customers = sorted(
        customers,
        key=lambda c: float(c.total_invoiced_amount), # type: ignore
        reverse=True
    )[:5]
    
    # Average payment days (excluding None values)
    payment_days = [c.average_payment_days for c in customers if c.average_payment_days] # type: ignore
    avg_payment_days = sum(payment_days) / len(payment_days) if payment_days else None
    
    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "inactive_customers": total_customers - active_customers,
        "average_payment_days": avg_payment_days,
        "top_customers": [
            {
                "id": c.id,
                "name": c.name,
                "total_invoiced": float(c.total_invoiced_amount), # type: ignore
                "total_paid": float(c.total_paid_amount), # type: ignore
                "outstanding": float(c.outstanding_amount)
            }
            for c in top_customers
        ]
    }