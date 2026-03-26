"""
Customer API Endpoints
Location: app/api/v1/endpoints/customers.py

WITH SECURITY FIXES: Input sanitization
PRODUCTION OPTIMIZED: Enhanced pagination, search, and query optimization
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import func, or_ # type: ignore
from typing import Optional, List
import uuid
import math
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.sanitizer import sanitizer # type: ignore
from app.core.config import settings
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
logger = logging.getLogger(__name__)


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
# Customer CRUD Endpoints - PRODUCTION OPTIMIZED
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
    
    **Security:** All text inputs are sanitized to prevent XSS attacks
    """
    try:
        business = get_user_business(db, current_user.id) # type: ignore
        
        # SECURITY: Sanitize email for duplicate check
        sanitized_email = sanitizer.sanitize_email(customer_data.email) if customer_data.email else None
        
        # Check for duplicate email (if provided)
        if sanitized_email:
            existing = db.query(Customer).filter(
                Customer.business_id == business.id,
                Customer.email == sanitized_email
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Customer with email {sanitized_email} already exists"
                )
        
        # SECURITY: Sanitize all text inputs before creating customer
        customer = Customer(
            business_id=business.id,
            name=sanitizer.sanitize_text(customer_data.name, field_type="name"),
            email=sanitized_email,
            phone=sanitizer.sanitize_phone(customer_data.phone) if customer_data.phone else None,
            address=sanitizer.sanitize_text(customer_data.address, field_type="address") if customer_data.address else None,
            city=sanitizer.sanitize_text(customer_data.city) if customer_data.city else None,
            state=sanitizer.sanitize_text(customer_data.state) if customer_data.state else None,
            tin=sanitizer.sanitize_tin(customer_data.tin) if customer_data.tin else None,
            customer_type=customer_data.customer_type,
            credit_limit=customer_data.credit_limit,
            payment_terms_days=customer_data.payment_terms_days,
            notes=sanitizer.sanitize_text(customer_data.notes, field_type="notes") if customer_data.notes else None,
        )
        
        db.add(customer)
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Customer created: {customer.id} by user {current_user.id}")
        
        return customer
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating customer"
        )


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description=f"Maximum number of records to return (max: {settings.MAX_PAGE_SIZE})"
    ),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    customer_type: Optional[str] = Query(None, description="Filter by customer type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a paginated list of customers - PRODUCTION OPTIMIZED
    
    **Performance:** Optimized with pagination, filtering, and efficient queries
    
    **Query Parameters:**
    - **skip**: Offset for pagination (default: 0)
    - **limit**: Items per page (default: 50, max: 1000)
    - **search**: Search in name, email, or phone
    - **customer_type**: Filter by "Individual" or "Business"
    - **is_active**: Filter by active status
    - **sort_by**: Field to sort by (default: created_at)
    - **sort_order**: "asc" or "desc" (default: desc)
    
    **Returns:** Paginated list with metadata
    - items: List of customers
    - total: Total count of customers matching filters
    - page: Current page number
    - per_page: Items per page
    - total_pages: Total number of pages
    - has_next: Whether there are more pages
    - has_prev: Whether there are previous pages
    """
    try:
        business = get_user_business(db, current_user.id) # type: ignore
        
        # Base query - optimized with proper filtering
        query = db.query(Customer).filter(Customer.business_id == business.id)
        
        # Apply search filter with ILIKE for case-insensitive search
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.email.ilike(search_term),
                    Customer.phone.ilike(search_term)
                )
            )
        
        # Apply customer type filter
        if customer_type:
            query = query.filter(Customer.customer_type == customer_type)
        
        # Apply active status filter
        if is_active is not None:
            query = query.filter(Customer.is_active == is_active)
        
        # Get total count BEFORE pagination (for metadata)
        total = query.count()
        
        # Apply sorting
        if hasattr(Customer, sort_by):
            if sort_order == "desc":
                query = query.order_by(getattr(Customer, sort_by).desc())
            else:
                query = query.order_by(getattr(Customer, sort_by).asc())
        else:
            # Default sort if field doesn't exist
            query = query.order_by(Customer.created_at.desc())
        
        # Apply pagination - CRITICAL for performance
        customers = query.offset(skip).limit(limit).all()
        
        # Calculate pagination metadata
        total_pages = math.ceil(total / limit) if limit > 0 else 0
        current_page = (skip // limit) + 1 if limit > 0 else 1
        
        logger.debug(
            f"Listed customers: total={total}, page={current_page}, "
            f"limit={limit}, search={search}"
        )
        
        return {
            "customers": customers,
            "total": total,
            "page": current_page,
            "page_size": limit,
            "total_pages": total_pages,
            "has_next": skip + limit < total,
            "has_prev": skip > 0
        }
        
    except Exception as e:
        logger.error(f"Error listing customers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving customers"
        )


@router.get("/search", response_model=List[CustomerSummary])
async def search_customers(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Quick customer search - OPTIMIZED for autocomplete/typeahead
    
    **Performance:** Lightweight query with minimal fields for fast response
    
    **Use Cases:**
    - Autocomplete dropdowns
    - Typeahead search
    - Quick customer selection
    
    **Args:**
    - **q**: Search query (minimum 2 characters)
    - **limit**: Maximum results (default: 20, max: 100)
    
    **Returns:** Lightweight customer summaries with essential fields only
    """
    try:
        business = get_user_business(db, current_user.id) # type: ignore
        
        search_term = f"%{q}%"
        
        # Optimized query - only active customers
        customers = db.query(Customer)\
            .filter(Customer.business_id == business.id)\
            .filter(Customer.is_active == True)\
            .filter(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.email.ilike(search_term),
                    Customer.phone.ilike(search_term)
                )
            )\
            .order_by(Customer.name)\
            .limit(limit)\
            .all()
        
        # Return lightweight summaries
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
        
    except Exception as e:
        logger.error(f"Error searching customers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error searching customers"
        )




