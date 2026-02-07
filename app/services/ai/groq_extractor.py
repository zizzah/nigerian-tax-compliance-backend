"""
AI-Powered Receipt Data Extraction using Groq (llama-3.3-70b-versatile)
Location: app/services/ai/groq_extractor.py

Groq provides FAST and COST-EFFECTIVE AI inference
- 10x faster than OpenAI
- 90% cheaper than Claude
- Perfect for document processing
"""
from groq import Groq # type: ignore
from typing import Dict, Any, Optional, List
import json
import logging
from decimal import Decimal
from datetime import datetime, date
import base64
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqReceiptExtractor:
    """
    Extract structured data from receipts using Groq's llama-3.3-70b-versatile
    
    This is the core AI service that makes the platform intelligent.
    
    Why Groq?
    - Lightning fast inference (10x faster than GPT-4)
    - Very cost-effective (90% cheaper)
    - High quality with llama-3.3-70b
    - Perfect for production document processing
    """
    
    def __init__(self):
        """Initialize Groq client"""
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = "llama-3.3-70b-versatile"  # Best model for document extraction
    
    def extract_receipt_data(
        self,
        ocr_text: str,
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from receipt OCR text
        
        Note: Groq currently doesn't support vision, so we use OCR text
        This is actually FASTER and often more accurate!
        
        Args:
            ocr_text: OCR-extracted text from document
            image_path: Optional path to original image (for future vision support)
            
        Returns:
            Structured receipt data as dictionary
        """
        try:
            logger.info("Starting Groq AI extraction...")
            
            # Build extraction prompt
            prompt = self._build_extraction_prompt(ocr_text)
            
            # Call Groq API
            start_time = datetime.now()
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting structured data from Nigerian business receipts and invoices. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000,
                top_p=1,
                stream=False
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Groq processing completed in {processing_time:.2f} seconds")
            
            # Extract response
            response_text = response.choices[0].message.content
            
            # Parse JSON
            if not response_text:
                raise ValueError("Groq returned empty response")
            extracted_data = self._parse_response(response_text)
            
            # Validate and clean data
            validated_data = self._validate_data(extracted_data)
            
            # Add metadata
            validated_data['_meta'] = {
                'model': self.model,
                'processing_time_seconds': processing_time,
                'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') and response.usage is not None else None
            }
            
            logger.info(f"Successfully extracted receipt data: {validated_data.get('vendor_name', 'Unknown')}")
            
            return validated_data
            
        except Exception as e:
            logger.error(f"Groq extraction failed: {e}")
            raise
    
    def _build_extraction_prompt(self, ocr_text: str) -> str:
        """
        Build comprehensive prompt for Groq
        
        This prompt is CRITICAL - it determines extraction quality
        """
        prompt = f"""Extract structured data from this Nigerian business receipt/invoice.

OCR TEXT:
```
{ocr_text[:3000]}  # Limit to avoid token limits
```

Extract the following information and return ONLY valid JSON:

{{
  "vendor_name": "Business name",
  "vendor_tin": "Tax Identification Number (if visible)",
  "vendor_address": "Full address",
  "vendor_phone": "Phone number",
  
  "document_type": "RECEIPT or INVOICE",
  "document_number": "Receipt/Invoice number",
  "document_date": "YYYY-MM-DD format",
  
  "line_items": [
    {{
      "description": "Item description",
      "quantity": 1.0,
      "unit_price": 0.00,
      "amount": 0.00
    }}
  ],
  
  "subtotal": 0.00,
  "vat_amount": 0.00,
  "vat_rate": 7.5,
  "total_amount": 0.00,
  
  "payment_method": "Cash/Card/Transfer/POS/Other",
  "payment_reference": "Transaction reference if available",
  
  "category": "Office Supplies/Utilities/Transportation/Meals/Equipment/Services/Other",
  "confidence_score": 0.95
}}

CRITICAL INSTRUCTIONS:

1. **Nigerian Context:**
   - VAT rate in Nigeria is 7.5% (use this if not explicitly stated)
   - Currency is Nigerian Naira (₦)
   - Common formats: DD/MM/YYYY or DD-MM-YYYY for dates

2. **Number Extraction:**
   - Extract ALL numeric amounts as numbers (not strings)
   - Remove currency symbols (₦, N, NGN)
   - Remove thousand separators (commas)
   - Examples: "₦450,000.00" → 450000.00, "N 1,200" → 1200.00

3. **Date Formats:**
   - Convert to YYYY-MM-DD format
   - Common Nigerian formats: DD/MM/YYYY, DD-MM-YYYY

4. **Line Items:**
   - Extract each item separately
   - Calculate amount = quantity × unit_price
   - If quantity not shown, assume 1

5. **Validation:**
   - Verify: subtotal + vat_amount ≈ total_amount (within ±1 due to rounding)
   - If VAT not shown but total suggests it's included, calculate: subtotal × 0.075
   - If you can't find subtotal, calculate: total_amount / 1.075

6. **Confidence Score:**
   - Rate your confidence in the extraction (0.0 to 1.0)
   - Factors: Text clarity, completeness, ambiguity
   - Be honest - low confidence triggers human review
   - < 0.7 = requires review

7. **Missing Data:**
   - Use null for missing fields
   - Don't make up data
   - Don't include fields you're unsure about

RETURN ONLY THE JSON OBJECT - NO MARKDOWN, NO EXPLANATIONS, NO PREAMBLE.
Start with {{ and end with }}"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse Groq's JSON response
        
        Handles markdown code blocks and cleanup
        """
        # Remove markdown code blocks if present
        text = response_text.strip()
        
        # Remove various markdown patterns
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        # Parse JSON
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Response text: {text[:500]}")
            
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data
                except:
                    pass
            
            raise ValueError("Groq did not return valid JSON")
    
    def _validate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean extracted data
        
        Ensures data integrity before saving to database
        """
        validated = data.copy()
        
        # Convert date string to date object
        if validated.get('document_date'):
            try:
                date_str = validated['document_date']
                if isinstance(date_str, str):
                    validated['document_date'] = datetime.strptime(
                        date_str, '%Y-%m-%d'
                    ).date()
            except Exception as e:
                logger.warning(f"Date parsing failed: {e}")
                validated['document_date'] = None
        
        # Ensure numeric fields are Decimal
        numeric_fields = ['subtotal', 'vat_amount', 'total_amount', 'vat_rate', 'confidence_score']
        for field in numeric_fields:
            if field in validated and validated[field] is not None:
                try:
                    validated[field] = Decimal(str(validated[field]))
                except:
                    logger.warning(f"Could not convert {field} to Decimal")
                    validated[field] = Decimal('0')
        
        # Validate line items
        if validated.get('line_items'):
            cleaned_items = []
            for item in validated['line_items']:
                try:
                    cleaned_item = {
                        'description': str(item.get('description', 'Unknown Item')),
                        'quantity': Decimal(str(item.get('quantity', 1))),
                        'unit_price': Decimal(str(item.get('unit_price', 0))),
                        'amount': Decimal(str(item.get('amount', 0)))
                    }
                    cleaned_items.append(cleaned_item)
                except Exception as e:
                    logger.warning(f"Failed to parse line item: {e}")
            validated['line_items'] = cleaned_items
        
        # Set default confidence score if missing
        if 'confidence_score' not in validated or validated['confidence_score'] is None:
            validated['confidence_score'] = Decimal('0.5')
        
        # Flag for review if confidence is low
        confidence = float(validated.get('confidence_score', 0))
        validated['requires_review'] = confidence < 0.7
        
        # Validate financial calculations
        subtotal = float(validated.get('subtotal', 0))
        vat = float(validated.get('vat_amount', 0))
        total = float(validated.get('total_amount', 0))
        
        # Check if calculations are consistent (within ±2 for rounding)
        if abs((subtotal + vat) - total) > 2:
            logger.warning(f"Financial calculation mismatch: {subtotal} + {vat} ≠ {total}")
            validated['requires_review'] = True
        
        return validated
    
    def categorize_expense(self, description: str, vendor_name: str = "") -> str:
        """
        Auto-categorize expense based on description and vendor
        
        Uses Groq for intelligent categorization
        
        Args:
            description: Item description or transaction description
            vendor_name: Vendor name (optional)
            
        Returns:
            Category name
        """
        try:
            prompt = f"""Categorize this Nigerian business expense into ONE category:

Vendor: {vendor_name or 'Unknown'}
Description: {description}

Categories:
- Office Supplies
- Utilities (Electricity, Water, Internet)
- Transportation (Fuel, Taxi, Logistics)
- Meals & Entertainment
- Equipment & Hardware
- Software & Subscriptions
- Professional Services
- Marketing & Advertising
- Rent & Facilities
- Salaries & Wages
- Maintenance & Repairs
- Insurance
- Other

Return ONLY the category name, nothing else."""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a business expense categorization expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            category = response.choices[0].message.content
            if category is None:
                return "Other"
            category = category.strip()
            
            logger.info(f"Categorized as: {category}")
            
            return category
            
        except Exception as e:
            logger.error(f"Categorization failed: {e}")
            return "Other"
    
    def extract_vendor_from_text(self, text: str) -> Optional[str]:
        """
        Extract vendor name from text when it's not clearly labeled
        
        Args:
            text: OCR text
            
        Returns:
            Vendor name or None
        """
        try:
            prompt = f"""Extract the business/vendor name from this receipt text.

Text:
{text[:500]}

Return ONLY the business name, nothing else. If you can't find it, return "Unknown"."""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            vendor = response.choices[0].message.content
            if vendor is None:
                return None
            vendor = vendor.strip()
            
            if vendor.lower() == "unknown":
                return None
            
            return vendor
            
        except Exception as e:
            logger.error(f"Vendor extraction failed: {e}")
            return None