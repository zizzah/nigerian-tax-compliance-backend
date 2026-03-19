"""
Expense Model
Location: app/models/expense.py

Matches the database schema created by create_expenses_table.py exactly.
Enum names match PostgreSQL types: expensecategory, expensepaymentmethod
"""
import uuid
import enum

from sqlalchemy import (
    Column, String, Numeric, Date, Boolean,
    Integer, Text, ForeignKey, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SQLEnum

from app.core.database import Base


# ── Enums (must match PostgreSQL enum type names exactly) ─────────────────────

class ExpenseCategory(str, enum.Enum):
    COST_OF_SALES        = "COST_OF_SALES"
    SALARIES_WAGES       = "SALARIES_WAGES"
    PAYE_TAX             = "PAYE_TAX"
    PENSION_CONTRIBUTION = "PENSION_CONTRIBUTION"
    NHF_CONTRIBUTION     = "NHF_CONTRIBUTION"
    STAFF_WELFARE        = "STAFF_WELFARE"
    RENT_RATES           = "RENT_RATES"
    UTILITIES            = "UTILITIES"
    MAINTENANCE_REPAIRS  = "MAINTENANCE_REPAIRS"
    FUEL_TRANSPORT       = "FUEL_TRANSPORT"
    INTERNET_TELECOM     = "INTERNET_TELECOM"
    OFFICE_SUPPLIES      = "OFFICE_SUPPLIES"
    EQUIPMENT_ASSETS     = "EQUIPMENT_ASSETS"
    DEPRECIATION         = "DEPRECIATION"
    MARKETING_ADS        = "MARKETING_ADS"
    BANK_CHARGES         = "BANK_CHARGES"
    LOAN_REPAYMENT       = "LOAN_REPAYMENT"
    LOAN_INTEREST        = "LOAN_INTEREST"
    PROFESSIONAL_FEES    = "PROFESSIONAL_FEES"
    GOVT_LEVIES          = "GOVT_LEVIES"
    INSURANCE            = "INSURANCE"
    COMPANY_TAX          = "COMPANY_TAX"
    VAT_REMITTED         = "VAT_REMITTED"
    WHT_REMITTED         = "WHT_REMITTED"
    TRAVEL_ACCOMMODATION = "TRAVEL_ACCOMMODATION"
    TRAINING_DEVELOPMENT = "TRAINING_DEVELOPMENT"
    OTHER                = "OTHER"


class ExpensePaymentMethod(str, enum.Enum):
    CASH          = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD          = "CARD"
    CHEQUE        = "CHEQUE"
    MOBILE_MONEY  = "MOBILE_MONEY"
    OTHER         = "OTHER"


# ── Lookup tables used by endpoints ───────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "COST_OF_SALES":        "Cost of Sales",
    "SALARIES_WAGES":       "Salaries & Wages",
    "PAYE_TAX":             "PAYE Tax Remitted",
    "PENSION_CONTRIBUTION": "Pension Contribution",
    "NHF_CONTRIBUTION":     "NHF Contribution",
    "STAFF_WELFARE":        "Staff Welfare",
    "RENT_RATES":           "Rent & Rates",
    "UTILITIES":            "Utilities",
    "MAINTENANCE_REPAIRS":  "Maintenance & Repairs",
    "FUEL_TRANSPORT":       "Fuel & Transport",
    "INTERNET_TELECOM":     "Internet & Telecoms",
    "OFFICE_SUPPLIES":      "Office Supplies",
    "EQUIPMENT_ASSETS":     "Equipment & Assets",
    "DEPRECIATION":         "Depreciation",
    "MARKETING_ADS":        "Marketing & Advertising",
    "BANK_CHARGES":         "Bank Charges",
    "LOAN_REPAYMENT":       "Loan Repayment",
    "LOAN_INTEREST":        "Loan Interest",
    "PROFESSIONAL_FEES":    "Professional Fees",
    "GOVT_LEVIES":          "Government Levies",
    "INSURANCE":            "Insurance",
    "COMPANY_TAX":          "Company Tax (CIT)",
    "VAT_REMITTED":         "VAT Remitted",
    "WHT_REMITTED":         "WHT Remitted",
    "TRAVEL_ACCOMMODATION": "Travel & Accommodation",
    "TRAINING_DEVELOPMENT": "Training & Development",
    "OTHER":                "Other Expenses",
}