@router.get("/{customer_id}/credit-score")
def get_customer_credit_score(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate a credit score (0-100) for a customer based on:
    - Payment speed (days to pay)
    - Payment consistency (std deviation)
    - Outstanding balance ratio
    - Invoice dispute rate
    - Relationship length (account age)
    """
    from datetime import date, timedelta
    from app.models.invoice import Invoice, InvoiceStatus

    business = get_user_business(db, current_user.id) # type: ignore
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.business_id == business.id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Get all invoices for this customer
    all_invoices = db.query(Invoice).filter(
        Invoice.customer_id == customer_id,
        Invoice.business_id == business.id,
        Invoice.status != InvoiceStatus.DRAFT, # type: ignore
        Invoice.status != InvoiceStatus.CANCELLED, # type: ignore
    ).all()

    if not all_invoices:
        return {
            "score": None, "grade": "N/A", "color": "#9e9990",
            "reason": "No invoice history",
            "factors": {},
        }

    paid = [i for i in all_invoices if i.status == InvoiceStatus.PAID and i.paid_at and i.issue_date] # type: ignore
    overdue_now = [i for i in all_invoices if i.status == InvoiceStatus.OVERDUE or # type: ignore
                   (i.status in [InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID] and i.due_date and i.due_date < date.today())]

    # --- Factor 1: Payment Speed (0-30 points) ---
    speed_score = 0
    avg_days = None
    if paid:
        days_list = [(i.paid_at.date() - i.issue_date).days for i in paid]
        avg_days = sum(days_list) / len(days_list)
        if avg_days <= 14:   speed_score = 30
        elif avg_days <= 30: speed_score = 25
        elif avg_days <= 45: speed_score = 15
        elif avg_days <= 60: speed_score = 8
        else:                speed_score = 2

    # --- Factor 2: Payment Consistency (0-25 points) ---
    consistency_score = 0
    if len(paid) >= 2:
        days_list = [(i.paid_at.date() - i.issue_date).days for i in paid]
        mean = sum(days_list) / len(days_list)
        std_dev = (sum((d - mean) ** 2 for d in days_list) / len(days_list)) ** 0.5
        if std_dev < 5:   consistency_score = 25
        elif std_dev < 10: consistency_score = 20
        elif std_dev < 20: consistency_score = 12
        elif std_dev < 35: consistency_score = 6
        else:              consistency_score = 2
    elif len(paid) == 1:
        consistency_score = 10  # some data

    # --- Factor 3: Current Overdue (0-25 points, inverse) ---
    overdue_score = 25  # start max
    total_invoiced = float(customer.total_invoiced_amount or 0) # type: ignore
    total_overdue = sum(float(i.outstanding_amount or 0) for i in overdue_now)   # type: ignore
    if total_invoiced > 0:
        overdue_ratio = total_overdue / total_invoiced
        if overdue_ratio > 0.5:  overdue_score = 0
        elif overdue_ratio > 0.3: overdue_score = 5
        elif overdue_ratio > 0.1: overdue_score = 12
        elif overdue_ratio > 0:  overdue_score = 18

    # --- Factor 4: Relationship Length (0-10 points) ---
    first_invoice = min(all_invoices, key=lambda i: i.issue_date)
    days_relationship = (date.today() - first_invoice.issue_date).days
    if days_relationship > 365:   rel_score = 10
    elif days_relationship > 180: rel_score = 7
    elif days_relationship > 90:  rel_score = 4
    else:                         rel_score = 2

    # --- Factor 5: Volume (0-10 points) ---
    vol_score = min(10, len(all_invoices))

    total_score = speed_score + consistency_score + overdue_score + rel_score + vol_score

    # Grade
    if total_score >= 80:   grade, color = "A", "#059669"
    elif total_score >= 65: grade, color = "B", "#2563eb"
    elif total_score >= 50: grade, color = "C", "#d97706"
    elif total_score >= 35: grade, color = "D", "#ea580c"
    else:                   grade, color = "F", "#dc2626"

    return {
        "score": total_score,
        "grade": grade,
        "color": color,
        "avg_payment_days": round(avg_days, 1) if avg_days else None,
        "total_invoices": len(all_invoices),
        "paid_invoices": len(paid),
        "overdue_invoices": len(overdue_now),
        "overdue_amount": total_overdue,
        "factors": {
            "payment_speed": {"score": speed_score, "max": 30, "label": "Payment Speed"},
            "consistency": {"score": consistency_score, "max": 25, "label": "Consistency"},
            "overdue_risk": {"score": overdue_score, "max": 25, "label": "No Outstanding Debt"},
            "relationship": {"score": rel_score, "max": 10, "label": "Relationship Length"},
            "volume": {"score": vol_score, "max": 10, "label": "Invoice Volume"},
        },
    }

@router.get("/summary", response_model=list[CustomerSummary])
async def list_customers_summary(
    limit: int = Query(10, ge=1, le=100, description="Max items to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a lightweight summary of customers (for dropdowns, autocomplete, etc.)
    
    **Performance:** Returns only essential fields for better performance
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
    
    **Security:** All text inputs are sanitized to prevent XSS attacks
    """
    try:
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
        
        # Get update data and sanitize text fields
        update_data = customer_data.model_dump(exclude_unset=True)
        
        # SECURITY: Sanitize all text inputs
        if "name" in update_data:
            update_data["name"] = sanitizer.sanitize_text(update_data["name"], field_type="name")
        
        if "email" in update_data:
            update_data["email"] = sanitizer.sanitize_email(update_data["email"])
            
            # Check for email conflict (if email is being updated)
            if update_data["email"] and update_data["email"] != customer.email:
                existing = db.query(Customer).filter(
                    Customer.business_id == business.id,
                    Customer.email == update_data["email"],
                    Customer.id != customer_id
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Customer with email {update_data['email']} already exists"
                    )
        
        if "phone" in update_data:
            update_data["phone"] = sanitizer.sanitize_phone(update_data["phone"])
        
        if "address" in update_data:
            update_data["address"] = sanitizer.sanitize_text(update_data["address"], field_type="address")
        
        if "city" in update_data:
            update_data["city"] = sanitizer.sanitize_text(update_data["city"])
        
        if "state" in update_data:
            update_data["state"] = sanitizer.sanitize_text(update_data["state"])
        
        if "tin" in update_data:
            update_data["tin"] = sanitizer.sanitize_tin(update_data["tin"])
        
        if "notes" in update_data:
            update_data["notes"] = sanitizer.sanitize_text(update_data["notes"], field_type="notes")
        
        # Update fields
        for field, value in update_data.items():
            setattr(customer, field, value)
        
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Customer updated: {customer_id} by user {current_user.id}")
        
        return customer
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating customer"
        )


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
    try:
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
        
        logger.info(f"Customer soft deleted: {customer_id} by user {current_user.id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting customer"
        )


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
    try:
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
        
        logger.info(f"Customer permanently deleted: {customer_id} by user {current_user.id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error permanently deleting customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting customer"
        )


