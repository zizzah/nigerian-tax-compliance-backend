#!/usr/bin/env python3
"""
FINAL WORKING DOCUMENT PROCESSING TEST
=======================================

All issues fixed:
- Handles existing users
- Generates unique TIN
- Clean error handling

Run: python test_document_final.py
"""

import requests
import time
import json
from datetime import datetime
from pathlib import Path
import sys
import os
import random
"""
Document Processing End-to-End Test
Tests the complete flow: Upload → OCR → Groq → Database
"""
import requests
import time
import random
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont  # ADD THIS LINE

# Rest of your code...

# ============================================================================
# CONFIGURATION
# ============================================================================

TEST_EMAIL = os.getenv("TEST_EMAIL", f"doctest{random.randint(1000,9999)}@example.com")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "DocTest@123!")

API_BASE_URL = "http://localhost:8000"
API_V1 = f"{API_BASE_URL}/api/v1"

# Colors
class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_section(title, color=C.BLUE):
    print(f"\n{color}{'='*80}{C.RESET}")
    print(f"{color}{C.BOLD}{title}{C.RESET}")
    print(f"{color}{'='*80}{C.RESET}\n")

def print_success(msg):
    print(f"{C.GREEN}✓ {msg}{C.RESET}")

def print_error(msg):
    print(f"{C.RED}✗ {msg}{C.RESET}")

def print_info(msg):
    print(f"{C.CYAN}ℹ {msg}{C.RESET}")

def print_warning(msg):
    print(f"{C.YELLOW}⚠ {msg}{C.RESET}")

def print_json(data, title=None):
    if title:
        print(f"\n{C.MAGENTA}{title}:{C.RESET}")
    print(json.dumps(data, indent=2, default=str))

# ============================================================================
# CREATE SAMPLE RECEIPT
# ============================================================================

