"""
app/api/v1/endpoints/stock_movements.py
Handles stock IN/OUT movements, history, and restocking
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, extract
from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.business import Business
from app.models.product import Product

router = APIRouter(prefix="/stock-movements", tags=["stock-movements"])


def _get_business(db: Session, user: User) -> Business:
    biz = db.query(Business).filter(Business.owner_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz


# ── Schemas ───────────────────────────────────────────────────────────────────

class StockInRequest(BaseModel):
    product_id: str
    quantity: float
    unit_cost: Optional[float] = None
    note: Optional[str] = None
    movement_date: Optional[date] = None


class StockAdjustRequest(BaseModel):
    product_id: str
    quantity: float          # positive = add, negative = remove
    reason: Optional[str] = None
    movement_date: Optional[date] = None


# ── GET /stock-movements/{product_id} ─────────────────────────────────────────

@router.get("/{product_id}")
def get_product_movements(
    product_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = _get_business(db, current_user)

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == biz.id,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    rows = db.execute(text("""
        SELECT
            sm.id, sm.movement_type, sm.quantity, sm.unit_cost,
            sm.note, sm.movement_date, sm.created_at,
            i.invoice_number
        FROM stock_movements sm
        LEFT JOIN invoices i ON sm.invoice_id = i.id
        WHERE sm.product_id = :product_id
          AND sm.business_id = :biz_id
        ORDER BY sm.movement_date DESC, sm.created_at DESC
        LIMIT :limit
    """), {
        "product_id": product_id,
        "biz_id": str(biz.id),
        "limit": limit,
    }).fetchall()

    # Totals
    totals = db.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN movement_type = 'IN'  THEN quantity ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN movement_type = 'OUT' THEN quantity ELSE 0 END), 0) AS total_out
        FROM stock_movements
        WHERE product_id = :product_id
          AND business_id = :biz_id
    """), {"product_id": product_id, "biz_id": str(biz.id)}).fetchone()

    total_in  = float(totals.total_in  or 0) # type: ignore
    total_out = float(totals.total_out or 0) # type: ignore
    available = total_in - total_out

    return {
        "product_id":  product_id,
        "product_name": product.name,
        "total_in":    total_in,
        "total_out":   total_out,   # = total sold (ever)
        "available":   available,
        "movements": [
            {
                "id":             str(r.id),
                "type":           r.movement_type,
                "quantity":       float(r.quantity),
                "unit_cost":      float(r.unit_cost) if r.unit_cost else None,
                "note":           r.note,
                "movement_date":  str(r.movement_date),
                "invoice_number": r.invoice_number,
            }
            for r in rows
        ],
    }


# ── GET /stock-movements/ — all products summary ──────────────────────────────

@router.get("/")
def get_all_stock_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    biz = _get_business(db, current_user)

    rows = db.execute(text("""
        SELECT
            p.id,
            p.name,
            p.sku,
            p.unit_price,
            p.cost_price,
            p.low_stock_threshold,
            p.track_inventory,
            COALESCE(SUM(CASE WHEN sm.movement_type = 'IN'  THEN sm.quantity ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN sm.movement_type = 'OUT' THEN sm.quantity ELSE 0 END), 0) AS total_sold,
            COALESCE(SUM(CASE WHEN sm.movement_type = 'IN'  THEN sm.quantity ELSE 0 END), 0)
              - COALESCE(SUM(CASE WHEN sm.movement_type = 'OUT' THEN sm.quantity ELSE 0 END), 0) AS available
        FROM products p
        LEFT JOIN stock_movements sm
               ON sm.product_id = p.id AND sm.business_id = p.business_id
        WHERE p.business_id = :biz_id
          AND p.track_inventory = true
        GROUP BY p.id, p.name, p.sku, p.unit_price, p.cost_price,
                 p.low_stock_threshold, p.track_inventory
        ORDER BY p.name
    """), {"biz_id": str(biz.id)}).fetchall()

    return [
        {
            "product_id":          str(r.id),
            "name":                r.name,
            "sku":                 r.sku,
            "unit_price":          float(r.unit_price or 0),
            "cost_price":          float(r.cost_price or 0),
            "low_stock_threshold": r.low_stock_threshold,
            "total_in":            float(r.total_in),
            "total_sold":          float(r.total_sold),
            "available":           float(r.available),
            "is_low":              float(r.available) <= (r.low_stock_threshold or 0),
            "is_out":              float(r.available) <= 0,
        }
        for r in rows
    ]


# ── POST /stock-movements/restock ─────────────────────────────────────────────

@router.post("/restock")
def add_stock(
    body: StockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add new stock (IN movement). Does NOT reset total_sold."""
    biz = _get_business(db, current_user)

    product = db.query(Product).filter(
        Product.id == body.product_id,
        Product.business_id == biz.id,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    movement_date = body.movement_date or date.today()

    db.execute(text("""
        INSERT INTO stock_movements
            (id, business_id, product_id, movement_type, quantity, unit_cost, note, movement_date)
        VALUES
            (gen_random_uuid(), :biz_id, :product_id, 'IN', :qty, :cost, :note, :dt)
    """), {
        "biz_id":     str(biz.id),
        "product_id": body.product_id,
        "qty":        body.quantity,
        "cost":       body.unit_cost or product.cost_price,
        "note":       body.note or "Stock replenishment",
        "dt":         movement_date,
    })

    # Sync quantity_in_stock on product table for compatibility
    new_available = db.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN movement_type='IN'  THEN quantity ELSE 0 END),0)
          - COALESCE(SUM(CASE WHEN movement_type='OUT' THEN quantity ELSE 0 END),0)
        FROM stock_movements
        WHERE product_id = :pid AND business_id = :biz_id
    """), {"pid": body.product_id, "biz_id": str(biz.id)}).scalar()

    db.execute(text("""
        UPDATE products SET quantity_in_stock = :qty
        WHERE id = :pid AND business_id = :biz_id
    """), {"qty": float(new_available or 0), "pid": body.product_id, "biz_id": str(biz.id)})

    db.commit()

    return {
        "success":   True,
        "added_qty": body.quantity,
        "available": float(new_available or 0),
        "message":   str(int(body.quantity)) + " units of " + product.name + " added to stock",
    }