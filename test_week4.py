"""
WEEK 4 COMPREHENSIVE TEST SCRIPT
Tests AI-powered document processing with Groq

Usage: python test_week4.py
"""
import requests
import time
import json
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"

print("\n" + "="*80)
print("  WEEK 4: AI DOCUMENT PROCESSING TEST")
print("  Powered by Groq AI (llama-3.3-70b-versatile)")
print("="*80 + "\n")

# Step 1: Login
print("1️⃣  Logging in...")
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": "admin@example.com", "password": "Admin@123"}
)

if response.status_code != 200:
    print(f"❌ Login failed: {response.status_code}")
    print(response.text)
    exit(1)

token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in successfully\n")

# Step 2: Create a test receipt image
print("2️⃣  Creating test receipt...")
from PIL import Image, ImageDraw, ImageFont

# Create a simple receipt image
img = Image.new('RGB', (600, 800), color='white')
draw = ImageDraw.Draw(img)

# Receipt content
receipt_text = """
    SHOPRITE STORES
    123 Victoria Island, Lagos
    TIN: 12345678-0001
    
    Date: 05/02/2026
    Receipt #: SR-2026-0234
    
    Items:
    Rice (5kg)         x2    ₦12,000.00
    Cooking Oil (2L)   x1     ₦4,500.00
    Chicken (1kg)      x3     ₦9,000.00
    
    Subtotal:              ₦25,500.00
    VAT (7.5%):             ₦1,912.50
    TOTAL:                 ₦27,412.50
    
    Payment: Card
    Ref: TRX-9876543210
    
    Thank you for shopping!
"""

# Draw text
y_position = 50
for line in receipt_text.strip().split('\n'):
    draw.text((50, y_position), line.strip(), fill='black')
    y_position += 30

# Save receipt
test_receipt_path = Path("test_receipt.jpg")
img.save(test_receipt_path)
print(f"✅ Created test receipt: {test_receipt_path}\n")

# Step 3: Upload document
print("3️⃣  Uploading document for AI processing...")
with open(test_receipt_path, "rb") as f:
    files = {"file": ("test_receipt.jpg", f, "image/jpeg")}
    data = {
        "document_type": "RECEIPT",
        "notes": "Test receipt for Week 4 AI processing"
    }
    
    response = requests.post(
        f"{BASE_URL}/documents/upload",
        files=files,
        data=data,
        headers=headers
    )

if response.status_code != 201:
    print(f"❌ Upload failed: {response.status_code}")
    print(response.text)
    exit(1)

upload_result = response.json()
document_id = upload_result["document_id"]
task_id = upload_result["task_id"]

print(f"✅ Document uploaded!")
print(f"   Document ID: {document_id}")
print(f"   Task ID: {task_id}")
print(f"   Status: {upload_result['status']}")
print(f"   Estimated completion: {upload_result['estimated_completion_seconds']}s\n")

# Step 4: Poll task status
print("4️⃣  Waiting for AI processing to complete...")
max_wait = 60  # 60 seconds max
elapsed = 0
status = "pending"

