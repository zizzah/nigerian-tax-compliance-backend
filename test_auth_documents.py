"""
TaxFlow NG — Auth + Document Endpoint Tests
============================================
Tests auth flow and all document endpoints.

Usage:
    python test_auth_documents.py

Requirements:
    pip install requests
"""

import requests
import json
import sys
import time
import base64
import io
from datetime import date
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL      = "http://127.0.0.1:8000/api/v1"
TEST_EMAIL    = f"testuser_{int(time.time())}@taxflow-test.com"
TEST_PASSWORD = "TestPass@123"

# ── Terminal colours ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── Shared state ──────────────────────────────────────────────────────────────
state: dict = {
    "token":       None,
    "document_id": None,   # documents.id returned from upload
    "receipt_id":  None,   # receipts.id found after processing
}

passed  = 0
failed  = 0
skipped = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {state['token']}"}


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


def post(path: str, payload: dict = None, auth: bool = True) -> requests.Response:
    h = auth_headers() if auth else {}
    h["Content-Type"] = "application/json"
    return requests.post(f"{BASE_URL}{path}", json=payload, headers=h, timeout=30)


def get(path: str, params: dict = None, auth: bool = True) -> requests.Response:
    h = auth_headers() if auth else {}
    return requests.get(f"{BASE_URL}{path}", params=params, headers=h, timeout=30)


def patch(path: str, payload: dict, auth: bool = True) -> requests.Response:
    h = auth_headers() if auth else {}
    h["Content-Type"] = "application/json"
    return requests.patch(f"{BASE_URL}{path}", json=payload, headers=h, timeout=30)


def delete(path: str, auth: bool = True) -> requests.Response:
    h = auth_headers() if auth else {}
    return requests.delete(f"{BASE_URL}{path}", headers=h, timeout=30)


def poll_status(document_id: str, max_wait: int = 60) -> Optional[str]:
    """
    Poll GET /documents/{id}/status until COMPLETED or FAILED.
    Returns the final status string, or None if timed out.
    """
    print(f"    → polling status for {document_id} (max {max_wait}s)...")
    for i in range(max_wait):
        time.sleep(1)
        r = get(f"/documents/{document_id}/status")
        if r.status_code == 200:
            status = r.json().get("status")
            if i % 5 == 0:
                print(f"    → [{i+1}s] status: {status}")
            if status in ("COMPLETED", "FAILED"):
                print(f"    → done after {i+1}s — {status}")
                return status
        else:
            print(f"    → [{i+1}s] status endpoint returned {r.status_code}")
    print(f"    → timed out after {max_wait}s")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 1. AUTH
# ══════════════════════════════════════════════════════════════════════════════

