"""
Check Invoice Models for Common Issues
This will help identify configuration problems
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent if '__file__' in globals() else Path.cwd()
sys.path.insert(0, str(project_root))

def check_models():
    print("=" * 70)
    print("  CHECKING MODEL CONFIGURATION")
    print("=" * 70)
    print()
    
    # Check if models can be imported
    print("1. Checking model imports...")
    try:
        from app.models.invoice import Invoice
        print("✅ Invoice model imported")
    except Exception as e:
        print(f"❌ Failed to import Invoice model: {e}")
        return
    
    try:
        from app.models.invoice_item import InvoiceItem
        print("✅ InvoiceItem model imported")
    except Exception as e:
        print(f"❌ Failed to import InvoiceItem model: {e}")
        return
    
    try:
        from app.models.product import Product
        print("✅ Product model imported")
    except Exception as e:
        print(f"❌ Failed to import Product model: {e}")
    
    try:
        from app.models.customer import Customer
        print("✅ Customer model imported")
    except Exception as e:
        print(f"❌ Failed to import Customer model: {e}")
    
    try:
        from app.models.business import Business
        print("✅ Business model imported")
    except Exception as e:
        print(f"❌ Failed to import Business model: {e}")
    
    # Check relationships
    print("\n2. Checking Invoice model relationships...")
    try:
        if hasattr(Invoice, 'items'):
            print("✅ Invoice has 'items' relationship")
            # Check relationship properties
            rel = Invoice.items.property
            print(f"   Cascade: {rel.cascade}")
            print(f"   Lazy: {rel.lazy}")
        else:
            print("❌ Invoice missing 'items' relationship!")
            print("   This is required for loading invoice items!")
    except Exception as e:
        print(f"⚠️  Error checking relationship: {e}")
    
    if hasattr(Invoice, 'customer'):
        print("✅ Invoice has 'customer' relationship")
    else:
        print("⚠️  Invoice missing 'customer' relationship (optional)")
    
    if hasattr(Invoice, 'business'):
        print("✅ Invoice has 'business' relationship")
    else:
        print("⚠️  Invoice missing 'business' relationship (optional)")
    
    # Check InvoiceItem relationships
    print("\n3. Checking InvoiceItem model relationships...")
    if hasattr(InvoiceItem, 'invoice'):
        print("✅ InvoiceItem has 'invoice' relationship")
    else:
        print("❌ InvoiceItem missing 'invoice' relationship!")
    
    # Check methods
    print("\n4. Checking Invoice methods...")
    required_methods = ['calculate_totals', 'update_status', 'mark_as_sent', 
                       'mark_as_paid', 'mark_as_cancelled']
    for method in required_methods:
        if hasattr(Invoice, method):
            print(f"✅ Invoice has '{method}' method")
        else:
            print(f"❌ Invoice missing '{method}' method!")
    
    print("\n5. Checking InvoiceItem methods...")
    if hasattr(InvoiceItem, 'calculate_totals'):
        print("✅ InvoiceItem has 'calculate_totals' method")
    else:
        print("❌ InvoiceItem missing 'calculate_totals' method!")
    
    # Try creating a test instance
    print("\n6. Testing model instantiation...")
    try:
        from datetime import date
        from decimal import Decimal
        import uuid
        
        # Don't save, just test instantiation
        test_invoice = Invoice(
            id=uuid.uuid4(),
            business_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            invoice_number="TEST-001",
            issue_date=date.today(),
            due_date=date.today(),
            status="DRAFT",
            subtotal=Decimal("0"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            paid_amount=Decimal("0"),
            outstanding_amount=Decimal("0")
        )
        print("✅ Invoice can be instantiated")
        
    except Exception as e:
        print(f"❌ Error instantiating Invoice: {e}")
        import traceback
        traceback.print_exc()
    
    # Check schemas
    print("\n7. Checking Pydantic schemas...")
    try:
        from app.schemas.invoice import InvoiceCreate, InvoiceResponse
        print("✅ Invoice schemas imported")
        
        # Check if they have proper config
        if hasattr(InvoiceResponse, 'model_config'):
            config = InvoiceResponse.model_config
            print(f"✅ InvoiceResponse has model_config")
            if 'from_attributes' in config:
                print(f"   from_attributes: {config['from_attributes']}")
        else:
            print("⚠️  InvoiceResponse missing model_config")
            print("   May need: model_config = ConfigDict(from_attributes=True)")
        
    except Exception as e:
        print(f"❌ Error importing schemas: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 70)
    print("  CHECK COMPLETE")
    print("=" * 70)
    print()

if __name__ == "__main__":
    try:
        check_models()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()