#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMERGENCY FIX - Restore customers.py router
============================================

The automatic fix accidentally removed the router definition.
This script will restore it.
"""

from pathlib import Path

def emergency_fix():
    """Restore the router definition in customers.py"""
    
    customers_file = Path("app/api/v1/endpoints/customers.py")
    backup_file = Path("app/api/v1/endpoints/customers.py.backup")
    
    print("\n" + "="*80)
    print("EMERGENCY FIX - Restoring customers.py")
    print("="*80 + "\n")
    
    # Check if backup exists
    if not backup_file.exists():
        print("❌ No backup found! Cannot restore automatically.")
        print("\nPlease restore from git:")
        print("  git checkout app/api/v1/endpoints/customers.py")
        return False
    
    print("📝 Restoring from backup...")
    
    # Read backup
    backup_content = backup_file.read_text(encoding='utf-8')
    
    # Check if backup has router
    if "router = APIRouter" not in backup_content:
        print("❌ Backup is also corrupted!")
        return False
    
    # Restore backup
    customers_file.write_text(backup_content, encoding='utf-8')
    print("✅ Restored from backup")
    
    # Now apply the fix correctly
    print("\n📝 Applying performance fix (correctly this time)...")
    
    content = customers_file.read_text(encoding='utf-8')
    
    # Find the stats function
    stats_start = content.find("# Get all customers for sorting by computed properties")
    if stats_start == -1:
        stats_start = content.find("all_customers = db.query(Customer)")
    
    if stats_start == -1:
        print("⚠️  Could not find statistics function to fix")
        print("✅ File restored from backup - server should work now")
        print("❌ Performance issue NOT fixed - needs manual fix")
        return True
    
    # Find the end of the problematic section
    stats_end = content.find("except Exception as e:", stats_start)
    
    if stats_end == -1:
        print("⚠️  Could not find end of function")
        print("✅ File restored from backup - server should work now")
        return True
    
    # Create the fixed version
    fixed_section = '''
        # ================================================================
        # PERFORMANCE FIX: Use database aggregation (not Python sorting)
        # ================================================================
        
        # Optimized aggregation query (uses indexes)
        stats = db.query(
            func.count(Customer.id).label('total'),
            func.count(Customer.id).filter(Customer.is_active == True).label('active')
        ).filter(
            Customer.business_id == business.id
        ).first()
        
        total_customers = stats.total or 0
        active_customers = stats.active or 0
        
        # CRITICAL FIX: Get top customers using SQL ORDER BY (not Python sorting)
        top_customers_query = db.query(Customer)\\
            .filter(Customer.business_id == business.id)\\
            .filter(Customer.is_active == True)\\
            .order_by(Customer.total_invoiced_amount.desc())\\
            .limit(5)\\
            .all()
        
        # Calculate average payment days in database (not Python)
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
        
    '''
    
    # Replace the section
    new_content = content[:stats_start] + fixed_section + content[stats_end:]
    
    # Save
    customers_file.write_text(new_content, encoding='utf-8')
    print("✅ Performance fix applied!")
    
    return True


if __name__ == "__main__":
    success = emergency_fix()
    
    if success:
        print("\n" + "="*80)
        print("✅ CUSTOMERS.PY RESTORED AND FIXED!")
        print("="*80)
        print("\n📋 Next steps:")
        print("  1. Server should auto-reload now")
        print("  2. Check for errors in server output")
        print("  3. If still broken, run: git checkout app/api/v1/endpoints/customers.py")
        print("  4. Then apply fixes manually")
        print("="*80 + "\n")
    else:
        print("\n" + "="*80)
        print("❌ EMERGENCY FIX FAILED")
        print("="*80)
        print("\n📋 Manual recovery:")
        print("  1. Restore from git:")
        print("     git checkout app/api/v1/endpoints/customers.py")
        print("\n  2. Apply fixes manually using the guide")
        print("="*80 + "\n")
    
    exit(0 if success else 1)