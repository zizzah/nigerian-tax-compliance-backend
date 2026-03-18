"""
Migration: Create stock_movements table
Run: python create_stock_movements.py
"""
import sys, os
sys.path.insert(0, '.')

from app.core.database import engine, SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    db.execute(text("""
        DO $$ BEGIN
            CREATE TYPE stockmovementtype AS ENUM ('IN', 'OUT');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id   UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            product_id    UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            invoice_id    UUID REFERENCES invoices(id) ON DELETE SET NULL,
            movement_type stockmovementtype NOT NULL,
            quantity      NUMERIC(10,2) NOT NULL,
            unit_cost     NUMERIC(12,2),
            note          TEXT,
            movement_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """))

    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_stock_movements_product_id
            ON stock_movements(product_id);
        CREATE INDEX IF NOT EXISTS ix_stock_movements_business_id
            ON stock_movements(business_id);
        CREATE INDEX IF NOT EXISTS ix_stock_movements_movement_date
            ON stock_movements(movement_date);
    """))

    # Seed existing stock as opening IN movements
    db.execute(text("""
        INSERT INTO stock_movements (business_id, product_id, movement_type, quantity, unit_cost, note, movement_date)
        SELECT p.business_id, p.id, 'IN', 
               COALESCE(p.quantity_in_stock, 0) + COALESCE(p.usage_count, 0),
               p.cost_price,
               'Opening stock (migrated)',
               CURRENT_DATE
        FROM products p
        WHERE p.track_inventory = true
          AND COALESCE(p.quantity_in_stock, 0) + COALESCE(p.usage_count, 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM stock_movements sm WHERE sm.product_id = p.id
          );
    """))

    # Seed existing sales as OUT movements from invoice_items
    db.execute(text("""
        INSERT INTO stock_movements (business_id, product_id, invoice_id, movement_type, quantity, unit_cost, note, movement_date)
        SELECT i.business_id, ii.product_id, ii.invoice_id, 'OUT',
               ii.quantity, p.cost_price,
               'Sale (migrated from invoice)',
               COALESCE(i.issue_date, CURRENT_DATE)
        FROM invoice_items ii
        JOIN invoices i   ON ii.invoice_id = i.id
        JOIN products p   ON ii.product_id = p.id
        WHERE ii.product_id IS NOT NULL
          AND p.track_inventory = true
          AND i.status NOT IN ('CANCELLED', 'DRAFT')
          AND NOT EXISTS (
              SELECT 1 FROM stock_movements sm
              WHERE sm.invoice_id = ii.invoice_id
                AND sm.product_id = ii.product_id
                AND sm.movement_type = 'OUT'
          );
    """))

    db.commit()
    print("SUCCESS: stock_movements table created and seeded")

except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
finally:
    db.close()