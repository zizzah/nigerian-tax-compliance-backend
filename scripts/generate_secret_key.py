"""
Generate Secret Key for JWT
Usage: python scripts/generate_secret_key.py
"""
import secrets

print("=" * 60)
print("🔑 SECRET KEY GENERATOR")
print("=" * 60)
print("")
print("Add this to your .env file:")
print("")
print(f"SECRET_KEY={secrets.token_urlsafe(32)}")
print("")
print("Copy the line above and paste it into your .env file")
print("=" * 60)