"""
Natural Language Invoice Parser
Location: app/api/v1/endpoints/nlp_invoice.py

Endpoint:
  POST /nlp/parse-invoice  — parse plain-English description into structured invoice data

Register in app/main.py:
  from app.api.v1.endpoints import nlp_invoice
  app.include_router(nlp_invoice.router, prefix=settings.API_V1_PREFIX)
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from groq import Groq

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.product import Product

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nlp", tags=["Natural Language Processing"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class NLPInvoiceRequest(BaseModel):
    text: str
    customer_hint: Optional[str] = None  # Partial customer name if known


class ParsedLineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    tax_rate: float = 7.5


class ParsedInvoice(BaseModel):
    customer_name: Optional[str]
    customer_id: Optional[str]       # Filled if we matched an existing customer
    line_items: list[ParsedLineItem]
    notes: Optional[str]
    payment_terms: Optional[str]
    total_estimate: float
    confidence: float                 # 0–1
    raw_interpretation: str           # What the AI understood


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return biz


# ── POST /nlp/parse-invoice ───────────────────────────────────────────────────

@router.post("/parse-invoice", response_model=ParsedInvoice)
def parse_invoice_from_text(
    request: NLPInvoiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Parse a natural-language invoice description into structured invoice data.

    Example inputs:
    - "Invoice Acme Corp for 5 days consulting at 80k per day plus travel expenses of 45000"
    - "Bill TechStart 3 laptops at 350,000 each and 2 monitors at 150k"
    - "Invoice Chidi for website design 200k and hosting 15,000 per month for 12 months"

    Returns a ParsedInvoice that the frontend can use to pre-fill the invoice form.
    """
    biz = _get_business(db, current_user)

    # Fetch existing customers & products to help the model match names/prices
    customers = db.query(Customer).filter(
        Customer.business_id == biz.id,
        Customer.is_active == True,
    ).all()

    products = db.query(Product).filter(
        Product.business_id == biz.id,
        Product.is_active == True,
    ).limit(50).all()

    customer_list = [{"id": str(c.id), "name": c.name} for c in customers]
    product_list = [
        {"id": str(p.id), "name": p.name, "price": float(p.unit_price)} # type: ignore
        for p in products
    ]

    prompt = f"""You are an invoice parser for a Nigerian business. Parse the following text into a structured invoice.

INPUT TEXT: "{request.text}"

EXISTING CUSTOMERS (match by name similarity):
{json.dumps(customer_list[:20], indent=2)}

EXISTING PRODUCTS (use prices if the product name matches):
{json.dumps(product_list[:20], indent=2)}

PARSING RULES:
- Nigerian currency shorthand: k/K = thousands (80k = 80,000), M = millions
- "per day" = daily rate, "per month" = monthly rate — multiply quantity accordingly
- Default VAT rate = 7.5% unless noted as VAT-exclusive or zero-rated
- Match customer name to existing customers (case-insensitive, fuzzy)
- If customer not found in the list, use the mentioned name as-is (customer_id = null)

Return ONLY valid JSON:
{{
  "customer_name": "matched or mentioned customer name or null",
  "customer_id": "uuid string if matched, else null",
  "line_items": [
    {{
      "description": "clear item description",
      "quantity": 1.0,
      "unit_price": 0.0,
      "tax_rate": 7.5
    }}
  ],
  "notes": "any special notes or null",
  "payment_terms": "e.g. Payment due within 30 days or null",
  "total_estimate": 0.0,
  "confidence": 0.95,
  "raw_interpretation": "I understood: invoice [customer] for [items]..."
}}"""

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(raw)

        # Build validated line items
        line_items = [
            ParsedLineItem(
                description=item.get("description", "Item"),
                quantity=float(item.get("quantity", 1)),
                unit_price=float(item.get("unit_price", 0)),
                tax_rate=float(item.get("tax_rate", 7.5)),
            )
            for item in parsed.get("line_items", [])
        ]

        # Calculate total from line items (inclusive of VAT)
        total = sum(
            item.quantity * item.unit_price * (1 + item.tax_rate / 100)
            for item in line_items
        )

        return ParsedInvoice(
            customer_name=parsed.get("customer_name"),
            customer_id=parsed.get("customer_id"),
            line_items=line_items,
            notes=parsed.get("notes"),
            payment_terms=parsed.get("payment_terms"),
            total_estimate=round(total, 2),
            confidence=float(parsed.get("confidence", 0.7)),
            raw_interpretation=parsed.get("raw_interpretation", ""),
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from Groq NLP: {e}")
        raise HTTPException(status_code=500, detail="AI returned invalid JSON — please rephrase your input.")
    except Exception as e:
        logger.error(f"NLP invoice parse failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse invoice: {str(e)}")