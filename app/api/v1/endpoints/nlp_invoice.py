"""
Natural Language Invoice Parser (Async + Timeout + Fallback)
Location: app/api/v1/endpoints/nlp_invoice.py
"""

import json
import logging
import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
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
    customer_hint: Optional[str] = None


class ParsedLineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    tax_rate: float = 7.5


class ParsedInvoice(BaseModel):
    customer_name: Optional[str]
    customer_id: Optional[str]
    line_items: list[ParsedLineItem]
    notes: Optional[str]
    payment_terms: Optional[str]
    total_estimate: float
    confidence: float
    raw_interpretation: str
    fallback: bool = False  # 🔥 NEW


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(
        select(Business).where(Business.user_id == user.id)
    )
    biz = result.scalars().first()

    if not biz:
        raise HTTPException(status_code=404, detail="Business profile not found")

    return biz


def _fallback_parse(text: str) -> dict:
    """
    Minimal safe fallback when AI fails.
    Keeps UI usable.
    """
    return {
        "customer_name": None,
        "customer_id": None,
        "line_items": [
            {
                "description": text[:80],
                "quantity": 1,
                "unit_price": 0,
                "tax_rate": 7.5,
            }
        ],
        "notes": None,
        "payment_terms": None,
        "total_estimate": 0.0,
        "confidence": 0.3,
        "raw_interpretation": f"Fallback parse: {text[:120]}",
        "fallback": True,
    }


# ── POST /nlp/parse-invoice ───────────────────────────────────────────────────

@router.post("/parse-invoice", response_model=ParsedInvoice)
async def parse_invoice_from_text(
    request: NLPInvoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Async NLP invoice parser with timeout + fallback protection.
    """

    start_time = time.time()

    biz = await _get_business(db, current_user)

    # ── Fetch customers ─────────────────────────
    customers_result = await db.execute(
        select(Customer).where(
            Customer.business_id == biz.id,
            Customer.is_active == True,
        )
    )
    customers = customers_result.scalars().all()

    # ── Fetch products ─────────────────────────
    products_result = await db.execute(
        select(Product)
        .where(
            Product.business_id == biz.id,
            Product.is_active == True,
        )
        .limit(50)
    )
    products = products_result.scalars().all()

    customer_list = [{"id": str(c.id), "name": c.name} for c in customers]

    product_list = [
        {
            "id": str(p.id),
            "name": p.name,
            "price": float(p.unit_price), # type: ignore
        }
        for p in products
    ]

    prompt = f"""You are an invoice parser for a Nigerian business.

INPUT TEXT: "{request.text}"

EXISTING CUSTOMERS:
{json.dumps(customer_list[:20], indent=2)}

EXISTING PRODUCTS:
{json.dumps(product_list[:20], indent=2)}

Return ONLY valid JSON in the required invoice format.
"""

    loop = asyncio.get_running_loop()

    def _call_groq():
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)

    # ── AI CALL WITH TIMEOUT ─────────────────────
    try:
        parsed = await asyncio.wait_for(
            loop.run_in_executor(None, _call_groq),
            timeout=5  # 🔥 tune if needed
        )
        parsed["fallback"] = False

    except asyncio.TimeoutError:
        logger.warning("Groq NLP timed out — using fallback")
        parsed = _fallback_parse(request.text)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from Groq: {e}")
        parsed = _fallback_parse(request.text)

    except Exception as e:
        logger.error(f"NLP invoice parse failed: {e}", exc_info=True)
        parsed = _fallback_parse(request.text)

    # ── Validate line items ─────────────────────
    line_items = [
        ParsedLineItem(
            description=item.get("description", "Item"),
            quantity=float(item.get("quantity", 1)),
            unit_price=float(item.get("unit_price", 0)),
            tax_rate=float(item.get("tax_rate", 7.5)),
        )
        for item in parsed.get("line_items", [])
    ]

    # ── Compute total ───────────────────────────
    total = sum(
        item.quantity * item.unit_price * (1 + item.tax_rate / 100)
        for item in line_items
    )

    latency = time.time() - start_time
    logger.info(f"NLP parse completed in {latency:.2f}s (fallback={parsed.get('fallback', False)})")

    return ParsedInvoice(
        customer_name=parsed.get("customer_name"),
        customer_id=parsed.get("customer_id"),
        line_items=line_items,
        notes=parsed.get("notes"),
        payment_terms=parsed.get("payment_terms"),
        total_estimate=round(total, 2),
        confidence=float(parsed.get("confidence", 0.7)),
        raw_interpretation=parsed.get("raw_interpretation", ""),
        fallback=parsed.get("fallback", False),
    )