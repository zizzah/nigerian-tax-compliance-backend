"""
AI-Powered Receipt Data Extraction using Groq (llama-3.3-70b-versatile)
Location: app/services/ai/groq_extractor.py
"""
from groq import Groq  # type: ignore
from typing import Dict, Any, Optional
import json
import re
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fields that must be Decimal for the Receipt model
_NUMERIC_FIELDS = ("subtotal", "vat_amount", "total_amount", "vat_rate", "confidence_score")

# Confidence below this triggers human review
_REVIEW_THRESHOLD = 0.7


class GroqReceiptExtractor:

    def __init__(self) -> None:
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model  = "llama-3.3-70b-versatile"

    # ── Public ────────────────────────────────────────────────────────────────

    def extract_receipt_data(self, ocr_text: str) -> Dict[str, Any]:
        """
        Extract structured data from receipt OCR text.
        Returns a dict shaped for the Receipt model.
        Raises on unrecoverable failure — caller handles the exception.
        """
        logger.info("Starting Groq receipt extraction")
        start = datetime.now()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at extracting structured data from "
                        "Nigerian business receipts and invoices. "
                        "You always return valid JSON with no markdown, no preamble."
                    ),
                },
                {"role": "user", "content": self._build_prompt(ocr_text)},
            ],
            temperature=0.1,
            max_tokens=2000,
            top_p=1,
            stream=False,
        )

        elapsed = (datetime.now() - start).total_seconds()
        logger.info("Groq responded in %.2fs", elapsed)

        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("Groq returned an empty response")

        extracted = self._parse_json(raw)
        validated = self._validate(extracted)

        validated["_meta"] = {
            "model": self.model,
            "processing_time_seconds": elapsed,
            "tokens_used": (
                response.usage.total_tokens
                if response.usage is not None
                else None
            ),
        }

        logger.info("Extraction complete — vendor: %s", validated.get("vendor_name", "Unknown"))
        return validated

    def categorize_expense(self, description: str, vendor_name: str = "") -> str:
        """
        Categorize a single expense line.
        Returns 'Other' on any failure — never raises.
        """
        prompt = f"""Categorize this Nigerian business expense into ONE category.

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

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a business expense categorization expert.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=50,
            )
            result = (response.choices[0].message.content or "").strip()
            return result if result else "Other"
        except Exception as e:
            logger.error("Categorization failed: %s", e)
            return "Other"

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(self, ocr_text: str) -> str:
        # Truncate BEFORE the f-string — never put comments inside f-string expressions
        truncated = ocr_text[:3000]

        return f"""Extract structured data from this Nigerian business receipt/invoice.

OCR TEXT:
{truncated}

Return ONLY a valid JSON object — no markdown, no explanation, no preamble.
Start with {{ and end with }}

{{
  "vendor_name": "Business name or null",
  "vendor_tin": "Tax Identification Number or null",
  "vendor_address": "Full address or null",
  "vendor_phone": "Phone number or null",

  "document_type": "RECEIPT or INVOICE",
  "document_number": "Receipt/Invoice number or null",
  "document_date": "YYYY-MM-DD or null",

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

  "payment_method": "Cash/Card/Transfer/POS/Other or null",
  "payment_reference": "Transaction reference or null",

  "category": "Office Supplies/Utilities/Transportation/Meals/Equipment/Services/Other",
  "confidence_score": 0.95
}}

RULES:
1. Nigerian VAT rate is 7.5% — use this if not explicitly stated.
2. All amounts must be plain numbers — no ₦ symbol, no commas.
   Examples: "₦450,000.00" → 450000.00 | "N 1,200" → 1200.00
3. Dates must be YYYY-MM-DD. Convert DD/MM/YYYY or DD-MM-YYYY if needed.
4. line_items: extract each item separately. amount = quantity × unit_price.
   If quantity is not shown, assume 1.
5. Verify: subtotal + vat_amount ≈ total_amount (±1 rounding tolerance).
   If VAT is missing: vat_amount = subtotal × 0.075
   If subtotal is missing: subtotal = total_amount / 1.075
6. confidence_score: 0.0–1.0. Be honest — below 0.7 triggers human review.
7. Use null for any field you cannot find. Do not invent data."""

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """
        Strip markdown fences and parse JSON.
        Falls back to regex extraction if the model wraps output unexpectedly.
        Raises ValueError if no valid JSON can be found.
        """
        cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Last resort: find the outermost {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.error("Could not parse Groq response as JSON. Raw (first 500): %s", text[:500])
        raise ValueError("Groq did not return valid JSON")

    def _validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean and validate extracted data for the Receipt model.
        Never silently zeroes a field without logging — caller must know what happened.
        """
        out = data.copy()

        # ── Date ──────────────────────────────────────────────────────────────
        raw_date = out.get("document_date")
        if raw_date and isinstance(raw_date, str):
            parsed = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    parsed = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed is None:
                logger.warning("Could not parse document_date: %s — setting null", raw_date)
            out["document_date"] = parsed

        # ── Numeric fields ─────────────────────────────────────────────────────
        for field in _NUMERIC_FIELDS:
            value = out.get(field)
            if value is None:
                continue
            try:
                out[field] = Decimal(str(value))
            except (InvalidOperation, ValueError) as e:
                logger.warning("Could not convert %s=%r to Decimal: %s", field, value, e)
                # confidence_score missing → conservative default that triggers review
                # financial fields missing → null is safer than 0 (0 hides the gap)
                out[field] = Decimal("0.5") if field == "confidence_score" else None

        # ── Confidence and review flag ─────────────────────────────────────────
        if out.get("confidence_score") is None:
            out["confidence_score"] = Decimal("0.5")
            logger.warning("confidence_score missing — defaulting to 0.5 (review required)")

        confidence = float(out["confidence_score"])
        out["requires_review"] = confidence < _REVIEW_THRESHOLD

        # ── Line items ─────────────────────────────────────────────────────────
        raw_items = out.get("line_items") or []
        cleaned_items = []
        for i, item in enumerate(raw_items):
            try:
                cleaned_items.append({
                    "description": str(item.get("description") or "Unknown Item"),
                    "quantity":    Decimal(str(item.get("quantity")   or 1)),
                    "unit_price":  Decimal(str(item.get("unit_price") or 0)),
                    "amount":      Decimal(str(item.get("amount")     or 0)),
                })
            except (InvalidOperation, ValueError) as e:
                logger.warning("Skipping malformed line item %d: %s — %s", i, item, e)
        out["line_items"] = cleaned_items

        # ── Financial consistency check ────────────────────────────────────────
        subtotal = float(out.get("subtotal") or 0)
        vat      = float(out.get("vat_amount") or 0)
        total    = float(out.get("total_amount") or 0)

        if total > 0 and abs((subtotal + vat) - total) > 2:
            logger.warning(
                "Financial mismatch: subtotal %.2f + vat %.2f = %.2f but total_amount is %.2f",
                subtotal, vat, subtotal + vat, total,
            )
            out["requires_review"] = True

        return out