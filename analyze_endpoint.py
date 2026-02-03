"""
Endpoint Error Identifier
This will show exactly where the endpoint is failing
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent if '__file__' in globals() else Path.cwd()
sys.path.insert(0, str(project_root))


def analyze_endpoint():
    print("=" * 70)
    print("  ANALYZING INVOICE ENDPOINT")
    print("=" * 70)
    print()
    
    # Import the endpoint file
    print("1. Checking endpoint file...")
    try:
        from app.api.v1.endpoints import invoices
        print("✅ Endpoint module imported")
    except Exception as e:
        print(f"❌ Failed to import endpoint module: {e}")
        return
    
    # Check the create_invoice function
    print("\n2. Analyzing create_invoice function...")
    try:
        import inspect
        source = inspect.getsource(invoices.create_invoice)
        
        print("✅ Function source retrieved")
        print(f"\nFunction has {len(source.splitlines())} lines")
        
        # Look for potential issues
        print("\n3. Checking for common issues...")
        
        issues_found = []
        
        # Check 1: Proper error handling
        if "try:" in source and "except Exception as e:" in source:
            print("✅ Has try/except block")
        else:
            issues_found.append("Missing proper error handling")
            print("❌ Missing try/except block")
        
        # Check 2: Database commit
        if "db.commit()" in source:
            print("✅ Has db.commit()")
        else:
            issues_found.append("Missing db.commit()")
            print("❌ Missing db.commit()")
        
        # Check 3: Refresh after commit
        if "db.refresh(invoice)" in source:
            # Check if it's AFTER commit
            commit_pos = source.find("db.commit()")
            refresh_pos = source.find("db.refresh(invoice)")
            if refresh_pos > commit_pos:
                print("✅ Has db.refresh(invoice) after commit")
            else:
                issues_found.append("db.refresh(invoice) before db.commit()")
                print("⚠️  db.refresh(invoice) is BEFORE db.commit()")
        else:
            issues_found.append("Missing db.refresh(invoice)")
            print("❌ Missing db.refresh(invoice)")
        
        # Check 4: Calculate totals
        if "calculate_totals()" in source:
            print("✅ Calls calculate_totals()")
        else:
            issues_found.append("Not calling calculate_totals()")
            print("⚠️  Not calling calculate_totals()")
        
        # Check 5: Flush before refresh
        if "db.flush()" in source:
            print("✅ Has db.flush()")
        else:
            print("⚠️  No db.flush() - might be okay")
        
        # Check 6: Response model
        if "@router.post" in source:
            if "response_model=InvoiceResponse" in source:
                print("✅ Has response_model")
            else:
                issues_found.append("Missing response_model")
                print("⚠️  Missing response_model")
        
        # Summary
        print("\n" + "=" * 70)
        if issues_found:
            print("  ⚠️  ISSUES FOUND")
            print("=" * 70)
            for i, issue in enumerate(issues_found, 1):
                print(f"{i}. {issue}")
        else:
            print("  ✅ NO OBVIOUS ISSUES FOUND")
            print("=" * 70)
            print("\nThe issue might be in:")
            print("1. Schema validation (InvoiceCreate)")
            print("2. Model method implementation")
            print("3. Database constraints")
        
        # Show the actual source
        print("\n" + "=" * 70)
        print("  FULL ENDPOINT SOURCE CODE")
        print("=" * 70)
        print()
        print(source)
        print()
        
    except Exception as e:
        print(f"❌ Error analyzing function: {e}")
        import traceback
        traceback.print_exc()


def test_schema_validation():
    """Test if the schema can validate the invoice data"""
    print("\n" + "=" * 70)
    print("  TESTING SCHEMA VALIDATION")
    print("=" * 70)
    print()
    
    try:
        from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
        from datetime import date, timedelta
        
        print("1. Creating test data...")
        
        # Create test invoice data
        test_data = {
            "customer_id": "bc2119ea-c2df-4ed6-8800-b791db9a67a4",
            "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=30),
            "discount_amount": 0,
            "items": [
                {
                    "description": "Test Product",
                    "quantity": 1,
                    "unit_price": 10000,
                    "discount_percent": 0,
                    "tax_rate": 7.5,
                    "sort_order": 0
                }
            ]
        }
        
        print("✅ Test data created")
        
        # Try to validate
        print("\n2. Validating with InvoiceCreate schema...")
        try:
            invoice_create = InvoiceCreate(**test_data)
            print("✅ Schema validation passed!")
            print(f"\nValidated data:")
            print(f"   Customer ID: {invoice_create.customer_id}")
            print(f"   Issue date: {invoice_create.issue_date}")
            print(f"   Due date: {invoice_create.due_date}")
            print(f"   Items: {len(invoice_create.items)}")
            print(f"   First item: {invoice_create.items[0].description}")
            
        except Exception as e:
            print(f"❌ Schema validation failed: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ Error in schema test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_endpoint()
    test_schema_validation()