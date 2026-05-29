"""
Bank Statement Reconciliation Service
Location: app/services/ai/bank_reconciler.py
"""
import json
import logging
from typing import List, Dict, Optional, Tuple

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from groq import Groq

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceStatus
from app.models.customer import Customer

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 40


class BankReconciler:

    def __init__(self) -> None:
        self.client = Groq(api_key=settings.GROQ_API_KEY)

    # ── Statement parsing ──────────────────────────────────────────────────────

    def parse_statement_text(self, text: str, bank_name: str = "") -> List[Dict]:
        """
        Extract credit transactions from raw bank statement text using Groq.

        Returns:
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
            logger.error(f"parse_statement_text failed: {e}")
            return []

    # ── Invoice matching ───────────────────────────────────────────────────────

    async def match_transactions(
        self,
        transactions: List[Dict],
        business_id: str,
        db: AsyncSession,
    ) -> List[Dict]:
        """
        Match each credit transaction to the most likely outstanding invoice.

        Scoring:
          +60  exact amount match (within ₦1)
          +40  amount within 2%
          +20  customer name fuzzy-matches narration (partial_ratio > 70)
          +30  invoice number found in narration or reference field

        A score >= 40 is treated as a match.
        """
        stmt = (
            select(Invoice, Customer.name.label("customer_name"))
            .join(Customer, Invoice.customer_id == Customer.id, isouter=True)
            .where(
                Invoice.business_id == business_id,
                Invoice.status.in_([ # type: ignore
                    InvoiceStatus.SENT,
                    InvoiceStatus.OVERDUE,
                    InvoiceStatus.PARTIALLY_PAID,
                ]),
            )
        )
        result = await db.execute(stmt)
        outstanding = result.all()

        results = []
        for txn in transactions:
            best_match, best_score = self._score_against_invoices(
                txn, outstanding # type: ignore
            )
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

    # ── Private helpers ────────────────────────────────────────────────────────

    def _score_against_invoices(
        self,
        txn: Dict,
        outstanding: List[Tuple],
    ) -> Tuple[Optional[Tuple], int]:
        """
        Score one transaction against all outstanding invoices.
        Returns (best_match_tuple | None, best_score).
        """
        txn_amount = float(txn.get("amount", 0))
        txn_desc = (txn.get("description") or "").lower()
        txn_ref = (txn.get("reference") or "").lower()

        best_match = None
        best_score = 0

        for inv, customer_name in outstanding:
            score = 0
            inv_amount = float(inv.outstanding_amount or 0)

            # ── Amount ────────────────────────────────────────────────────────
            if abs(txn_amount - inv_amount) < 1:
                score += 60
            elif inv_amount > 0 and abs(txn_amount - inv_amount) / inv_amount < 0.02:
                score += 40

            # ── Customer name fuzzy match ──────────────────────────────────────
            # partial_ratio handles abbreviations, missing words, and short names
            # like UBA, GTB, OPay without any length-filtering games.
            if customer_name:
                ratio = fuzz.partial_ratio(customer_name.lower(), txn_desc)
                if ratio > 70:
                    score += 20

            # ── Invoice number in narration or reference ───────────────────────
            inv_num = (inv.invoice_number or "").lower()
            if inv_num and (inv_num in txn_desc or inv_num in txn_ref):
                score += 30

            if score > best_score and score >= _MATCH_THRESHOLD:
                best_score = score
                best_match = (inv, customer_name)

        return best_match, best_score