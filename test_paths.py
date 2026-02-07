# test_paths.py
from pathlib import Path
import os

# Print current directory
print(f"Current directory: {os.getcwd()}")

# Test upload path
upload_base = Path("uploads") / "documents"
print(f"Upload base: {upload_base}")
print(f"Absolute path: {upload_base.absolute()}")
print(f"Exists: {upload_base.exists()}")

# Create test business folder
test_business_id = "123e4567-e89b-12d3-a456-426614174000"
upload_dir = upload_base / test_business_id
upload_dir.mkdir(parents=True, exist_ok=True)
print(f"Created: {upload_dir.absolute()}")