# True = FIRS allowable deduction, False = not deductible
TAX_DEDUCTIBLE: dict[str, bool] = {
    "COST_OF_SALES":        True,
    "SALARIES_WAGES":       True,
    "PAYE_TAX":             False,   # employer remittance, not a business deduction
    "PENSION_CONTRIBUTION": True,
    "NHF_CONTRIBUTION":     False,
    "STAFF_WELFARE":        True,
    "RENT_RATES":           True,
    "UTILITIES":            True,
    "MAINTENANCE_REPAIRS":  True,
    "FUEL_TRANSPORT":       True,
    "INTERNET_TELECOM":     True,
    "OFFICE_SUPPLIES":      True,
    "EQUIPMENT_ASSETS":     True,
    "DEPRECIATION":         True,
    "MARKETING_ADS":        True,
    "BANK_CHARGES":         True,
    "LOAN_REPAYMENT":       False,   # capital repayment, not deductible
    "LOAN_INTEREST":        True,
    "PROFESSIONAL_FEES":    True,
    "GOVT_LEVIES":          True,
    "INSURANCE":            True,
    "COMPANY_TAX":          False,   # CIT itself is not deductible
    "VAT_REMITTED":         False,   # pass-through tax
    "WHT_REMITTED":         False,   # pass-through tax
    "TRAVEL_ACCOMMODATION": True,
    "TRAINING_DEVELOPMENT": True,
    "OTHER":                True,
}

# Groupings for the P&L / By Category view
CATEGORY_GROUPS: dict[str, list[str]] = {
    "Cost of Sales":        ["COST_OF_SALES"],
    "Staff Costs":          ["SALARIES_WAGES", "PAYE_TAX", "PENSION_CONTRIBUTION",
                             "NHF_CONTRIBUTION", "STAFF_WELFARE"],
    "Premises":             ["RENT_RATES", "UTILITIES", "MAINTENANCE_REPAIRS"],
    "Operations":           ["FUEL_TRANSPORT", "INTERNET_TELECOM", "OFFICE_SUPPLIES",
                             "EQUIPMENT_ASSETS", "DEPRECIATION"],
    "Marketing":            ["MARKETING_ADS"],
    "Finance & Loans":      ["BANK_CHARGES", "LOAN_REPAYMENT", "LOAN_INTEREST"],
    "Professional & Legal": ["PROFESSIONAL_FEES", "INSURANCE"],
    "Compliance & Tax":     ["GOVT_LEVIES", "COMPANY_TAX", "VAT_REMITTED", "WHT_REMITTED"],
    "Other":                ["TRAVEL_ACCOMMODATION", "TRAINING_DEVELOPMENT", "OTHER"],
}


# ── SQLAlchemy Model ──────────────────────────────────────────────────────────

class Expense(Base):
    __tablename__ = "expenses"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id      = Column(
                           UUID(as_uuid=True),
                           ForeignKey("businesses.id", ondelete="CASCADE"),
                           nullable=False,
                           index=True,
                       )

    # Core fields — match CREATE TABLE exactly
    category         = Column(
                           SQLEnum(ExpenseCategory, name="expensecategory", create_type=False),
                           nullable=False,
                       )
    subcategory      = Column(String(100),  nullable=True)
    description      = Column(Text,         nullable=False)
    amount           = Column(Numeric(18, 2), nullable=False)
    expense_date     = Column(Date,         nullable=False)
    vendor_name      = Column(String(255),  nullable=True)
    reference_number = Column(String(100),  nullable=True)
    payment_method   = Column(
                           SQLEnum(ExpensePaymentMethod, name="expensepaymentmethod", create_type=False),
                           nullable=False,
                           default=ExpensePaymentMethod.CASH,
                       )
    is_tax_deductible = Column(Boolean, nullable=False, default=True)
    tax_year          = Column(Integer, nullable=True)
    is_recurring      = Column(Boolean, nullable=False, default=False)
    recurrence_period = Column(String(20), nullable=True)   # stored as VARCHAR in DB
    next_due_date     = Column(Date,    nullable=True)
    receipt_url       = Column(Text,    nullable=True)
    notes             = Column(Text,    nullable=True)

    # Timestamps — TIMESTAMP in DB
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    business = relationship("Business", back_populates="expenses")

    def __repr__(self) -> str:
        return f"<Expense {self.category} ₦{self.amount} {self.expense_date}>"