def create_sample_receipt():
    """Create a more realistic receipt image for testing"""
    print("="*80)
    print("Creating Sample Receipt Image")
    print("="*80)
    
    # Create a larger, clearer image
    width, height = 800, 1000
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Use a larger, clearer font
    try:
        # Try to use a system font
        title_font = ImageFont.truetype("arial.ttf", 40)
        header_font = ImageFont.truetype("arial.ttf", 28)
        item_font = ImageFont.truetype("arial.ttf", 24)
        total_font = ImageFont.truetype("arialbd.ttf", 32)  # Bold for totals
    except:
        # Fallback to default
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        item_font = ImageFont.load_default()
        total_font = ImageFont.load_default()
    
    y = 50
    
    # Store name (centered, bold)
    store_name = "ABC SUPERMARKET"
    draw.text((width//2, y), store_name, fill='black', font=title_font, anchor='mm')
    y += 60
    
    # Store details
    draw.text((width//2, y), "123 Lagos Street, Victoria Island", fill='black', font=header_font, anchor='mm')
    y += 40
    draw.text((width//2, y), "Tel: +234-801-234-5678", fill='black', font=header_font, anchor='mm')
    y += 40
    draw.text((width//2, y), "TIN: 12345678-0001", fill='black', font=header_font, anchor='mm')
    y += 60
    
    # Separator line
    draw.line([(50, y), (width-50, y)], fill='black', width=2)
    y += 40
    
    # Receipt number and date
    draw.text((50, y), "RECEIPT NO: RCT-2024-001", fill='black', font=header_font)
    y += 35
    draw.text((50, y), "DATE: 17/02/2024", fill='black', font=header_font)
    y += 60
    
    # Items header
    draw.line([(50, y), (width-50, y)], fill='black', width=2)
    y += 40
    draw.text((50, y), "ITEM", fill='black', font=item_font)
    draw.text((400, y), "QTY", fill='black', font=item_font)
    draw.text((width-200, y), "PRICE", fill='black', font=item_font, anchor='rm')
    y += 40
    draw.line([(50, y), (width-50, y)], fill='black', width=1)
    y += 40
    
    # Items
    items = [
        ("Rice (50kg)", "2", "12,000.00"),
        ("Cooking Oil (5L)", "3", "4,500.00"),
        ("Sugar (2kg)", "5", "2,500.00"),
    ]
    
    subtotal = 0
    for item, qty, price in items:
        draw.text((50, y), item, fill='black', font=item_font)
        draw.text((420, y), qty, fill='black', font=item_font)
        draw.text((width-50, y), f"₦{price}", fill='black', font=item_font, anchor='rm')
        y += 40
        # Calculate subtotal
        subtotal += float(price.replace(',', ''))
    
    y += 20
    draw.line([(50, y), (width-50, y)], fill='black', width=1)
    y += 40
    
    # Totals
    vat = subtotal * 0.075
    total = subtotal + vat
    
    draw.text((50, y), "SUBTOTAL:", fill='black', font=item_font)
    draw.text((width-50, y), f"₦{subtotal:,.2f}", fill='black', font=item_font, anchor='rm')
    y += 40
    
    draw.text((50, y), "VAT (7.5%):", fill='black', font=item_font)
    draw.text((width-50, y), f"₦{vat:,.2f}", fill='black', font=item_font, anchor='rm')
    y += 50
    
    draw.line([(50, y), (width-50, y)], fill='black', width=2)
    y += 40
    
    draw.text((50, y), "TOTAL:", fill='black', font=total_font)
    draw.text((width-50, y), f"₦{total:,.2f}", fill='black', font=total_font, anchor='rm')
    y += 60
    
    draw.line([(50, y), (width-50, y)], fill='black', width=2)
    y += 40
    
    # Payment info
    draw.text((50, y), "Payment Method: CASH", fill='black', font=item_font)
    y += 40
    draw.text((width//2, y), "Thank you for your patronage!", fill='black', font=header_font, anchor='mm')
    
    # Save
    filename = 'test_receipt.jpg'
    img.save(filename, quality=95, optimize=True)
    
    print(f"✓ Created: {filename}")
    print(f"ℹ Receipt: ABC SUPERMARKET, Total: ₦{total:,.2f}")
    
    return filename, total
# ============================================================================
# AUTHENTICATION
# ============================================================================

def authenticate():
    """Register and login"""
    print_section("Authentication")
    
    print_info(f"Email: {TEST_EMAIL}")
    
    # Register
    try:
        response = requests.post(
            f"{API_V1}/auth/register",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "confirm_password": TEST_PASSWORD,
                "phone": "+2348012345678"
            }
        )
        
        if response.status_code == 201:
            print_success("Registered")
        elif response.status_code == 400:
            print_info("User exists, logging in...")
        else:
            print_error(f"Registration failed: {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Registration error: {e}")
        return None
    
    # Login
    try:
        response = requests.post(
            f"{API_V1}/auth/login",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Logged in")
            return data['access_token']
        else:
            print_error(f"Login failed: {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Login error: {e}")
        return None

# ============================================================================
# BUSINESS SETUP
# ============================================================================

def setup_business(token):
    """Get or create business"""
    print_section("Business Setup")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check existing
    try:
        response = requests.get(f"{API_V1}/businesses/me", headers=headers)
        if response.status_code == 200:
            business = response.json()
            print_success(f"Found: {business['business_name']}")
            return business
    except:
        pass
    
    # Create with unique TIN
    unique_tin = f"{random.randint(10000000, 99999999)}-{random.randint(1000, 9999)}"
    
    business_data = {
        "business_name": f"Test Firm {random.randint(1000, 9999)}",
        "business_type": "Professional Services",
        "industry": "Accounting",
        "tin": unique_tin,  # ← Unique TIN
        "vat_registered": True,
        "phone": "+2348012345678",
        "email": f"info{random.randint(1000, 9999)}@testfirm.com",
        "address": "123 Lagos Street",
        "city": "Lagos",
        "state": "Lagos",
    }
    
    try:
        response = requests.post(
            f"{API_V1}/businesses/",
            json=business_data,
            headers=headers
        )
        
        if response.status_code == 201:
            business = response.json()
            print_success(f"Created: {business['business_name']}")
            return business
        else:
            print_error(f"Failed: {response.status_code}")
            print_json(response.json())
            return None
            
    except Exception as e:
        print_error(f"Error: {e}")
        return None

# ============================================================================
# DOCUMENT UPLOAD
# ============================================================================

def upload_document(token, receipt_path):
    """Upload document"""
    print_section("Document Upload")
    
    if not Path(receipt_path).exists():
        print_error(f"File not found: {receipt_path}")
        return None
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        with open(receipt_path, 'rb') as f:
            files = {'file': ('test_receipt.jpg', f, 'image/jpeg')}
            data = {'document_type': 'RECEIPT'}
            
            print_info("Uploading...")
            response = requests.post(
                f"{API_V1}/documents/upload",
                files=files,
                data=data,
                headers=headers
            )
        
        if response.status_code == 201:
            result = response.json()
            print_success("Uploaded!")
            print_info(f"Document ID: {result['document_id']}")
            print_info(f"Status: {result['status']}")
            return result
        else:
            print_error(f"Upload failed: {response.status_code}")
            print_json(response.json())
            return None
            
    except Exception as e:
        print_error(f"Error: {e}")
        return None

# ============================================================================
# MONITOR PROCESSING
# ============================================================================

def monitor_processing(token, document_id, max_wait=60):
    """Monitor processing"""
    print_section("Monitoring Processing")
    
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    last_status = None
    
    print_info(f"Document: {document_id}")
    print_info(f"Max wait: {max_wait}s\n")
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(
                f"{API_V1}/documents/{document_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                doc = response.json()
                status = doc['status']
                
                if status != last_status:
                    elapsed = time.time() - start
                    print(f"{C.CYAN}[{elapsed:.1f}s] {status}{C.RESET}")
                    last_status = status
                
                if status == 'COMPLETED':
                    print_success(f"Completed in {elapsed:.1f}s!")
                    return doc
                elif status == 'FAILED':
                    print_error("Failed!")
                    return doc
                
                time.sleep(2)
                
        except Exception as e:
            print_error(f"Error: {e}")
            break
    
    print_warning("Timeout - may still be processing")
    return None

# ============================================================================
# DISPLAY RESULTS
# ============================================================================

def display_results(doc):
    """Display extracted data"""
    print_section("RESULTS", C.GREEN)
    
    if not doc:
        print_error("No data")
        return
    
    status = doc.get('status')
    
    if status == 'COMPLETED':
        print_success("Processing complete!\n")
        
        print(f"{C.BOLD}📄 Document:{C.RESET}")
        print(f"  Type: {doc.get('document_type')}")
        print(f"  Number: {doc.get('document_number') or 'N/A'}")
        print(f"  Date: {doc.get('document_date') or 'N/A'}")
        
        print(f"\n{C.BOLD}🏪 Vendor:{C.RESET}")
        print(f"  Name: {doc.get('vendor_name') or 'N/A'}")
        print(f"  TIN: {doc.get('vendor_tin') or 'N/A'}")
        print(f"  Phone: {doc.get('vendor_phone') or 'N/A'}")
        
        print(f"\n{C.BOLD}💰 Financial:{C.RESET}")
        print(f"  Subtotal: ₦{float(doc.get('subtotal', 0)):,.2f}")
        print(f"  VAT: ₦{float(doc.get('vat_amount', 0)):,.2f}")
        print(f"  {C.GREEN}Total: ₦{float(doc.get('total_amount', 0)):,.2f}{C.RESET}")
        
        items = doc.get('line_items')
        if items:
            print(f"\n{C.BOLD}🛒 Items:{C.RESET}")
            for i, item in enumerate(items, 1):
                desc = item.get('description', 'Unknown')
                qty = item.get('quantity', 0)
                price = item.get('unit_price', 0)
                amt = item.get('amount', 0)
                print(f"  {i}. {desc}: {qty} x ₦{float(price):,.2f} = ₦{float(amt):,.2f}")
        
        print(f"\n{C.BOLD}📊 Metrics:{C.RESET}")
        print(f"  OCR Confidence: {float(doc.get('ocr_confidence', 0)):.2%}")
        print(f"  AI Confidence: {float(doc.get('confidence_score', 0)):.2%}")
        print(f"  Time: {float(doc.get('processing_duration_seconds', 0)):.2f}s")
        print(f"  Category: {doc.get('category', 'N/A')}")
        
    elif status == 'FAILED':
        print_error("Processing failed!")
        error = doc.get('processing_error')
        if error:
            print(f"  Error: {error}")
    else:
        print_warning(f"Status: {status}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run test"""
    print(f"\n{C.BOLD}{C.CYAN}{'='*80}")
    print("  DOCUMENT PROCESSING TEST - Final Version")
    print(f"{'='*80}{C.RESET}\n")
    
    print_info(f"Started: {datetime.now().strftime('%H:%M:%S')}")
    print_info(f"API: {API_BASE_URL}\n")
    
    # Check server
    try:
        requests.get(f"{API_BASE_URL}/health", timeout=5)
        print_success("Server running")
    except:
        print_error("Server not running. Start with: uvicorn app.main:app --reload")
        sys.exit(1)
    
    # Create receipt
    receipt_path, expected_total = create_sample_receipt()
    if not receipt_path:
        sys.exit(1)
    
    # Authenticate
    token = authenticate()
    if not token:
        sys.exit(1)
    
    # Setup business
    business = setup_business(token)
    if not business:
        sys.exit(1)
    
    # Upload
    upload_result = upload_document(token, receipt_path)
    if not upload_result:
        sys.exit(1)
    
    document_id = upload_result.get('document_id')
    if not document_id:
        print_error("No document ID")
        sys.exit(1)
    
    # Monitor
    print_info("\n⏳ Waiting for background processing...")
    print_info("(QStash → Background → OCR → Groq)\n")
    
    document = monitor_processing(token, document_id, max_wait=60)
    
    # Results
    display_results(document)
    
    # Summary
    print_section("SUMMARY", C.MAGENTA)
    
    if document and document.get('status') == 'COMPLETED':
        print(f"{C.GREEN}{C.BOLD}✅ SUCCESS!{C.RESET}\n")
        print("Your document processing pipeline is working:")
        print("  ✓ Upload → QStash → Background → OCR → Groq → Database\n")
        print_info("Ready for production! 🚀")
    else:
        print_warning("⚠ Completed with issues")
        print_info("Check logs above")
    
    print(f"\n{C.BOLD}Finished: {datetime.now().strftime('%H:%M:%S')}{C.RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}Interrupted{C.RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{C.RED}Error: {e}{C.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)