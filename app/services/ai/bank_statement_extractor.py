"""
Bank Statement AI Extractor
Location: app/services/ai/bank_statement_extractor.py

Uses Groq Vision (llama-3.2-90b-vision-preview) for image/PDF pages.
No Tesseract — image goes directly to the model.
"""
import base64
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional
from groq import Groq
from app.core.config import settings


logger = logging.getLogger(__name__)

# Supported Nigerian banks and their known statement formats
NIGERIAN_BANKS = [
    "ZENITH BANK", "GTBANK", "GUARANTY TRUST", "ACCESS BANK", "UBA",
    "UNITED BANK FOR AFRICA", "FIRST BANK", "FIRSTBANK", "UNION BANK",
    "FIDELITY BANK", "STANBIC IBTC", "STERLING BANK", "POLARIS BANK","PALMPAY"
    "WEMA BANK", "KEYSTONE BANK", "JAIZ BANK", "ECOBANK", "CITIBANK","OPAY","MONIEPOINT",
    "STANDARD CHARTERED", "HERITAGE BANK", "PROVIDUS BANK", "TITAN BANK", "ALAT BY WEMA",
]

GROQ_VISION_PROMPT = """
You are a financial data extraction expert specialising in Nigerian bank statements.

Extract ALL transactions from this bank statement image and return ONLY valid JSON.
No preamble, no explanation, no markdown — raw JSON only.

Required JSON structure:
{
  "account_name": "string",
  "account_number": "string",
  "bank_name": "string",
  "currency": "NGN",
  "period_from": "YYYY-MM-DD",
  "period_to": "YYYY-MM-DD",
  "opening_balance": number,
  "closing_balance": number,
  "total_inflow": number,
  "total_outflow": number,
  "inflows": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number,
      "value_date": "YYYY-MM-DD or null",
      "balance": number
    }
  ],
  "outflows": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number,
      "value_date": "YYYY-MM-DD or null",
      "balance": number
    }
  ],
  "confidence_score": 0.0 to 1.0
}

Rules:
- DEBIT column = outflow. CREDIT column = inflow.
- If a row has a DEBIT value > 0, it is an outflow.
- If a row has a CREDIT value > 0, it is an inflow.
- Do NOT include the Opening Balance row as a transaction.
- Dates must be YYYY-MM-DD format. Convert DD/MM/YYYY if needed.
- All amounts must be plain numbers, no commas or currency symbols.
- total_inflow = sum of all inflow amounts.
- total_outflow = sum of all outflow amounts.
- If you cannot read a field clearly, use null.
- confidence_score: 0.95+ if all rows extracted cleanly, lower if text was unclear.
"""


class BankStatementExtractor:
    """
    Extracts structured inflow/outflow data from Nigerian bank statements.
    Accepts PDF (converted to images) or direct image files.
    Uses Groq Vision — no Tesseract required.
    """

    def __init__(self):
        try:
            self.client = Groq(api_key=settings.GROQ_API_KEY)
            self.vision_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        except Exception as e:
            logger.error("Failed to initialise Groq client: %s", e)
            raise

    def _image_to_base64(self, image_path: str) -> tuple[str, str]:
        """Read image file and return (base64_string, media_type)."""
        suffix = Path(image_path).suffix.lower()
        media_type_map = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
        }
        media_type = media_type_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), media_type

    def _pdf_to_images(self, pdf_path: str) -> list[str]:
        """
        Convert each PDF page to a PNG image.
        Returns list of temp image file paths.
        Requires: pip install pymupdf
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF not installed. Run: pip install pymupdf"
            )

        doc = fitz.open(pdf_path)
        image_paths = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # 2x zoom for better resolution → better extraction accuracy
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)

            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_page{page_num}.png"
            )
            pix.save(tmp.name)
            image_paths.append(tmp.name)

        doc.close()
        return image_paths

    def _extract_from_image(self, image_path: str) -> dict:
        """Send a single image to Groq Vision and parse the response."""
        b64, media_type = self._image_to_base64(image_path)

        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": GROQ_VISION_PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,  # deterministic extraction
        )

        raw = response.choices[0].message.content or ""
        # Strip markdown fences if model adds them despite instructions
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        return json.loads(raw)

    def _merge_pages(self, pages: list[dict]) -> dict:
        """
        Merge extraction results from multiple PDF pages into one.
        Header info comes from page 1; transactions are concatenated.
        """
        if not pages:
            return {}

        merged = {
            "account_name":    pages[0].get("account_name"),
            "account_number":  pages[0].get("account_number"),
            "bank_name":       pages[0].get("bank_name"),
            "currency":        pages[0].get("currency", "NGN"),
            "period_from":     pages[0].get("period_from"),
            "period_to":       pages[-1].get("period_to") or pages[0].get("period_to"),
            "opening_balance": pages[0].get("opening_balance"),
            "closing_balance": pages[-1].get("closing_balance") or pages[0].get("closing_balance"),
            "inflows":         [],
            "outflows":        [],
        }

        for page in pages:
            merged["inflows"].extend(page.get("inflows") or [])
            merged["outflows"].extend(page.get("outflows") or [])

        merged["total_inflow"]  = round(sum(t.get("amount", 0) for t in merged["inflows"]), 2)
        merged["total_outflow"] = round(sum(t.get("amount", 0) for t in merged["outflows"]), 2)

        # Average confidence across pages
        scores = [p.get("confidence_score", 0) for p in pages if p.get("confidence_score")]
        merged["confidence_score"] = round(sum(scores) / len(scores), 2) if scores else 0.7

        return merged

    def extract(self, file_path: str, mime_type: str) -> dict:
        """
        Main entry point. Accepts image or PDF path.
        Returns structured extraction dict.
        """
        tmp_images: list[str] = []

        try:
            if mime_type == "application/pdf":
                tmp_images = self._pdf_to_images(file_path)
                if not tmp_images:
                    raise ValueError("PDF produced no pages")

                page_results = []
                for img_path in tmp_images:
                    try:
                        result = self._extract_from_image(img_path)
                        page_results.append(result)
                    except Exception as e:
                        logger.warning("Page extraction failed: %s", e)
                        continue

                if not page_results:
                    raise ValueError("No pages could be extracted")

                return self._merge_pages(page_results)

            else:
                # Direct image (PNG/JPG)
                return self._extract_from_image(file_path)

        finally:
            for p in tmp_images:
                try:
                    os.unlink(p)
                except Exception:
                    pass