"""
TaxFlow NG — Full Endpoint Test Suite
======================================
Tests every endpoint on the hosted Render backend.

Usage:
    python test_all_endpoints.py

Requirements:
    pip install requests
"""

import requests
import json
import sys
import time
from datetime import date, timedelta
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000/api/v1"
# BASE_URL = "https://nigerian-tax-compliance-backend.onrender.com/api/v1"

# Test credentials — change if you already have an account on the hosted server
TEST_EMAIL    = f"testuser_{int(time.time())}@taxflow-test.com"
TEST_PASSWORD = "TestPass@123"

# Colours for terminal output
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── State shared between tests ────────────────────────────────────────────────
state: dict = {
    "token":        None,
    "business_id":  None,
    "customer_id":  None,
    "product_id":   None,
    "invoice_id":   None,
    "payment_id":   None,
    "expense_id":   None,
    "document_id":  None,
    "receipt_id":   None,   # set after background processing completes
    "statement_id": None,   # set after background processing completes
    "reminder_id":  None,
    "target_year":  date.today().year,
}

passed = 0
failed = 0
skipped = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def headers() -> dict:
    return {"Authorization": f"Bearer {state['token']}", "Content-Type": "application/json"}


def p(label: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        failed += 1
        print(f"  {RED}✗{RESET} {label}  {RED}{detail}{RESET}")


def section(title: str):
    print(f"\n{BOLD}{BLUE}── {title} {'─' * (55 - len(title))}{RESET}")


def skip(label: str, reason: str = ""):
    global skipped
    skipped += 1
    print(f"  {YELLOW}○{RESET} {label}  {YELLOW}(skipped: {reason}){RESET}")


def post(path, payload=None, auth=True):
    h = headers() if auth else {"Content-Type": "application/json"}
    r = requests.post(f"{BASE_URL}{path}", json=payload, headers=h, timeout=30)
    return r


def get(path, params=None, auth=True):
    h = headers() if auth else {}
    r = requests.get(f"{BASE_URL}{path}", params=params, headers=h, timeout=30)
    return r


def patch(path, payload, auth=True):
    h = headers() if auth else {"Content-Type": "application/json"}
    r = requests.patch(f"{BASE_URL}{path}", json=payload, headers=h, timeout=30)
    return r


def delete(path, auth=True):
    h = headers() if auth else {}
    r = requests.delete(f"{BASE_URL}{path}", headers=h, timeout=30)
    return r


# ══════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM HEALTH
# ══════════════════════════════════════════════════════════════════════════════

def test_system():
    section("System Health")

    r = requests.get(BASE_URL.replace("/api/v1", "/"), timeout=15)
    p("GET /  (root)", r.status_code == 200)

    r = requests.get(BASE_URL.replace("/api/v1", "/alive"), timeout=15)
    p("GET /alive  (liveness probe)", r.status_code == 200)

    r = requests.get(BASE_URL.replace("/api/v1", "/health"), timeout=15)
    p("GET /health  (health check)", r.status_code == 200,
      f"status={r.status_code}")

    r = requests.get(BASE_URL.replace("/api/v1", "/pool-status"), timeout=15)
    p("GET /pool-status", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 2. AUTH
# ══════════════════════════════════════════════════════════════════════════════

def test_auth():
    section("Authentication")

    # Register
    r = post("/auth/register", {
        "email":            TEST_EMAIL,
        "password":         TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
    }, auth=False)
    p("POST /auth/register", r.status_code == 201, f"{r.status_code} {r.text[:100]}")

    # Login
    r = post("/auth/login", {
        "email":    TEST_EMAIL,
        "password": TEST_PASSWORD,
    }, auth=False)
    ok = r.status_code == 200 and "access_token" in r.json()
    p("POST /auth/login", ok, f"{r.status_code} {r.text[:100]}")
    if ok:
        state["token"] = r.json()["access_token"]

    # Wrong password
    r = post("/auth/login", {
        "email":    TEST_EMAIL,
        "password": "WrongPassword",
    }, auth=False)
    p("POST /auth/login  (wrong password → 401)", r.status_code == 401)

    # Forgot password
    r = post("/auth/forgot-password", {"email": TEST_EMAIL}, auth=False)
    p("POST /auth/forgot-password", r.status_code == 200)

    # Health
    r = get("/auth/health", auth=False)
    p("GET /auth/health", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 3. USERS
# ══════════════════════════════════════════════════════════════════════════════

def test_users():
    section("Users")
    if not state["token"]:
        skip("all user tests", "no token"); return

    r = get("/users/me")
    p("GET /users/me", r.status_code == 200)

    r = patch("/users/me", {"phone": "+2348012345678"})
    p("PATCH /users/me", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 4. BUSINESSES
# ══════════════════════════════════════════════════════════════════════════════

def test_businesses():
    section("Businesses")
    if not state["token"]:
        skip("all business tests", "no token"); return

    r = post("/businesses", {
        "business_name": "TaxFlow Test Ltd",
        "business_type": "Limited Liability Company",
        "industry":      "Technology",
        "vat_registered": False,
        "phone":         "+2348012345678",
        "email":         "biz@taxflowtest.com",
        "city":          "Lagos",
        "state":         "Lagos",
    })
    p("POST /businesses", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["business_id"] = r.json()["id"]

    r = get("/businesses/me")
    p("GET /businesses/me", r.status_code == 200)

    r = patch("/businesses/me", {"business_name": "TaxFlow Test Ltd (Updated)"})
    p("PATCH /businesses/me", r.status_code == 200)

    r = get("/businesses/me/summary")
    p("GET /businesses/me/summary", r.status_code == 200)

    r = get("/businesses/me/next-invoice-number")
    p("GET /businesses/me/next-invoice-number", r.status_code == 200)

    r = get("/businesses/me/paystack/status")
    p("GET /businesses/me/paystack/status", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 5. CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════

def test_customers():
    section("Customers")
    if not state["token"]:
        skip("all customer tests", "no token"); return

    r = post("/customers", {
        "name":               "Acme Nigeria Ltd",
        "email":              "acme@example.ng",
        "phone":              "+2349012345678",
        "customer_type":      "Business",
        "payment_terms_days": 30,
        "city":               "Abuja",
        "state":              "FCT",
    })
    p("POST /customers", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["customer_id"] = r.json()["id"]

    r = get("/customers")
    p("GET /customers", r.status_code == 200)

    r = get("/customers/summary")
    p("GET /customers/summary", r.status_code == 200)

    r = get("/customers/search", params={"q": "Acme"})
    p("GET /customers/search", r.status_code == 200)

    r = get("/customers/stats/overview")
    p("GET /customers/stats/overview", r.status_code == 200)

    if state["customer_id"]:
        r = get(f"/customers/{state['customer_id']}")
        p("GET /customers/{id}", r.status_code == 200)

        r = patch(f"/customers/{state['customer_id']}", {"notes": "Test customer"})
        p("PATCH /customers/{id}", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 6. PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════

def test_products():
    section("Products")
    if not state["token"]:
        skip("all product tests", "no token"); return

    r = post("/products", {
        "name":        "Web Design Service",
        "unit_price":  150000,
        "cost_price":  50000,
        "tax_rate":    7.5,
        "is_taxable":  True,
        "category":    "Services",
        "description": "Professional web design",
    })
    p("POST /products", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["product_id"] = r.json()["id"]

    r = get("/products")
    p("GET /products", r.status_code == 200)

    r = get("/products/summary")
    p("GET /products/summary", r.status_code == 200)

    r = get("/products/categories/list")
    p("GET /products/categories/list", r.status_code == 200)

    if state["product_id"]:
        r = get(f"/products/{state['product_id']}")
        p("GET /products/{id}", r.status_code == 200)

        r = patch(f"/products/{state['product_id']}", {"unit_price": 160000})
        p("PATCH /products/{id}", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 7. INVOICES
# ══════════════════════════════════════════════════════════════════════════════

def test_invoices():
    section("Invoices")
    if not state["token"]:
        skip("all invoice tests", "no token"); return
    if not state["customer_id"]:
        skip("all invoice tests", "no customer"); return

    today    = date.today().isoformat()
    due_date = (date.today() + timedelta(days=30)).isoformat()

    item = {
        "description": "Web Design Service",
        "quantity":    1,
        "unit_price":  150000,
        "tax_rate":    7.5,
        "sort_order":  0,
    }
    if state["product_id"]:
        item["product_id"] = state["product_id"]

    r = post("/invoices", {
        "customer_id":    state["customer_id"],
        "issue_date":     today,
        "due_date":       due_date,
        "discount_amount": 0,
        "notes":          "Test invoice",
        "items":          [item],
    })
    p("POST /invoices", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["invoice_id"] = r.json()["id"]

    r = get("/invoices")
    p("GET /invoices", r.status_code == 200)

    r = get("/invoices/stats/overview")
    p("GET /invoices/stats/overview", r.status_code == 200)

    if state["invoice_id"]:
        r = get(f"/invoices/{state['invoice_id']}")
        p("GET /invoices/{id}", r.status_code == 200)

        r = patch(f"/invoices/{state['invoice_id']}", {"notes": "Updated note"})
        p("PATCH /invoices/{id}", r.status_code == 200)

        r = requests.get(
            f"{BASE_URL}/invoices/{state['invoice_id']}/pdf",
            headers=headers(), timeout=30,
        )
        p("GET /invoices/{id}/pdf", r.status_code == 200,
          f"content-type={r.headers.get('content-type','')}")

        r = post(f"/invoices/{state['invoice_id']}/finalize")
        p("POST /invoices/{id}/finalize", r.status_code == 200,
          f"{r.status_code} {r.text[:80]}")

        r = get(f"/invoices/{state['invoice_id']}/email-status")
        p("GET /invoices/{id}/email-status", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 8. PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

def test_payments():
    section("Payments")
    if not state["token"] or not state["invoice_id"]:
        skip("all payment tests", "no invoice"); return

    r = post("/payments", {
        "invoice_id":     state["invoice_id"],
        "amount":         150000 * 1.075,   # full amount incl VAT
        "payment_date":   date.today().isoformat(),
        "payment_method": "BANK_TRANSFER",
        "reference_number": "TRX-TEST-001",
    })
    p("POST /payments", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["payment_id"] = r.json()["id"]

    r = get("/payments")
    p("GET /payments", r.status_code == 200)

    if state["payment_id"]:
        r = get(f"/payments/{state['payment_id']}")
        p("GET /payments/{id}", r.status_code == 200)

        r = patch(f"/payments/{state['payment_id']}", {"notes": "Verified"})
        p("PATCH /payments/{id}", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 9. EXPENSES
# ══════════════════════════════════════════════════════════════════════════════

def test_expenses():
    section("Expenses")
    if not state["token"]:
        skip("all expense tests", "no token"); return

    r = post("/expenses", {
        "category":     "UTILITIES",
        "description":  "EKEDC electricity bill",
        "amount":       25000,
        "expense_date": date.today().isoformat(),
        "vendor_name":  "EKEDC",
        "payment_method": "BANK_TRANSFER",
        "is_recurring": True,
        "recurrence_period": "monthly",
    })
    p("POST /expenses", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        state["expense_id"] = r.json()["id"]

    r = get("/expenses")
    p("GET /expenses", r.status_code == 200)

    r = get("/expenses/summary", params={"year": date.today().year})
    p("GET /expenses/summary", r.status_code == 200)

    r = get("/expenses/recurring")
    p("GET /expenses/recurring", r.status_code == 200)

    if state["expense_id"]:
        r = get(f"/expenses/{state['expense_id']}")
        p("GET /expenses/{id}", r.status_code == 200)

        r = patch(f"/expenses/{state['expense_id']}", {"amount": 26000})
        p("PATCH /expenses/{id}", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 10. ANALYTICS / DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def test_analytics():
    section("Analytics")
    if not state["token"]:
        skip("all analytics tests", "no token"); return

    r = get("/analytics/dashboard")
    p("GET /analytics/dashboard", r.status_code == 200, f"{r.status_code}")


# ══════════════════════════════════════════════════════════════════════════════
# 11. DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════════

def _poll_for_completion(document_id: str, max_wait: int = 30) -> Optional[str]:
    """
    Poll GET /documents/receipts/{id} until status is COMPLETED or FAILED.
    Returns final status string or None on timeout.
    """
    for _ in range(max_wait):
        time.sleep(1)
        r = get(f"/documents/receipts/{document_id}")
        if r.status_code == 200:
            status = r.json().get("status")
            if status in ("COMPLETED", "FAILED"):
                return status
        elif r.status_code == 404:
            # Receipt row not created yet — still processing
            pass
    return None


def test_documents():
    section("Documents")
    if not state["token"]:
        skip("all document tests", "no token"); return

    # ── Statistics ────────────────────────────────────────────────────────────
    r = get("/documents/statistics/summary")
    p("GET /documents/statistics/summary", r.status_code == 200,
      f"{r.status_code} {r.text[:100]}")

    # ── List receipts ─────────────────────────────────────────────────────────
    r = get("/documents/receipts")
    p("GET /documents/receipts", r.status_code == 200,
      f"{r.status_code} {r.text[:100]}")

    # ── List bank statements ──────────────────────────────────────────────────
    r = get("/documents/bank-statements")
    p("GET /documents/bank-statements", r.status_code == 200,
      f"{r.status_code} {r.text[:100]}")

    # ── Upload receipt (1x1 white PNG — triggers OCR + Groq extraction) ───────
    import base64, io
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
    )
    png_bytes = base64.b64decode(png_b64)

    upload_r = requests.post(
        f"{BASE_URL}/documents/upload",
        headers={"Authorization": f"Bearer {state['token']}"},
        files={"file": ("test_receipt.png", io.BytesIO(png_bytes), "image/png")},
        data={"document_type": "RECEIPT", "notes": "automated test"},
        timeout=60,
    )
    p("POST /documents/upload (RECEIPT)", upload_r.status_code == 201,
      f"{upload_r.status_code} {upload_r.text[:100]}")

    if upload_r.status_code == 201:
        state["document_id"] = upload_r.json().get("document_id")
        print(f"    → document_id: {state['document_id']} — polling for completion...")

        # Poll until background task finishes (max 30s)
        final_status = _poll_for_completion(state["document_id"])
        p(
            f"  Background processing completed (status={final_status})",
            final_status in ("COMPLETED", "FAILED"),  # FAILED is ok — 1x1 pixel has no text
            f"timed out after 30s" if final_status is None else "",
        )

    # ── GET /documents/receipts/{id} ──────────────────────────────────────────
    if state["document_id"]:
        r = get(f"/documents/receipts/{state['document_id']}")
        p("GET /documents/receipts/{id}", r.status_code in (200, 404),
          f"{r.status_code} {r.text[:100]}")

        if r.status_code == 200:
            state["receipt_id"] = state["document_id"]
            data = r.json()
            print(f"    → status:      {data.get('status')}")
            print(f"    → vendor_name: {data.get('vendor_name')}")
            print(f"    → total_amount:{data.get('total_amount')}")
            print(f"    → requires_review: {data.get('requires_review')}")

    # ── PATCH /documents/receipts/{id} ────────────────────────────────────────
    if state["receipt_id"]:
        r = patch(f"/documents/receipts/{state['receipt_id']}", {
            "vendor_name": "Manual Override Vendor",
            "category":    "Office Supplies",
        })
        p("PATCH /documents/receipts/{id}", r.status_code == 200,
          f"{r.status_code} {r.text[:100]}")

    # ── DELETE /documents/{id} (CASCADE deletes receipt row too) ─────────────
    if state["document_id"]:
        r = delete(f"/documents/{state['document_id']}")
        p("DELETE /documents/{id}", r.status_code == 204,
          f"{r.status_code}")
        if r.status_code == 204:
            state["document_id"] = None
            state["receipt_id"]  = None


# ══════════════════════════════════════════════════════════════════════════════
# 12. REMINDERS
# ══════════════════════════════════════════════════════════════════════════════

def test_reminders():
    section("Reminders")
    if not state["token"]:
        skip("all reminder tests", "no token"); return

    r = get("/reminders/rules")
    p("GET /reminders/rules", r.status_code == 200)

    r = post("/reminders/rules", {
        "name":          "7-day chase",
        "days_overdue":  7,
        "cooldown_days": 7,
        "is_active":     True,
    })
    p("POST /reminders/rules", r.status_code == 201, f"{r.status_code} {r.text[:100]}")
    if r.status_code == 201:
        state["reminder_id"] = r.json()["id"]

    r = get("/reminders/preview")
    p("GET /reminders/preview", r.status_code == 200)

    r = get("/reminders/logs")
    p("GET /reminders/logs", r.status_code == 200)

    r = post("/reminders/trigger")
    p("POST /reminders/trigger", r.status_code == 200)

    if state["reminder_id"]:
        r = requests.put(
            f"{BASE_URL}/reminders/rules/{state['reminder_id']}",
            json={"cooldown_days": 14},
            headers=headers(),
            timeout=30,
        )
        p("PUT /reminders/rules/{id}", r.status_code == 200)

        r = delete(f"/reminders/rules/{state['reminder_id']}")
        p("DELETE /reminders/rules/{id}", r.status_code == 204)


# ══════════════════════════════════════════════════════════════════════════════
# 13. SALES TARGETS
# ══════════════════════════════════════════════════════════════════════════════

def test_targets():
    section("Sales Targets")
    if not state["token"]:
        skip("all target tests", "no token"); return

    year = state["target_year"]

    r = post("/targets", {
        "year":           year,
        "annual_target":  12000000,
    })
    p("POST /targets", r.status_code == 201, f"{r.status_code} {r.text[:100]}")

    r = get("/targets")
    p("GET /targets", r.status_code == 200)

    r = get(f"/targets/{year}")
    p(f"GET /targets/{year}", r.status_code == 200)

    r = post(f"/targets/{year}/ai-advice")
    p(f"POST /targets/{year}/ai-advice", r.status_code == 200,
      f"{r.status_code} {r.text[:80]}")

    r = delete(f"/targets/{year}")
    p(f"DELETE /targets/{year}", r.status_code == 204)


# ══════════════════════════════════════════════════════════════════════════════
# 14. PAYSTACK
# ══════════════════════════════════════════════════════════════════════════════

def test_paystack():
    section("Paystack")
    if not state["token"] or not state["invoice_id"]:
        skip("paystack link test", "no invoice"); return

    # Invoice is already PAID at this point so link creation will fail —
    # that's expected. We just check the endpoint is reachable.
    r = post(f"/paystack/links/{state['invoice_id']}")
    p("POST /paystack/links/{invoice_id}",
      r.status_code in (200, 400),   # 400 = already paid / draft = expected
      f"{r.status_code}")


# ══════════════════════════════════════════════════════════════════════════════
# 15. STOCK MOVEMENTS
# ══════════════════════════════════════════════════════════════════════════════

def test_stock():
    section("Stock Movements")
    if not state["token"]:
        skip("all stock tests", "no token"); return

    r = get("/stock-movements")
    p("GET /stock-movements", r.status_code == 200, f"{r.status_code}")

    if state["product_id"]:
        # First enable inventory tracking on the product
        patch(f"/products/{state['product_id']}", {
            "track_inventory":    True,
            "quantity_in_stock":  100,
        })

        r = post("/stock-movements/restock", {
            "product_id": state["product_id"],
            "quantity":   50,
            "note":       "test restock",
        })
        p("POST /stock-movements/restock", r.status_code == 200,
          f"{r.status_code} {r.text[:80]}")

        r = get(f"/stock-movements/{state['product_id']}")
        p(f"GET /stock-movements/{{product_id}}", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════════════════
# 16. CLEANUP — delete test data (optional, comment out to keep)
# ══════════════════════════════════════════════════════════════════════════════

def test_cleanup():
    section("Cleanup (soft deletes)")
    if not state["token"]:
        return

    if state["expense_id"]:
        r = delete(f"/expenses/{state['expense_id']}")
        p("DELETE /expenses/{id}", r.status_code == 204)

    if state["customer_id"]:
        r = delete(f"/customers/{state['customer_id']}")
        p("DELETE /customers/{id}  (soft)", r.status_code == 204)

    if state["product_id"]:
        r = delete(f"/products/{state['product_id']}")
        p("DELETE /products/{id}  (soft)", r.status_code == 204)

    # document cleanup is handled inside test_documents itself


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  TaxFlow NG — Full API Test Suite{RESET}")
    print(f"  Target: {BASE_URL}")
    print(f"{BOLD}{'═' * 60}{RESET}")

    test_system()
    test_auth()
    test_users()
    test_businesses()
    test_customers()
    test_products()
    test_invoices()
    test_payments()
    test_expenses()
    test_analytics()
    test_documents()
    test_reminders()
    test_targets()
    test_paystack()
    test_stock()
    test_cleanup()

    total = passed + failed + skipped
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  Results: {total} tests{RESET}")
    print(f"  {GREEN}{passed} passed{RESET}  "
          f"{RED}{failed} failed{RESET}  "
          f"{YELLOW}{skipped} skipped{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()