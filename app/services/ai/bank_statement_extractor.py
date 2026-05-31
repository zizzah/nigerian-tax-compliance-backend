"""
Bank Statement AI Extractor
Location: app/services/ai/bank_statement_extractor.py

Strategy:
- Text-based PDFs → PyMuPDF text extraction with x-coordinate column detection
- Image files or scanned PDFs → Groq Vision fallback
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

# Groq Vision fallback prompt — only used for scanned/image PDFs
_VISION_PROMPT = """You are a financial data extraction expert specialising in Nigerian bank statements.

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
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "debit": number or null,
      "credit": number or null,
      "value_date": "YYYY-MM-DD or null",
      "balance": number or null
    }
  ],
  "confidence_score": 0.0
}

RULES:
- For each transaction row, read the DEBIT column value and put it in "debit". Read the CREDIT column value and put it in "credit".
- If the DEBIT column is empty, zero, or "--" → set "debit" to null.
- If the CREDIT column is empty, zero, or "--" → set "credit" to null.
- Never put the same amount in both debit and credit.
- Never use the Balance or Balance After column as a debit or credit amount.
- opening_balance and closing_balance must come from the statement header, not transaction rows.
- Do NOT include the Opening Balance row as a transaction.
- If the PDF has multiple account sections, extract ALL transactions from ALL sections.
- Dates must be YYYY-MM-DD. Convert DD/MM/YYYY, DD-Mon-YYYY, DD May YYYY formats.
- All amounts must be plain numbers — no commas, no ₦ symbol, no dashes.
- confidence_score: 0.95+ if all rows extracted cleanly."""



class BankStatementExtractor:
    """
    Extracts structured inflow/outflow data from Nigerian bank statements.

    For text-based PDFs: uses PyMuPDF x-coordinate column detection.
    For image files or scanned PDFs: falls back to Groq Vision.
    """

    def __init__(self) -> None:
        self.client = Groq(api_key=settings.GROQ_API_KEY)


    # ── Public ────────────────────────────────────────────────────────────────

    def extract(self, file_path: str, mime_type: str) -> dict:
        """
        Main entry point. Accepts image or PDF path.
        Returns structured extraction dict.
        Raises on unrecoverable failure.
        """
        if mime_type == "application/pdf":
            logger.info("PDF received — using Groq Vision extraction")
            return self._extract_from_scanned_pdf(file_path)
        else:
            return self._extract_from_image(file_path)
        # ── Text-based PDF extraction ─────────────────────────────────────────────

    def _pdf_has_text(self, pdf_path: str) -> bool:
        try:
            import fitz
            import re
            doc = fitz.open(pdf_path)
            date_pattern = re.compile(r"\d{2}[\/\-]\d{2}[\/\-]\d{2,4}")
            
            for page in doc:
                text = page.get_text("text").strip() # type: ignore
                if len(text) < 50:
                    continue
                dates_found = date_pattern.findall(text)
                if len(dates_found) >= 3:
                    doc.close()
                    return True
            
            doc.close()
            return False
        except Exception:
            return False


    def _extract_from_text_pdf(self, pdf_path: str) -> dict:
        import fitz

        doc = fitz.open(pdf_path)
        all_pages_data = []
        detected_col_positions = None  # shared across pages

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_data = self._parse_page(
                page, 
                col_positions_override=detected_col_positions, # type: ignore
                 is_first_page=(page_num == 0) 
            )
            if page_data:
                # Save column positions from first successful detection
                if detected_col_positions is None and page_data.get("_col_positions"):
                    detected_col_positions = page_data.pop("_col_positions")
                    logger.info(
                        "Column positions detected on page %d: %s",
                        page_num + 1, detected_col_positions
                    )
                else:
                    page_data.pop("_col_positions", None)
                all_pages_data.append(page_data)

        doc.close()

        if not all_pages_data:
            raise ValueError("Could not extract any transaction data from PDF")

        return self._merge_pages_text(all_pages_data)




    def _parse_page(self, page, col_positions_override=None, is_first_page=False) -> Optional[dict]:
        words = page.get_text("words")
        if not words:
            return None

        lines: dict[int, list] = {}
        for w in words:
            y_key = round(w[1] / 5) * 5
            if y_key not in lines:
                lines[y_key] = []
            lines[y_key].append({"text": w[4], "x": w[0], "y": w[1]})

        sorted_lines = [
            sorted(lines[y], key=lambda w: w["x"])
            for y in sorted(lines.keys())
        ]

        if col_positions_override:
            col_positions = col_positions_override
        else:
            col_positions = self._detect_columns(sorted_lines)
            if not col_positions:
                logger.warning("Could not detect column positions on page")
                return None

        if is_first_page:
            metadata = self._extract_metadata(sorted_lines)
        else:
            metadata = {}

        transactions = self._extract_transactions(sorted_lines, col_positions)

        result = {**metadata, "transactions": transactions}

        if not col_positions_override:
            result["_col_positions"] = col_positions

        return result

    def _detect_columns(self, sorted_lines: list) -> Optional[dict]:
        print(f"DETECT_COLUMNS CALLED — {len(sorted_lines)} lines", flush=True)
        for i, line in enumerate(sorted_lines[:15]):
            print(f"  Line {i}: {[w['text'] for w in line]}", flush=True)

        header_keywords = {
            "date":    ["DATE", "TRANS. DATE", "TRANS DATE", "TRAN DATE", "TRANS. TIME"],
            "debit":   ["DEBIT", "DR", "WITHDRAWAL", "DEBITS", "DEBIT(N)"],
            "credit":  ["CREDIT", "CR", "DEPOSIT", "CREDITS", "CREDIT(N)"],
            "balance": ["BALANCE", "BAL"],
        }

        # Check each line and also merge with the next line (handles split headers)
        for i, line in enumerate(sorted_lines):
            # Build a combined line from current + next (handles GTB split headers)
            combined_words = line[:]
            if i + 1 < len(sorted_lines):
                combined_words = combined_words + sorted_lines[i + 1]

            words_in_combined = [w["text"].upper() for w in combined_words]
            line_text = " ".join(words_in_combined)

            has_debit  = any(k in line_text for k in header_keywords["debit"])
            has_credit = any(k in line_text for k in header_keywords["credit"])

            if has_debit and has_credit:
                positions = {}
                for word in combined_words:
                    upper = word["text"].upper()
                    for col, keywords in header_keywords.items():
                        if any(k in upper for k in keywords):
                            if col not in positions:
                                positions[col] = word["x"]

                print(f"HEADER FOUND at line {i}: {positions}", flush=True)
                return positions

        print("NO HEADER FOUND after full scan", flush=True)
        return None



    def _extract_transactions(
        self, sorted_lines: list, col_positions: dict
    ) -> list[dict]:
        transactions = []

        debit_x  = col_positions.get("debit",  0)
        credit_x = col_positions.get("credit", 0)
        bal_x    = col_positions.get("balance", 9999)
        tolerance = 80
        
        logger.info(
        "Extracting with columns — debit_x=%.1f credit_x=%.1f bal_x=%.1f tolerance=%d",
        debit_x, credit_x, bal_x, tolerance
    )

        date_pattern = re.compile(r"^\d{2}[\/\-]\d{2}[\/\-]\d{2,4}$")

        # Strict money pattern — must have a decimal point and be a realistic amount
        # Excludes long reference numbers like 000013260303184237000020267556
        money_pattern = re.compile(r"^\-?\d{1,3}(?:,\d{3})*\.\d{2}$|^\-?\d{1,9}\.\d{2}$")

        skip_keywords = [
            "OPENING BALANCE", "CLOSING BALANCE", "TOTALS",
            "TOTAL (", "TOTAL(", "PAGE", "BROUGHT FORWARD",
        ]

        i = 0
        while i < len(sorted_lines):
            line = sorted_lines[i]
            words = [w["text"] for w in line]

            if not words or not date_pattern.match(words[0]):
                i += 1
                continue

            date_str = self._parse_date(words[0])
            if not date_str:
                i += 1
                continue

            line_text = " ".join(words).upper()
            if any(skip in line_text for skip in skip_keywords):
                i += 1
                continue

            description_parts = []
            debit_val   = None
            credit_val  = None
            balance_val = None
            value_date  = None

            for word in line:
                x   = word["x"]
                txt = word["text"]

                if txt == words[0]:
                    continue

                clean = txt.replace(",", "")

                if money_pattern.match(txt):  # match original with commas
                    try:
                        val = float(clean)
                    except ValueError:
                        description_parts.append(txt)
                        continue

                    dist_debit  = abs(x - debit_x)
                    dist_credit = abs(x - credit_x)
                    dist_bal    = abs(x - bal_x)
                    closest     = min(dist_debit, dist_credit, dist_bal)

                    if closest > tolerance:
                        description_parts.append(txt)
                    elif closest == dist_debit:
                        debit_val = val
                    elif closest == dist_credit:
                        credit_val = val
                    else:
                        balance_val = val

                elif date_pattern.match(txt):
                    value_date = self._parse_date(txt)

                else:
                    description_parts.append(txt)

            # Collect multi-line description continuations
            while i + 1 < len(sorted_lines):
                next_line  = sorted_lines[i + 1]
                next_words = [w["text"] for w in next_line]

                if not next_words:
                    break

                # New transaction starts with a date
                if date_pattern.match(next_words[0]):
                    break

                next_text = " ".join(next_words).upper()

                # Footer or summary row
                if any(k in next_text for k in [s.upper() for s in skip_keywords]):
                    break

                # Stop only if next line has ACTUAL money values (strict pattern)
                has_real_money = any(
                    money_pattern.match(w)
                    for w in next_words
                )
                if has_real_money:
                    break

                description_parts.extend(next_words)
                i += 1

            if debit_val is not None or credit_val is not None:
                transactions.append({
                    "date":        date_str,
                    "description": " ".join(description_parts).strip(),
                    "debit":       debit_val,
                    "credit":      credit_val,
                    "value_date":  value_date,
                    "balance":     balance_val,
                })

            i += 1

        return transactions


    def _extract_metadata(self, sorted_lines: list) -> dict:
        """
        Extract account info, period, and balances from page header text.
        Uses Groq text model for reliability across different bank formats.
        """
        header_text = "\n".join(
            " ".join(w["text"] for w in line)
            for line in sorted_lines[:30]
        )

        prompt = f"""Extract account metadata from this Nigerian bank statement header text.
    Return ONLY valid JSON, no markdown.

    {{
    "account_name": "string or null",
    "account_number": "string or null",
    "bank_name": "string or null",
    "period_from": "YYYY-MM-DD or null",
    "period_to": "YYYY-MM-DD or null",
    "opening_balance": number or null,
    "closing_balance": number or null,
    "currency": "NGN"
    }}

    HEADER TEXT:
    {header_text[:2000]}"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
            )
            raw = response.choices[0].message.content or "{}"
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning("Metadata extraction failed: %s", e)
            return {
                "account_name": None, "account_number": None,
                "bank_name": None, "period_from": None,
                "period_to": None, "opening_balance": None,
                "closing_balance": None, "currency": "NGN",
            }




    def _merge_pages_text(self, pages: list[dict]) -> dict:
        """Merge multi-page text extraction results."""
        merged = {
            "account_name":    pages[0].get("account_name"),
            "account_number":  pages[0].get("account_number"),
            "bank_name":       pages[0].get("bank_name"),
            "currency":        pages[0].get("currency", "NGN"),
            "period_from":     pages[0].get("period_from"),
            "period_to":       pages[-1].get("period_to") or pages[0].get("period_to"),
            "opening_balance": pages[0].get("opening_balance"),
            "closing_balance": pages[-1].get("closing_balance") or pages[0].get("closing_balance"),
            "transactions":    [],
            "confidence_score": 0.95,  # text extraction is highly reliable
        }

        for page in pages:
            merged["transactions"].extend(page.get("transactions") or [])

        logger.info(
            "Text extraction complete — %d transactions across %d pages",
            len(merged["transactions"]), len(pages)
        )

        return self._classify_transactions(merged)

    # ── Transaction classification (shared by text and vision paths) ──────────

    def _classify_transactions(self, data: dict) -> dict:
        inflows  = []
        outflows = []

        for txn in data.get("transactions") or []:
            debit  = txn.get("debit")
            credit = txn.get("credit")

            clean = {
                "date":        txn.get("date"),
                "description": txn.get("description") or "",
                "value_date":  txn.get("value_date"),
                "balance":     txn.get("balance"),
            }

            try:
                if credit is not None and float(credit) > 0:
                    clean["amount"] = float(credit)
                    inflows.append(clean)
                elif debit is not None and float(debit) > 0:
                    clean["amount"] = float(debit)
                    outflows.append(clean)
            except (TypeError, ValueError):
                pass

        total_inflow  = round(sum(t["amount"] for t in inflows), 2)
        total_outflow = round(sum(t["amount"] for t in outflows), 2)

        data["inflows"]       = inflows
        data["outflows"]      = outflows
        data["total_inflow"]  = total_inflow
        data["total_outflow"] = total_outflow
        data.pop("transactions", None)

        # ── Variance check against Vision-extracted header totals ──────────────
        # Vision extracts opening/closing balance from the header. If the sum of
        # classified transactions diverges significantly from what the statement
        # header says, flag it for manual review.
        opening  = data.get("opening_balance")
        closing  = data.get("closing_balance")

        if opening is not None and closing is not None:
            try:
                expected_net = round(float(closing) - float(opening), 2)
                actual_net   = round(total_inflow - total_outflow, 2)
                variance     = abs(expected_net - actual_net)
                variance_pct = (variance / max(abs(expected_net), 1)) * 100

                data["extraction_variance"] = round(variance, 2)

                if variance_pct > 1.0:
                    data["requires_review"] = True
                    logger.warning(
                        "Extraction variance %.2f%% (%.2f) — expected net %.2f, got %.2f. "
                        "Flagging for review.",
                        variance_pct, variance, expected_net, actual_net
                    )
                else:
                    data["requires_review"] = False
                    logger.info(
                        "Extraction variance %.2f%% (%.2f) — within threshold.",
                        variance_pct, variance
                    )
            except (TypeError, ValueError):
                logger.warning("Could not compute extraction variance — balance values missing.")

        logger.info(
            "Classified: %d inflows (%.2f) | %d outflows (%.2f)",
            len(inflows),  total_inflow,
            len(outflows), total_outflow,
        )

        return data



    # ── Vision fallback (scanned PDFs and images) ─────────────────────────────

    def _extract_from_scanned_pdf(self, pdf_path: str) -> dict:
        """Convert scanned PDF pages to images and run vision extraction."""
        tmp_images: list[str] = []
        try:
            tmp_images = self._pdf_to_images(pdf_path)
            if not tmp_images:
                raise ValueError("PDF produced no pages")

            page_results = []
            for img_path in tmp_images:
                try:
                    result = self._extract_from_image(img_path)
                    page_results.append(result)
                except Exception as e:
                    logger.warning("Vision page extraction failed: %s", e)

            if not page_results:
                raise ValueError("No pages could be extracted")

            return self._merge_pages_vision(page_results)

        finally:
            for p in tmp_images:
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning("Could not delete temp file %s: %s", p, e)


    def _extract_from_image(self, image_path: str) -> dict:
        """Send image to Groq Vision and return classified dict.
        
        Raises:
            ValueError: If Groq returns a response that cannot be parsed as JSON.
        """
        b64, media_type = self._image_to_base64(image_path)

        response = self.client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        },
                        {"type": "text", "text": _VISION_PROMPT},
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,
        )

        raw = response.choices[0].message.content or ""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        # State 1 & 2: clean JSON or JSON inside stripped markdown fences
        try:
            result = json.loads(cleaned)
            return self._classify_transactions(result)
        except json.JSONDecodeError:
            pass

        # State 3: JSON buried in surrounding text — last attempt
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                return self._classify_transactions(result)
            except json.JSONDecodeError:
                pass

        # All parsing attempts failed
        logger.error(
            "Groq Vision returned unparseable response for %s. Raw: %s",
            image_path, raw[:500]
        )
        raise ValueError(f"Groq Vision did not return valid JSON for {image_path}")



    def _merge_pages_vision(self, pages: list[dict]) -> dict:
        """Merge vision extraction results from multiple pages."""
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

        merged["total_inflow"]  = round(sum(t.get("amount", 0) for t in merged["inflows"]), 2)
        merged["total_outflow"] = round(sum(t.get("amount", 0) for t in merged["outflows"]), 2)

        scores = [
            p["confidence_score"]
            for p in pages
            if isinstance(p.get("confidence_score"), (int, float))
        ]
        merged["confidence_score"] = round(sum(scores) / len(scores), 2) if scores else 0.5

        return merged

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _image_to_base64(self, image_path: str) -> tuple[str, str]:
        suffix = Path(image_path).suffix.lower()
        media_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        }.get(suffix, "image/jpeg")
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), media_type

    def _pdf_to_images(self, pdf_path: str) -> list[str]:
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PyMuPDF not installed. Add 'pymupdf' to requirements.txt.")

        image_paths: list[str] = []
        doc = fitz.open(pdf_path)
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                # Use a unique temp path without pre-creating the file
                tmp_path = os.path.join(
                    tempfile.gettempdir(),
                    f"stmt_{os.getpid()}_{page_num}.png"
                )
                pix.save(tmp_path)
                image_paths.append(tmp_path)
        finally:
            doc.close()
        return image_paths

    def _parse_date(self, text: str) -> Optional[str]:
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d"):
            try:
                from datetime import datetime
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None