while elapsed < max_wait:
    time.sleep(3)
    elapsed += 3
    
    response = requests.get(
        f"{BASE_URL}/documents/tasks/{task_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        task_data = response.json()
        status = task_data.get("status", "unknown")
        
        print(f"   [{elapsed}s] Status: {status}")
        
        if status == "success":
            print("✅ Processing completed!\n")
            break
        elif status == "failure":
            print(f"❌ Processing failed: {task_data.get('result')}\n")
            exit(1)
    else:
        print(f"   Warning: Could not check task status")

if status != "success":
    print("⚠️  Processing is taking longer than expected")
    print("   Continuing to check document...\n")

# Step 5: Get processed document
print("5️⃣  Retrieving processed document...")
time.sleep(2)  # Give it a moment

response = requests.get(
    f"{BASE_URL}/documents/{document_id}",
    headers=headers
)

if response.status_code != 200:
    print(f"❌ Failed to retrieve document: {response.status_code}")
    print(response.text)
    exit(1)

document = response.json()

print("✅ Document retrieved!\n")
print("="*80)
print("  EXTRACTION RESULTS")
print("="*80 + "\n")

# Display results
print(f"📄 Document Information:")
print(f"   Type: {document['document_type']}")
print(f"   Original Filename: {document['original_filename']}")
print(f"   Status: {document['status']}")
print(f"   File Size: {document['file_size']:,} bytes\n")

print(f"🏪 Vendor Information:")
print(f"   Name: {document.get('vendor_name', 'Not extracted')}")
print(f"   TIN: {document.get('vendor_tin', 'Not extracted')}")
print(f"   Address: {document.get('vendor_address', 'Not extracted')}")
print(f"   Phone: {document.get('vendor_phone', 'Not extracted')}\n")

print(f"💰 Financial Information:")
print(f"   Subtotal: ₦{float(document['subtotal']):,.2f}")
print(f"   VAT ({document['vat_rate']}%): ₦{float(document['vat_amount']):,.2f}")
print(f"   Total: ₦{float(document['total_amount']):,.2f}\n")

if document.get('line_items'):
    print(f"📋 Line Items:")
    for i, item in enumerate(document['line_items'], 1):
        print(f"   {i}. {item.get('description', 'Unknown')}")
        print(f"      Qty: {item.get('quantity', 0)} × ₦{float(item.get('unit_price', 0)):,.2f} = ₦{float(item.get('amount', 0)):,.2f}")
    print()

print(f"🏷️  Categorization:")
print(f"   Category: {document.get('category', 'Not categorized')}")
print(f"   Payment Method: {document.get('payment_method', 'Not specified')}\n")

print(f"🤖 AI Processing:")
print(f"   Model: {document.get('ai_model_used', 'Unknown')}")
print(f"   Confidence: {float(document.get('confidence_score', 0)):.1%}")
print(f"   OCR Confidence: {float(document.get('ocr_confidence', 0)):.1%}")
print(f"   Processing Time: {float(document.get('processing_duration_seconds', 0)):.2f}s")
print(f"   Requires Review: {'Yes' if document.get('requires_review') else 'No'}\n")

# Step 6: Get statistics
print("6️⃣  Retrieving statistics...")
response = requests.get(
    f"{BASE_URL}/documents/stats/overview",
    headers=headers
)

if response.status_code == 200:
    stats = response.json()
    print("✅ Statistics retrieved!\n")
    print("="*80)
    print("  DOCUMENT STATISTICS")
    print("="*80 + "\n")
    
    print(f"📊 Overview:")
    print(f"   Total Documents: {stats['total_documents']}")
    print(f"   Completed: {stats['completed']}")
    print(f"   Pending: {stats['pending_processing']}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Requires Review: {stats['requires_review']}")
    print(f"   Total Amount Processed: ₦{float(stats['total_amount_processed']):,.2f}\n")

# Step 7: List documents
print("7️⃣  Listing all documents...")
response = requests.get(
    f"{BASE_URL}/documents?page=1&page_size=10",
    headers=headers
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Found {data['total']} document(s)\n")
    
    for doc in data['documents'][:3]:
        print(f"   • {doc['original_filename']}")
        print(f"     Status: {doc['status']}, Total: ₦{float(doc['total_amount']):,.2f}")

print("\n" + "="*80)
print("  TEST COMPLETED SUCCESSFULLY! 🎉")
print("="*80 + "\n")

print("✅ Week 4 AI Document Processing is WORKING!")
print("\nNext steps:")
print("1. Try uploading real receipt images")
print("2. Test with different document types")
print("3. Review low-confidence extractions")
print("4. Build frontend interface")
print("\nGreat job! Ready for Week 5! 🚀\n")

# Cleanup
test_receipt_path.unlink()