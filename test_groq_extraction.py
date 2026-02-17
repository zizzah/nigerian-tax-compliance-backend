"""Test just the Groq extraction part"""
import logging
from app.services.ai.groq_extractor import GroqReceiptExtractor

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Sample OCR text (realistic Nigerian receipt)
sample_ocr = """
ABC SUPERMARKET
123 Lagos Street, Victoria Island
Tel: +234-801-234-5678
TIN: 12345678-0001

RECEIPT NO: RCT-2024-001
DATE: 17/02/2024

ITEM                QTY    PRICE
Rice (50kg)         2      ₦12,000.00
Cooking Oil (5L)    3      ₦4,500.00
Sugar (2kg)         5      ₦2,500.00

SUBTOTAL:                  ₦19,000.00
VAT (7.5%):                ₦1,425.00
TOTAL:                     ₦20,425.00

Payment Method: CASH
Thank you!
"""

print("="*80)
print("GROQ EXTRACTION TEST")
print("="*80)
print(f"\nInput OCR text ({len(sample_ocr)} chars):")
print(sample_ocr)
print("\n" + "="*80 + "\n")

try:
    extractor = GroqReceiptExtractor()
    result = extractor.extract_receipt_data(sample_ocr)
    
    print("✅ Extraction successful!")
    print("\n" + "="*80)
    print("EXTRACTED DATA")
    print("="*80)
    
    import json
    print(json.dumps(result, indent=2, default=str))
    
    print("\n" + "="*80)
    print("KEY FIELDS")
    print("="*80)
    print(f"Vendor Name: {result.get('vendor_name')}")
    print(f"Total Amount: ₦{result.get('total_amount', 0):,.2f}")
    print(f"VAT Amount: ₦{result.get('vat_amount', 0):,.2f}")
    print(f"Confidence: {result.get('confidence_score', 0):.2%}")
    print(f"Line Items: {len(result.get('line_items', []))}")
    
except Exception as e:
    print(f"❌ Extraction failed: {e}")
    import traceback
    traceback.print_exc()