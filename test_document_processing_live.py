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
    """Create a sample receipt image"""
    print_section("Creating Sample Receipt Image", C.CYAN)
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        width, height = 600, 800
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        try:
            font_large = ImageFont.truetype("arial.ttf", 24)
            font_medium = ImageFont.truetype("arial.ttf", 18)
            font_small = ImageFont.truetype("arial.ttf", 14)
        except:
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
                font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
        
        y = 40
        draw.text((150, y), "ABC SUPERMARKET", fill='black', font=font_large)
        y += 40
        draw.text((120, y), "123 Lagos Street, Victoria Island", fill='black', font=font_small)
        y += 25
        draw.text((200, y), "Tel: 080-1234-5678", fill='black', font=font_small)
        y += 25
        draw.text((220, y), "TIN: 12345678-0001", fill='black', font=font_small)
        y += 40
        draw.line([(50, y), (550, y)], fill='black', width=2)
        y += 30
        draw.text((50, y), f"Date: {datetime.now().strftime('%d/%m/%Y')}", fill='black', font=font_small)
        draw.text((350, y), "Receipt: R-001234", fill='black', font=font_small)
        y += 30
        draw.text((50, y), "Cashier: John Doe", fill='black', font=font_small)
        y += 40
        draw.text((50, y), "ITEMS:", fill='black', font=font_medium)
        y += 35
        
        items = [
            ("Rice (5kg)", "2", "3,500", "7,000"),
            ("Cooking Oil", "1", "2,500", "2,500"),
            ("Sugar (2kg)", "1", "1,500", "1,500"),
            ("Tomato Paste", "3", "800", "2,400"),
        ]
        
        for item, qty, price, total in items:
            draw.text((50, y), item, fill='black', font=font_small)
            draw.text((280, y), qty, fill='black', font=font_small)
            draw.text((340, y), f"x {price}", fill='black', font=font_small)
            draw.text((460, y), f"= {total}", fill='black', font=font_small)
            y += 25
        
        y += 20
        draw.line([(50, y), (550, y)], fill='black', width=1)
        y += 25
        draw.text((300, y), "Subtotal:", fill='black', font=font_small)
        draw.text((460, y), "13,400", fill='black', font=font_small)
        y += 25
        draw.text((300, y), "VAT (7.5%):", fill='black', font=font_small)
        draw.text((460, y), "1,005", fill='black', font=font_small)
        y += 30
        draw.line([(300, y), (550, y)], fill='black', width=2)
        y += 25
        draw.text((300, y), "TOTAL:", fill='black', font=font_large)
        draw.text((460, y), "NGN 14,405", fill='black', font=font_large)
        y += 50
        draw.line([(50, y), (550, y)], fill='black', width=2)
        y += 30
        draw.text((50, y), "Payment Method: Cash", fill='black', font=font_small)
        y += 25
        draw.text((50, y), "Amount Paid: NGN 15,000", fill='black', font=font_small)
        y += 25
        draw.text((50, y), "Change: NGN 595", fill='black', font=font_small)
        y += 40
        draw.line([(50, y), (550, y)], fill='black', width=2)
        y += 30
        draw.text((150, y), "THANK YOU FOR YOUR PATRONAGE", fill='black', font=font_medium)
        
        receipt_path = Path("test_receipt.jpg")
        img.save(receipt_path, 'JPEG', quality=95)
        
        print_success(f"Created: {receipt_path}")
        print_info("Receipt: ABC Supermarket, Total: ₦14,405")
        
        return str(receipt_path)
        
    except ImportError:
        print_error("PIL not installed. Run: pip install pillow")
        return None
    except Exception as e:
        print_error(f"Error: {e}")
        return None

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
    receipt_path = create_sample_receipt()
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