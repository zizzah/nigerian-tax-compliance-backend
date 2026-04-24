"""
Models Package
Location: app/models/__init__.py

Import ALL models here so Alembic can detect them and relationships resolve.
"""
from app.core.base import Base

# Core auth & business
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer

# Products & invoicing
from app.models.product import Product
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment

# Payments / Paystack
from app.models.payment_link import PaymentLink

# AI document processing
from app.models.document import Document, DocumentType, ProcessingStatus

# Expense tracking
from app.models.expense import (
    Expense,
    ExpenseCategory,
    ExpensePaymentMethod,
    CATEGORY_LABELS,
    TAX_DEDUCTIBLE,
    CATEGORY_GROUPS,
)

# Payment reminders
from app.models.reminder import ReminderRule, ReminderLog

# Sales targets
from app.models.sales_target import SalesTarget, split_annual_target

# AI Insights  ← NEW
from app.models.ai_insight import AIInsight
from app.models.bank_reconciliation import BankReconciliation


__all__ = [
    "Base",
    # Auth / business
    "User",
    "Business",
    "Customer",
    # Invoicing
    "Product",
    "Invoice",
    "InvoiceItem",
    "Payment",
    "PaymentLink",
    # Documents
    "Document",
    "DocumentType",
    "ProcessingStatus",
    # Expenses
    "Expense",
    "ExpenseCategory",
    "ExpensePaymentMethod",
    "CATEGORY_LABELS",
    "TAX_DEDUCTIBLE",
    "CATEGORY_GROUPS",
    # Reminders
    "ReminderRule",
    "ReminderLog",
    # Targets
    "SalesTarget",
    "split_annual_target",
    # AI
    "AIInsight",
    "BankReconciliation",
]
