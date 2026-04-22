"""
Bank Statement Reconciliation Service
Location: app/services/ai/bank_reconciler.py

Parses bank statement text (CSV / TXT / PDF-extracted), extracts credit
transactions, and matches them to outstanding invoices using amount + customer
name fuzzy matching.
"""
import json
import logging
from sqlalchemy.orm import Session
from groq import Groq

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceStatus
from app.models.customer import Customer

logger = logging.getLogger(__name__)


class BankReconciler:

    def __init__(self):
        self.client = Groq(api_key=settings.GROQ_API_KEY)

    # ── Statement parsing ──────────────────────────────────────────────────────

    def parse_statement_text(self, text: str, bank_name: str = "") -> list[dict]:
        """
        Extract credit transactions from raw bank statement text using Groq.

        Returns a list of dicts:
          [{date, description, amount, reference, type}, ...]
        """
        prompt = f"""Extract all CREDIT transactions from this Nigerian bank statement.

BANK: {bank_name or "Unknown"}
STATEMENT TEXT:
{text[:8000]}

Return ONLY a JSON array of credit transactions:
[
  {{
    "date": "YYYY-MM-DD",
    "description": "transaction narration",
    "amount": 125000.00,
    "reference": "TXN reference if present or null",
    "type": "credit"
  }}
]

RULES:
- Only include CREDIT entries (money coming IN to the account)
- Convert Nigerian date formats (15-03-2026, 15/03/26) to YYYY-MM-DD
- Amount as a plain number — no ₦ symbol, no commas
- If no credits found, return an empty array []
- Return ONLY the JSON array, nothing else
"""
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=3000,
            )
            raw = response.choices[0].message.content or "[]"
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse bank statement via Groq: {e}")
            return []

    # ── Invoice matching ───────────────────────────────────────────────────────

    def match_transactions(
        self, transactions: list[dict], business_id: str, db: Session
    ) -> list[dict]:
        """
        Match each credit transaction to the most likely outstanding invoice.

        Scoring:
        - Exact amount match (+60), within 2% (+40)
        - Customer name found in narration (+20 per word, capped)
        - Invoice number found in narration or reference (+30)
        Threshold: score ≥ 40 is considered a match.
        """
        outstanding = (
            db.query(Invoice, Customer.name.label("customer_name"))
            .join(Customer, Invoice.customer_id == Customer.id, isouter=True)
            .filter(
                Invoice.business_id == business_id,
                Invoice.status.in_([ # type: ignore
                    InvoiceStatus.SENT,
                    InvoiceStatus.OVERDUE,
                    InvoiceStatus.PARTIALLY_PAID,
                ]),
            )
            .all()
        )

        results = []
        for txn in transactions:
            txn_amount = float(txn.get("amount", 0))
            txn_desc = (txn.get("description") or "").lower()
            txn_ref = (txn.get("reference") or "").lower()

            best_match = None
            best_score = 0

            for inv, customer_name in outstanding:
                inv_amount = float(inv.outstanding_amount or 0)
                score = 0

                # Amount matching
                if abs(txn_amount - inv_amount) < 1:
                    score += 60
                elif inv_amount > 0 and abs(txn_amount - inv_amount) / inv_amount < 0.02:
                    score += 40

                # Customer name in narration
                if customer_name:
                    for word in customer_name.lower().split():
                        if len(word) > 3 and word in txn_desc:
                            score += 20
                            break

                # Invoice number in narration or reference
                inv_num = (inv.invoice_number or "").lower()
                if inv_num and (inv_num in txn_desc or inv_num in txn_ref):
                    score += 30

                if score > best_score and score >= 40:
                    best_score = score
                    best_match = (inv, customer_name)

            results.append({
                "transaction": txn,
                "matched": best_match is not None,
                "confidence": min(100, best_score),
                "invoice_id": str(best_match[0].id) if best_match else None,
                "invoice_number": best_match[0].invoice_number if best_match else None,
                "customer_name": best_match[1] if best_match else None,
                "invoice_amount": float(best_match[0].outstanding_amount) if best_match else None,
            })

        return results