"""
Fix Invoice Counter Issue
This script will sync the invoice counter with the actual invoices in the database
Usage: python fix_invoice_counter.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.core.database import SessionLocal
from app.models.business import Business
from app.models.invoice import Invoice
from sqlalchemy import func


def fix_invoice_counter():
    """Fix the invoice counter to match the database"""
    print("=" * 70)
    print("  FIXING INVOICE COUNTER")
    print("=" * 70)
    print()
    
    db = SessionLocal()
    
    try:
        # Get all businesses
        businesses = db.query(Business).all()
        
        if not businesses:
            print("❌ No businesses found")
            return
        
        for business in businesses:
            print(f"\n📊 Business: {business.business_name}")
            print(f"   Current counter: {business.invoice_counter}")
            
            # Get the highest invoice number for this business
            # Extract the numeric part from invoice numbers like "TC-00001"
            invoices = db.query(Invoice).filter(
                Invoice.business_id == business.id
            ).all()
            
            if not invoices:
                print("   ℹ️  No invoices found - counter is correct")
                continue
            
            # Extract numeric parts and find the max
            max_number = 0
            for invoice in invoices:
                # Extract number from format like "TC-00001"
                try:
                    # Split by '-' and get the last part
                    number_part = invoice.invoice_number.split('-')[-1]
                    number = int(number_part)
                    max_number = max(max_number, number)
                except (ValueError, IndexError):
                    print(f"   ⚠️  Couldn't parse invoice number: {invoice.invoice_number}")
            
            print(f"   Highest invoice number: {max_number}")
            
            # Set counter to max_number + 1
            new_counter = max_number + 1
            
            if business.invoice_counter != new_counter: # type: ignore
                print(f"   ⚠️  Counter mismatch!")
                print(f"   Updating counter: {business.invoice_counter} → {new_counter}")
                business.invoice_counter = new_counter # type: ignore
                db.commit()
                print(f"   ✅ Counter updated!")
            else:
                print(f"   ✅ Counter is correct")
            
            # Show next invoice number
            next_number = business.get_next_invoice_number()
            print(f"   Next invoice: {next_number}")
        
        print()
        print("=" * 70)
        print("  ✅ INVOICE COUNTER FIX COMPLETE")
        print("=" * 70)
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    fix_invoice_counter()