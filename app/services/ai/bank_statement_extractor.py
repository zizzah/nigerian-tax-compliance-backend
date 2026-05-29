"""
Bank Statement AI Extractor
Location: app/services/ai/bank_statement_extractor.py

Uses Groq Vision (meta-llama/llama-4-scout-17b-16e-instruct) for image/PDF pages.
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

from groq import Groq  # type: ignore

from app.core.config import settings

logger = logging.getLogger(__name__)

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_PROMPT = """You are a financial data extraction expert specialising in Nigerian bank statements.

Extract ALL transactions from this bank statement image and return ONLY valid JSON.
No preamble, no explanation, no markdown — raw JSON only.

Required JSON structure:
{
  "account_name": "string or null",
  "account_number": "string or null",
  "bank_name": "string or null",
  "currency": "NGN",
  "period_from": "YYYY-MM-DD or null",
  "period_to": "YYYY-MM-DD or null",
  "opening_balance": number or null,
  "closing_balance": number or null,
  "total_inflow": number or null,
  "total_outflow": number or null,
  "inflows": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number,
      "value_date": "YYYY-MM-DD or null",
      "balance": number or null
    }
  ],
  "outflows": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number,
      "value_date": "YYYY-MM-DD or null",
      "balance": number or null
    }
  ],
  "confidence_score": 0.0
}

RULES:
- DEBIT column = outflow. CREDIT column = inflow.
- If a row has a DEBIT value > 0, it is an outflow.
- If a row has a CREDIT value > 0, it is an inflow.
- Do NOT include the Opening Balance row as a transaction.
- Dates must be YYYY-MM-DD. Convert DD/MM/YYYY if needed.
- All amounts must be plain numbers — no commas, no currency symbols.
- total_inflow = sum of all inflow amounts.
- total_outflow = sum of all outflow amounts.
- If you cannot read a field clearly, use null.
- confidence_score: 0.95+ if all rows extracted cleanly, lower if text was unclear."""


class BankStatementExtractor:
    """
    Extracts structured inflow/outflow data from Nigerian bank statements.
    Accepts PDF (converted to images per page) or direct image files.
    Uses Groq Vision — no Tesseract required.
    """

    def __init__(self) -> None:
        self.client = Groq(api_key=settings.GROQ_API_KEY)

    # ── Public ────────────────────────────────────────────────────────────────

    def extract(self, file_path: str, mime_type: str) -> dict:
        """
        Main entry point. Accepts image or PDF path.
        Returns structured extraction dict.
        Raises on unrecoverable failure — caller handles the exception.
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
                        # Log and skip — a single bad page should not abort extraction
                        logger.warning("Page extraction failed for %s: %s", img_path, e)

                if not page_results:
                    raise ValueError("No pages could be extracted from PDF")

                return self._merge_pages(page_results)

            else:
                # Direct image (PNG/JPG)
                return self._extract_from_image(file_path)

        finally:
            # Always clean up temp files regardless of success or failure
            for p in tmp_images:
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning("Could not delete temp file %s: %s", p, e)

    # ── Private ───────────────────────────────────────────────────────────────

    def _image_to_base64(self, image_path: str) -> tuple[str, str]:
        """Read image file and return (base64_string, media_type)."""
        suffix = Path(image_path).suffix.lower()
        media_type = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
        }.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), media_type

    def _pdf_to_images(self, pdf_path: str) -> list[str]:
        """
        Convert each PDF page to a PNG image.
        Returns list of temp file paths — caller is responsible for cleanup.
        Requires: pip install pymupdf
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF is not installed. Add 'pymupdf' to requirements.txt."
            )

        image_paths: list[str] = []
        doc = fitz.open(pdf_path)

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                # 2x zoom for better resolution → better extraction accuracy
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0)) # type: ignore

                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_page{page_num}.png"
                )
                pix.save(tmp.name)
                tmp.close()
                image_paths.append(tmp.name)
        finally:
            doc.close()

        return image_paths

    def _extract_from_image(self, image_path: str) -> dict:
        """Send a single image to Groq Vision and return parsed dict."""
        b64, media_type = self._image_to_base64(image_path)

        response = self.client.chat.completions.create(
            model=_VISION_MODEL,
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
                            "text": _PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,  # deterministic extraction
        )

        raw = response.choices[0].message.content or ""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: find outermost {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            logger.error(
                "Could not parse Groq Vision response as JSON. Raw (first 500): %s",
                raw[:500],
            )
            raise ValueError("Groq Vision did not return valid JSON")

    def _merge_pages(self, pages: list[dict]) -> dict:
        """
        Merge extraction results from multiple PDF pages into one.
        Header info (account, bank, period start) comes from page 1.
        Period end and closing balance come from the last page.
        Transactions are concatenated in order.
        """
        merged: dict = {
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

        merged["total_inflow"] = round(
            sum(t.get("amount", 0) for t in merged["inflows"]), 2
        )
        merged["total_outflow"] = round(
            sum(t.get("amount", 0) for t in merged["outflows"]), 2
        )

        scores = [
            p["confidence_score"]
            for p in pages
            if isinstance(p.get("confidence_score"), (int, float))
        ]
        merged["confidence_score"] = round(sum(scores) / len(scores), 2) if scores else 0.5

        return merged