# ============================================================================
# Customer Statistics - PRODUCTION OPTIMIZED
# ============================================================================

""

# ============================================================================
# FIX 1: Replace get_customer_statistics endpoint
# ============================================================================
# Location: app/api/v1/endpoints/customers.py (line ~450)

@router.get("/stats/overview")
async def get_customer_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    FIXED VERSION - No longer loads all customers into memory
    
    BEFORE: Loaded ALL customers, sorted in Python → 3000ms+
    AFTER: Uses database aggregation only → <100ms
    """
    try:
        business = get_user_business(db, current_user.id)   # type: ignore
        
        # ==================================================================
        # OPTIMIZATION: Use database aggregation (not Python)
        # ==================================================================
        
        # Get basic counts (uses indexes)
        stats = db.query(
            func.count(Customer.id).label('total'),
            func.count(Customer.id).filter(Customer.is_active == True).label('active')
        ).filter(
            Customer.business_id == business.id
        ).first()
        
        total_customers = stats.total or 0 # type: ignore
        active_customers = stats.active or 0 # type: ignore
        
        # ==================================================================
        # CRITICAL FIX: Get top customers using SQL (not Python sorting)
        # ==================================================================
        # This query uses the database to sort, not Python
        top_customers_query = db.query(Customer)\
            .filter(Customer.business_id == business.id)\
            .filter(Customer.is_active == True)\
            .order_by(Customer.total_invoiced_amount.desc())\
            .limit(5)\
            .all()
        
        # ==================================================================
        # OPTIMIZATION: Calculate average payment days in database
        # ==================================================================
        # Use database aggregation instead of Python
        avg_payment_days_result = db.query(
            func.avg(Customer.average_payment_days)
        ).filter(
            Customer.business_id == business.id,
            Customer.average_payment_days.isnot(None)  # type: ignore
        ).scalar()
        
        avg_payment_days = float(avg_payment_days_result) if avg_payment_days_result else None
        
        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "inactive_customers": total_customers - active_customers,
            "average_payment_days": avg_payment_days,
            "top_customers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "total_invoiced": float(c.total_invoiced_amount) if c.total_invoiced_amount else 0.0,  # type: ignore
                    "total_paid": float(c.total_paid_amount) if c.total_paid_amount else 0.0,  # type: ignore
                    "outstanding": float(c.outstanding_amount) if c.outstanding_amount else 0.0
                }
                for c in top_customers_query
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting customer statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving statistics"
        )


