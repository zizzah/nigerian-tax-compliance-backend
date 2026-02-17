"""Test the complete pipeline: Image → OCR → Groq"""
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from app.services.ai.groq_extractor import GroqReceiptExtractor
import logging
import json

logging.basicConfig(level=logging.INFO)

print("="*80)
print("FULL PIPELINE TEST")
print("="*80)

receipt_file = 'test_receipt_clear.jpg'  # From previous test

print("\n1️⃣  Preprocessing...")
preprocessor = ImagePreprocessor()
preprocessed = preprocessor.preprocess(receipt_file)

print("\n2️⃣  OCR Extraction...")
ocr = OCRExtractor()
text, confidence = ocr.extract_with_confidence(preprocessed)
print(f"   OCR Confidence: {confidence:.2%}")
print(f"   Text Length: {len(text)} chars")

print("\n3️⃣  Groq AI Extraction...")
groq = GroqReceiptExtractor()
result = groq.extract_receipt_data(ocr_text=text)

print("\n" + "="*80)
print("FINAL RESULTS")
print("="*80)
print(json.dumps(result, indent=2, default=str))

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"✓ Vendor: {result.get('vendor_name', 'N/A')}")
print(f"✓ Total: ₦{result.get('total_amount', 0):,.2f}")
print(f"✓ VAT: ₦{result.get('vat_amount', 0):,.2f}")
print(f"✓ Items: {len(result.get('line_items', []))}")
print(f"✓ Confidence: {result.get('confidence_score', 0):.2%}")
print(f"✓ Category: {result.get('category', 'N/A')}")