from app.core.database import engine
from sqlalchemy import text

sql_types = """
DO $$ BEGIN
  CREATE TYPE expensecategory AS ENUM (
    'COST_OF_SALES','SALARIES_WAGES','PAYE_TAX','PENSION_CONTRIBUTION',
    'NHF_CONTRIBUTION','STAFF_WELFARE','RENT_RATES','UTILITIES',
    'MAINTENANCE_REPAIRS','FUEL_TRANSPORT','INTERNET_TELECOM','OFFICE_SUPPLIES',
    'EQUIPMENT_ASSETS','DEPRECIATION','MARKETING_ADS','BANK_CHARGES',
    'LOAN_REPAYMENT','LOAN_INTEREST','PROFESSIONAL_FEES','GOVT_LEVIES',
    'INSURANCE','COMPANY_TAX','VAT_REMITTED','WHT_REMITTED',
    'TRAVEL_ACCOMMODATION','TRAINING_DEVELOPMENT','OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE expensepaymentmethod AS ENUM (
    'CASH','BANK_TRANSFER','CARD','CHEQUE','MOBILE_MONEY','OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""

sql_table = """
CREATE TABLE IF NOT EXISTS expenses (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id      UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  category         expensecategory NOT NULL,
  subcategory      VARCHAR(100),
  description      TEXT NOT NULL,
  amount           NUMERIC(18,2) NOT NULL,
  expense_date     DATE NOT NULL DEFAULT CURRENT_DATE,
  vendor_name      VARCHAR(255),
  reference_number VARCHAR(100),
  payment_method   expensepaymentmethod NOT NULL DEFAULT 'CASH',
  is_tax_deductible BOOLEAN NOT NULL DEFAULT TRUE,
  tax_year         INTEGER,
  is_recurring     BOOLEAN NOT NULL DEFAULT FALSE,
  recurrence_period VARCHAR(20),
  next_due_date    DATE,
  receipt_url      TEXT,
  notes            TEXT,
  created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_expenses_business_id
  ON expenses(business_id);
CREATE INDEX IF NOT EXISTS ix_expenses_date
  ON expenses(business_id, expense_date);
CREATE INDEX IF NOT EXISTS ix_expenses_category
  ON expenses(business_id, category);
CREATE INDEX IF NOT EXISTS ix_expenses_recurring
  ON expenses(business_id, is_recurring, next_due_date);
"""

with engine.connect() as conn:
    conn.execute(text(sql_types))
    conn.execute(text(sql_table))
    conn.commit()
    print("Expenses table and types created successfully")