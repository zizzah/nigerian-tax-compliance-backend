"""
Direct Database Invoice Creation Test
This bypasses the API to isolate where the error occurs
"""
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
import uuid

project_root = Path(__file__).parent.parent if '__file__' in globals() else Path.cwd()
sys.path.insert(0, str(project_root))

def test_direct_creation():
    print("=" * 70)
    print("  DIRECT DATABASE INVOICE CREATION TEST")
    print("=" * 70)
    print()
    
    from app.core.database import SessionLocal
    from app.models.business import Business
    from app.models.customer import Customer
    from app.models.product import Product
    from app.models.invoice import Invoice, InvoiceStatus
    from app.models.invoice_item import InvoiceItem
    
    db = SessionLocal()
    
    try:
        # Get business
        print("1. Getting business...")
        business = db.query(Business).first()
        if not business:
            print("❌ No business found")
            return
        print(f"✅ Business: {business.business_name}")
        
        # Get customer
        print("\n2. Getting customer...")
        customer = db.query(Customer).filter(Customer.business_id == business.id).first()
        if not customer:
            print("❌ No customer found")
            return
        print(f"✅ Customer: {customer.name}")
        
        # Get product
        print("\n3. Getting product...")
        product = db.query(Product).filter(Product.business_id == business.id).first()
        print(f"✅ Product: {product.name if product else 'None (will use manual item)'}")
        
        # Generate invoice number
        print("\n4. Generating invoice number...")
        invoice_number = business.get_next_invoice_number()
        print(f"✅ Invoice number: {invoice_number}")
        
        # Create invoice
        print("\n5. Creating invoice object...")
        invoice = Invoice(
            business_id=business.id,
            customer_id=customer.id,
            invoice_number=invoice_number,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            discount_amount=Decimal('0'),
            payment_terms="Payment due within 30 days",
            notes="Test invoice",
            status=InvoiceStatus.DRAFT
        )
        print("✅ Invoice object created")
        
        # Add to session and flush to get ID
        print("\n6. Adding invoice to database...")
        db.add(invoice)
        db.flush()
        print(f"✅ Invoice added, ID: {invoice.id}")
        
        # Create invoice item
        print("\n7. Creating invoice item...")
        item = InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id if product else None,
            description="Test Product - Direct Creation",
            quantity=Decimal('2'),
            unit_price=Decimal('10000'),
            discount_percent=Decimal('0'),
            tax_rate=Decimal('7.5'),
            sort_order=0
        )
        print("✅ Invoice item object created")
        
        # Calculate item totals
        print("\n8. Calculating item totals...")
        item.calculate_totals()
        print(f"✅ Line total: ₦{float(item.line_total):,.2f}")
        print(f"   Base: ₦{float(item.quantity * item.unit_price):,.2f}")
        print(f"   Tax: ₦{float(item.tax_amount):,.2f}")
        
        # Add item
        print("\n9. Adding item to database...")
        db.add(item)
        db.flush()
        print("✅ Item added")
        
        # Update product usage
        if product:
            print("\n10. Updating product usage...")
            product.increment_usage()
            print("✅ Product usage updated")
        
        # Refresh invoice to load items
        print("\n11. Refreshing invoice to load items...")
        db.refresh(invoice)
        print(f"✅ Invoice refreshed, items count: {len(invoice.items)}")
        
        # Calculate invoice totals
        print("\n12. Calculating invoice totals...")
        invoice.calculate_totals()
        print(f"✅ Totals calculated:")
        print(f"   Subtotal: ₦{float(invoice.subtotal):,.2f}")
        print(f"   Tax: ₦{float(invoice.tax_amount):,.2f}")
        print(f"   Total: ₦{float(invoice.total_amount):,.2f}")
        
        # Increment invoice counter
        print("\n13. Incrementing business invoice counter...")
        business.increment_invoice_counter()
        print(f"✅ Counter incremented to: {business.invoice_counter}")
        
        # Commit
        print("\n14. Committing transaction...")
        db.commit()
        print("✅ Transaction committed")
        
        # Try to serialize to dict
        print("\n15. Testing serialization...")
        try:
            invoice_dict = {
                "id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "total_amount": float(invoice.total_amount),
                "status": invoice.status.value,
                "items": [
                    {
                        "description": item.description,
                        "quantity": float(item.quantity),
                        "unit_price": float(item.unit_price),
                        "line_total": float(item.line_total)
                    }
                    for item in invoice.items
                ]
            }
            print("✅ Serialization successful")
            print(f"\nSerialized data:")
            import json
            print(json.dumps(invoice_dict, indent=2))
        except Exception as e:
            print(f"❌ Serialization failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 70)
        print("  ✅ DIRECT CREATION SUCCESSFUL!")
        print("=" * 70)
        print()
        print("Since direct creation works, the issue is in the API endpoint.")
        print("Let's check the endpoint code...")
        print()
        
        return invoice
        
    except Exception as e:
        print(f"\n❌ Error during creation: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return None
        
    finally:
        db.close()


def check_endpoint_code():
    """Check the invoice creation endpoint for issues"""
    print("=" * 70)
    print("  CHECKING ENDPOINT CODE")
    print("=" * 70)
    print()
    
    try:
        # Try to import the endpoint
        from app.api.v1.endpoints.invoices import create_invoice
        print("✅ Endpoint function imported")
        
        # Check the function signature
        import inspect
        sig = inspect.signature(create_invoice)
        print(f"✅ Function signature: {sig}")
        
        # Get source code
        source = inspect.getsource(create_invoice)
        
        # Check for common issues
        issues = []
        
        if "db.commit()" not in source:
            issues.append("⚠️  Missing db.commit()")
        
        if "db.refresh(invoice)" not in source:
            issues.append("⚠️  Missing db.refresh(invoice) after commit")
        
        if "calculate_totals" not in source:
            issues.append("⚠️  Missing calculate_totals() call")
        
        if "try:" not in source or "except" not in source:
            issues.append("⚠️  Missing error handling (try/except)")
        
        if issues:
            print("\n⚠️  Potential issues found:")
            for issue in issues:
                print(f"   {issue}")
        else:
            print("\n✅ No obvious issues in endpoint code")
        
        # Print the source
        print("\n" + "-" * 70)
        print("Endpoint source code:")
        print("-" * 70)
        print(source)
        print("-" * 70)
        
    except Exception as e:
        print(f"❌ Error checking endpoint: {e}")
        import traceback
        traceback.print_exc()
    
    print()


if __name__ == "__main__":
    # Test direct creation
    invoice = test_direct_creation()
    
    if invoice:
        print("\n")
        # Check endpoint code
        check_endpoint_code()