#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMPLETE FIX - Applies both performance and invoice fixes
==========================================================

Run with: python apply_complete_fix.py
"""

import re
from pathlib import Path

def fix_customers_performance():
    """Fix customer statistics performance issue"""
    
    customers_file = Path("app/api/v1/endpoints/customers.py")
    
    if not customers_file.exists():
        print("❌ Error: customers.py not found!")
        return False
    
    print("📝 Fixing customers.py performance issue...")
    content = customers_file.read_text(encoding='utf-8')
    
    # Check if already fixed
    if "Database aggregation" in content or "CRITICAL FIX: Get top customers using SQL" in content:
        print("✅ Customer performance fix already applied!")
        return True
    
    # Find stats function
    stats_start = content.find("@router.get(\"/stats/overview\")")
    if stats_start == -1:
        print("⚠️  Warning: Statistics endpoint not found!")
        return False
    
    next_route = content.find("@router.", stats_start + 10)
    stats_end = next_route if next_route != -1 else len(content)
    
    new_stats = '''@router.get("/stats/overview")
async def get_customer_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get overview statistics - OPTIMIZED"""
    try:
        business = get_user_business(db, current_user.id)
        
        # Database aggregation (FAST!)
        stats = db.query(
            func.count(Customer.id).label('total'),
            func.count(Customer.id).filter(Customer.is_active == True).label('active')
        ).filter(Customer.business_id == business.id).first()
        
        total_customers = stats.total or 0
        active_customers = stats.active or 0
        
        # Top customers using SQL (not Python!)
        top_customers_query = db.query(Customer)\\
            .filter(Customer.business_id == business.id)\\
            .filter(Customer.is_active == True)\\
            .order_by(Customer.total_invoiced_amount.desc())\\
            .limit(5).all()
        
        # Average in database
        avg_payment_days_result = db.query(
            func.avg(Customer.average_payment_days)
        ).filter(
            Customer.business_id == business.id,
            Customer.average_payment_days.isnot(None)
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
                    "total_invoiced": float(c.total_invoiced_amount) if c.total_invoiced_amount else 0.0,
                    "total_paid": float(c.total_paid_amount) if c.total_paid_amount else 0.0,
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


'''
    
    new_content = content[:stats_start] + new_stats + content[stats_end:]
    
    # Backup
    backup = customers_file.with_suffix('.py.backup')
    backup.write_text(content, encoding='utf-8')
    
    # Write fix
    customers_file.write_text(new_content, encoding='utf-8')
    print("✅ Customer performance fix applied!")
    
    return True


def fix_invoice_race_condition():
    """Fix invoice number race condition"""
    
    invoices_file = Path("app/api/v1/endpoints/invoices.py")
    
    if not invoices_file.exists():
        print("❌ Error: invoices.py not found!")
        return False
    
    print("📝 Fixing invoice race condition...")
    content = invoices_file.read_text(encoding='utf-8')
    
    # Check if already fixed
    if "with_for_update()" in content:
        print("✅ Invoice race condition fix already applied!")
        return True
    
    # Find the function
    func_start = content.find("def generate_unique_invoice_number(")
    if func_start == -1:
        print("⚠️  Warning: generate_unique_invoice_number not found!")
        return False
    
    # Find end of function (next def or end)
    next_def = content.find("\ndef ", func_start + 10)
    func_end = next_def if next_def != -1 else len(content)
    
    new_function = '''def generate_unique_invoice_number(db: Session, business: Business, max_retries: int = 5) -> str:
    """
    Generate unique invoice number with database locking (RACE CONDITION FIX)
    """
    from app.models.business import Business as BusinessModel
    
    for attempt in range(max_retries):
        try:
            # CRITICAL FIX: Lock business row to prevent race conditions
            locked_business = db.query(BusinessModel)\\
                .filter(BusinessModel.id == business.id)\\
                .with_for_update()\\
                .first()
            
            if not locked_business:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )
            
            # Generate number
            invoice_number = f"{locked_business.invoice_prefix}-{str(locked_business.invoice_counter + 1).zfill(5)}"
            
            # Check if exists (shouldn't with locking, but be safe)
            existing = db.query(Invoice).filter(
                Invoice.invoice_number == invoice_number
            ).first()
            
            if existing:
                locked_business.invoice_counter += 1
                db.commit()
                if attempt < max_retries - 1:
                    time.sleep(0.1)
                continue
            
            # SUCCESS: Increment and commit BEFORE returning
            locked_business.invoice_counter += 1
            business.invoice_counter = locked_business.invoice_counter
            db.commit()
            
            logger.info(f"Generated invoice number: {invoice_number}")
            return invoice_number
            
        except Exception as e:
            logger.error(f"Error generating invoice number (attempt {attempt + 1}): {e}")
            db.rollback()
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (attempt + 1))
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to generate unique invoice number after {max_retries} attempts"
    )


'''
    
    new_content = content[:func_start] + new_function + content[func_end:]
    
    # Backup
    backup = invoices_file.with_suffix('.py.backup')
    backup.write_text(content, encoding='utf-8')
    
    # Write fix
    invoices_file.write_text(new_content, encoding='utf-8')
    print("✅ Invoice race condition fix applied!")
    
    return True


def main():
    print("\n" + "="*80)
    print("COMPLETE FIX - Performance + Invoice Race Condition".center(80))
    print("="*80 + "\n")
    
    success_count = 0
    
    # Fix 1: Customer performance
    if fix_customers_performance():
        success_count += 1
    
    # Fix 2: Invoice race condition
    if fix_invoice_race_condition():
        success_count += 1
    
    print("\n" + "="*80)
    if success_count == 2:
        print("🎉 ALL FIXES APPLIED SUCCESSFULLY!")
        print("="*80)
        print("\n📋 Next steps:")
        print("  1. Restart server: uvicorn app.main:app --reload")
        print("  2. Run tests: python test_all_endpoints.py")
        print("\n✅ Expected results:")
        print("  • Customer list: <300ms (was 4251ms)")
        print("  • Invoice creation: SUCCESS (was failing)")
        print("  • Pass rate: >95% (was 89.5%)")
    else:
        print("⚠️  SOME FIXES FAILED")
        print("="*80)
        print(f"\nApplied {success_count}/2 fixes")
        print("See FIX_INVOICE_RACE_CONDITION.py for manual instructions")
    
    print("="*80 + "\n")
    
    return success_count == 2


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)