"""Test OCR quality on your test receipt"""
from app.services.ocr.preprocessor import ImagePreprocessor
from app.services.ocr.extractor import OCRExtractor
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

print("="*80)
print("OCR QUALITY TEST")
print("="*80)

# Create a test receipt first
from PIL import Image, ImageDraw, ImageFont

def create_clear_receipt():
    """Create a very clear, high-contrast receipt"""
    width, height = 800, 1200
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font_large = ImageFont.truetype("arial.ttf", 48)
        font_medium = ImageFont.truetype("arial.ttf", 32)
        font_small = ImageFont.truetype("arial.ttf", 28)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    y = 60
    
    # Store name
    text = "ABC SUPERMARKET"
    draw.text((width//2, y), text, fill='black', font=font_large, anchor='mm')
    y += 80
    
    # Address
    draw.text((width//2, y), "123 Lagos Street Victoria Island", fill='black', font=font_small, anchor='mm')
    y += 50
    draw.text((width//2, y), "Tel 234-801-234-5678", fill='black', font=font_small, anchor='mm')
    y += 50
    draw.text((width//2, y), "TIN 12345678-0001", fill='black', font=font_small, anchor='mm')
    y += 80
    
    # Receipt details
    draw.text((100, y), "RECEIPT NO RCT-2024-001", fill='black', font=font_small)
    y += 50
    draw.text((100, y), "DATE 17/02/2024", fill='black', font=font_small)
    y += 80
    
    # Items
    items = [
        "Rice 50kg                2        12000.00",
        "Cooking Oil 5L           3         4500.00",
        "Sugar 2kg                5         2500.00",
    ]
    
    for item in items:
        draw.text((100, y), item, fill='black', font=font_small)
        y += 50
    
    y += 50
    
    # Totals
    draw.text((100, y), "SUBTOTAL                        19000.00", fill='black', font=font_medium)
    y += 60
    draw.text((100, y), "VAT 7.5%                         1425.00", fill='black', font=font_medium)
    y += 60
    draw.text((100, y), "TOTAL                           20425.00", fill='black', font=font_medium)
    y += 80
    
    draw.text((width//2, y), "Payment Method CASH", fill='black', font=font_small, anchor='mm')
    
    filename = 'test_receipt_clear.jpg'
    img.save(filename, quality=100, dpi=(300, 300))
    return filename

# Create receipt
receipt_file = create_clear_receipt()
print(f"✓ Created: {receipt_file}")

# Preprocess
print("\n📸 Preprocessing image...")
preprocessor = ImagePreprocessor()
preprocessed = preprocessor.preprocess(receipt_file)

# Run OCR
print("\n🔍 Running OCR...")
ocr = OCRExtractor()
text, confidence = ocr.extract_with_confidence(preprocessed)

print("\n" + "="*80)
print("OCR RESULTS")
print("="*80)
print(f"Confidence: {confidence:.2%}")
print(f"\nExtracted Text ({len(text)} chars):")
print("-"*80)
print(text)
print("-"*80)

# Check quality
if confidence < 0.6:
    print("\n⚠️  LOW CONFIDENCE - OCR might not be working well")
elif confidence < 0.8:
    print("\n⚠️  MEDIUM CONFIDENCE - Text might have errors")
else:
    print("\n✅ HIGH CONFIDENCE - OCR is working well")

# Save OCR text to file
with open('ocr_output.txt', 'w', encoding='utf-8') as f:
    f.write(text)
print(f"\n💾 Saved OCR text to: ocr_output.txt")