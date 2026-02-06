import requests

BASE_URL = "http://localhost:8000/api/v1"

# Login
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": "admin@example.com", "password": "Admin@123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get all documents
response = requests.get(f"{BASE_URL}/documents?page=1&page_size=10", headers=headers)
documents = response.json()["documents"]

# Print the latest document with error
if documents:
    latest = documents[0]
    print(f"\n{'='*80}")
    print(f"LATEST DOCUMENT ERROR")
    print(f"{'='*80}\n")
    print(f"Document ID: {latest['id']}")
    print(f"Status: {latest['status']}")
    print(f"Processing Error: {latest.get('processing_error', 'No error message')}")
    print(f"\n{'='*80}\n")
else:
    print("No documents found")