def test_auth():
    section("Authentication")

    # Register
    r = post("/auth/register", {
        "email":            TEST_EMAIL,
        "password":         TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
    }, auth=False)
    p("POST /auth/register", r.status_code == 201,
      f"{r.status_code} {r.text[:150]}")

    # Login
    r = post("/auth/login", {
        "email":    TEST_EMAIL,
        "password": TEST_PASSWORD,
    }, auth=False)
    ok = r.status_code == 200 and "access_token" in r.json()
    p("POST /auth/login", ok, f"{r.status_code} {r.text[:150]}")
    if ok:
        state["token"] = r.json()["access_token"]
        print(f"    → token acquired")

    # Wrong password
    r = post("/auth/login", {
        "email":    TEST_EMAIL,
        "password": "WrongPassword",
    }, auth=False)
    p("POST /auth/login (wrong password → 401)", r.status_code == 401,
      f"{r.status_code}")

    # Me
    if state["token"]:
        r = get("/users/me")
        p("GET /users/me", r.status_code == 200,
          f"{r.status_code} {r.text[:150]}")

    # Business setup — documents endpoint requires a business
    if state["token"]:
        r = post("/businesses", {
            "business_name": "TaxFlow Doc Test Ltd",
            "business_type": "Limited Liability Company",
            "industry":      "Technology",
            "vat_registered": False,
            "phone":         "+2348012345678",
            "email":         "doctest@taxflowtest.com",
            "city":          "Lagos",
            "state":         "Lagos",
        })
        p("POST /businesses (setup for document tests)",
          r.status_code == 201,
          f"{r.status_code} {r.text[:150]}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════════

def test_documents():
    section("Documents")

    if not state["token"]:
        skip("all document tests", "no token")
        return

    # ── Statistics ────────────────────────────────────────────────────────────
    r = get("/documents/statistics/summary")
    p("GET /documents/statistics/summary", r.status_code == 200,
      f"{r.status_code} {r.text[:150]}")

    # ── List receipts ─────────────────────────────────────────────────────────
    r = get("/documents/receipts")
    p("GET /documents/receipts", r.status_code == 200,
      f"{r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        print(f"    → total receipts: {r.json().get('total', 0)}")

    # ── List bank statements ──────────────────────────────────────────────────
    r = get("/documents/bank-statements")
    p("GET /documents/bank-statements", r.status_code == 200,
      f"{r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        print(f"    → total statements: {r.json().get('total', 0)}")

    # ── Upload receipt ────────────────────────────────────────────────────────
    # Using a 1x1 white PNG — OCR will fail gracefully and set status=FAILED
    # That is expected and correct behavior for a blank image
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
    )
    png_bytes = base64.b64decode(png_b64)

    upload_r = requests.post(
        f"{BASE_URL}/documents/upload",
        headers=auth_headers(),
        files={"file": ("test_receipt.png", io.BytesIO(png_bytes), "image/png")},
        data={"document_type": "RECEIPT", "notes": "automated test"},
        timeout=60,
    )
    p("POST /documents/upload (RECEIPT)", upload_r.status_code == 201,
      f"{upload_r.status_code} {upload_r.text[:150]}")

    if upload_r.status_code != 201:
        print(f"    → upload failed, skipping remaining document tests")
        return

    state["document_id"] = upload_r.json().get("document_id")
    print(f"    → document_id: {state['document_id']}")

    # ── Poll status ───────────────────────────────────────────────────────────
    final_status = poll_status(state["document_id"], max_wait=60)
    p(
        f"GET /documents/{{id}}/status (reached terminal state)",
        final_status in ("COMPLETED", "FAILED"),
        "timed out" if final_status is None else "",
    )
    print(f"    → final status: {final_status}")

    # ── Get receipt by document_id ────────────────────────────────────────────
    r = get(f"/documents/{state['document_id']}/receipt")
    p("GET /documents/{document_id}/receipt", r.status_code in (200, 404),
      f"{r.status_code} {r.text[:150]}")

    if r.status_code == 200:
        data = r.json()
        state["receipt_id"] = data.get("id")
        print(f"    → receipt_id:    {state['receipt_id']}")
        print(f"    → vendor_name:   {data.get('vendor_name')}")
        print(f"    → total_amount:  {data.get('total_amount')}")
        print(f"    → confidence:    {data.get('confidence_score')}")
        print(f"    → requires_review: {data.get('requires_review')}")
    else:
        print(f"    → no receipt row (expected for blank image with FAILED status)")

    # ── Get receipt by receipt_id (if we have one) ────────────────────────────
    if state["receipt_id"]:
        r = get(f"/documents/receipts/{state['receipt_id']}")
        p("GET /documents/receipts/{receipt_id}", r.status_code == 200,
          f"{r.status_code} {r.text[:150]}")

        # ── Patch receipt ─────────────────────────────────────────────────────
        r = patch(f"/documents/receipts/{state['receipt_id']}", {
            "vendor_name": "Manual Override Vendor",
            "category":    "Office Supplies",
            "notes":       "manually reviewed",
        })
        p("PATCH /documents/receipts/{receipt_id}", r.status_code == 200,
          f"{r.status_code} {r.text[:150]}")
        if r.status_code == 200:
            print(f"    → vendor_name after patch: {r.json().get('vendor_name')}")
    else:
        skip("GET /documents/receipts/{receipt_id}", "no receipt row created")
        skip("PATCH /documents/receipts/{receipt_id}", "no receipt row created")

    # ── Delete document (CASCADE removes receipt row too) ─────────────────────
    r = delete(f"/documents/{state['document_id']}")
    p("DELETE /documents/{document_id}", r.status_code == 204,
      f"{r.status_code} {r.text[:150]}")

    if r.status_code == 204:
        # Verify receipt row is gone
        if state["receipt_id"]:
            r = get(f"/documents/receipts/{state['receipt_id']}")
            p("Receipt CASCADE deleted (404 after document delete)",
              r.status_code == 404,
              f"{r.status_code}")
        state["document_id"] = None
        state["receipt_id"]  = None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  TaxFlow NG — Auth + Document Tests{RESET}")
    print(f"  Target: {BASE_URL}")
    print(f"{BOLD}{'═' * 60}{RESET}")

    test_auth()
    test_documents()

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