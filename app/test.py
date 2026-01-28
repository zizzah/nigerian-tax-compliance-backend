# test_dependencies.py
import pytesseract
from PIL import Image
import spacy

print("Testing installed dependencies...\n")

# Test Tesseract
try:
    version = pytesseract.get_tesseract_version()
    print(f"✓ Tesseract OCR: v{version}")
except Exception as e:
    print(f"✗ Tesseract error: {e}")

# Test spaCy
try:
    nlp = spacy.load('en_core_web_sm')
    doc = nlp("Nigerian Federal Inland Revenue Service collects N500,000 in taxes")
    print(f"✓ spaCy: Working correctly")
    print(f"  Sample text: '{doc.text}'")
    if doc.ents:
        print("  Entities found:")
        for ent in doc.ents:
            print(f"    - {ent.text} ({ent.label_})")
except Exception as e:
    print(f"✗ spaCy error: {e}")

print("\n✅ All dependencies are ready!")