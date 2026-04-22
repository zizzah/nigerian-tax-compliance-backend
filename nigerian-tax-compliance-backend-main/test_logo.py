"""
Standalone logo upload test — run from project root.
Does NOT use conftest.py
"""
import io
import pytest
import httpx
from PIL import Image

BASE_URL      = "http://127.0.0.1:8000"
TEST_EMAIL    = "chukwudiokolo416@gmail.com"
TEST_PASSWORD = "Golden@1"


def get_token() -> str:
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30.0,  # add this
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


def make_test_image(fmt: str = "PNG", size: tuple = (200, 200)) -> bytes:
    img = Image.new("RGB", size, color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.read()


class TestLogoUpload:

    def setup_method(self):
        self.token = get_token()
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_upload_valid_png(self):
        image_bytes = make_test_image(fmt="PNG")
        response = httpx.post(
            f"{BASE_URL}/api/v1/businesses/me/logo",
            headers=self.headers,
            files={"logo": ("test_logo.png", image_bytes, "image/png")},
            timeout=30.0,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["logo_url"] is not None
        assert "cloudinary.com" in data["logo_url"], (
            f"Expected Cloudinary URL, got: {data['logo_url']}"
        )
        print(f"\n Logo URL: {data['logo_url']}")

    def test_upload_valid_jpeg(self):
        image_bytes = make_test_image(fmt="JPEG")
        response = httpx.post(
            f"{BASE_URL}/api/v1/businesses/me/logo",
            headers=self.headers,
            files={"logo": ("test_logo.jpg", image_bytes, "image/jpeg")},
            timeout=30.0,
        )
        assert response.status_code == 200, response.text
        assert "cloudinary.com" in response.json()["logo_url"]

    def test_upload_invalid_file_type(self):
        fake_pdf = b"%PDF-1.4 fake pdf content"
        response = httpx.post(
            f"{BASE_URL}/api/v1/businesses/me/logo",
            headers=self.headers,
            files={"logo": ("document.pdf", fake_pdf, "application/pdf")},
            timeout=30.0,

        )
        print(f"\nResponse: {response.json()}") 
        assert response.status_code == 400, response.text
        assert "Invalid file type" in response.json()["error"]["message"]

    def test_upload_oversized_file(self):
        large_bytes = b"0" * (6 * 1024 * 1024)  # 6MB of raw bytes
        response = httpx.post(
            f"{BASE_URL}/api/v1/businesses/me/logo",
            headers=self.headers,
            files={"logo": ("large.png", large_bytes, "image/png")},
            timeout=30.0,

        )
        assert response.status_code == 400, response.text
        assert "too large" in response.json()["error"]["message"].lower()

    def test_upload_requires_auth(self):
        image_bytes = make_test_image()
        response = httpx.post(
            f"{BASE_URL}/api/v1/businesses/me/logo",
            files={"logo": ("test.png", image_bytes, "image/png")},
            timeout=30.0,
        )
        assert response.status_code == 403, response.text