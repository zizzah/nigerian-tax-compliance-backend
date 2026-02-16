"""
Performance Test for List Endpoints
====================================

This test specifically measures the performance of list endpoints
to verify they meet production requirements (<500ms).

Usage:
    python test_performance.py
"""

import requests
import time
import json
from datetime import datetime
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TOKEN = None  # Will be set after login


class PerformanceTest:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.token = None
        self.results = []
    
    def setup(self):
        """Setup: Register and login to get token"""
        print("Setting up test user...")
        
        # Register
        register_data = {
            "email": f"perftest_{int(time.time())}@test.com",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "phone": "+2348012345678"
        }
        
        resp = requests.post(f"{self.base_url}/api/v1/auth/register", json=register_data)
        if resp.status_code != 201:
            print(f"❌ Registration failed: {resp.status_code}")
            return False
        
        # Login
        login_data = {
            "email": register_data["email"],
            "password": register_data["password"]
        }
        
        resp = requests.post(f"{self.base_url}/api/v1/auth/login", json=login_data)
        if resp.status_code != 200:
            print(f"❌ Login failed: {resp.status_code}")
            return False
        
        self.token = resp.json().get("access_token")
        print(f"✓ Setup complete. Token: {self.token[:20]}...")
        return True
    
    def create_business(self):
        """Create business profile"""
        print("\nCreating business profile...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        business_data = {
            "business_name": "Performance Test Business",
            "business_type": "Limited Liability Company",
            "industry": "Technology",
            "tin": f"PERF-{int(time.time())}",
            "vat_registered": True,
            "phone": "+2348012345678",
            "email": "business@perftest.com",
            "address": "123 Test Street",
            "city": "Lagos",
            "state": "Lagos"
        }
        
        resp = requests.post(
            f"{self.base_url}/api/v1/businesses/",
            json=business_data,
            headers=headers
        )
        
        if resp.status_code == 201:
            print("✓ Business created")
            return True
        elif resp.status_code == 400 and "already exists" in resp.text:
            print("✓ Business already exists")
            return True
        else:
            print(f"❌ Business creation failed: {resp.status_code}")
            return False
    
    def create_test_customers(self, count: int = 10):
        """Create test customers"""
        print(f"\nCreating {count} test customers...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        for i in range(count):
            customer_data = {
                "name": f"Customer {i+1}",
                "email": f"customer{i+1}@perftest.com",
                "phone": f"+234801234567{i}",
                "address": f"{i+1} Test Avenue",
                "city": "Lagos",
                "state": "Lagos",
                "tin": f"CUST-{i+1}",
                "customer_type": "Business",
                "payment_terms_days": 30
            }
            
            resp = requests.post(
                f"{self.base_url}/api/v1/customers/",
                json=customer_data,
                headers=headers
            )
            
            if resp.status_code == 201:
                print(f"  ✓ Created customer {i+1}/{count}", end="\r")
            else:
                print(f"\n  ⚠ Failed to create customer {i+1}: {resp.status_code}")
        
        print(f"\n✓ Created {count} customers")
    
    def test_endpoint_performance(
        self, 
        name: str, 
        endpoint: str, 
        params: Dict = None,
        threshold_ms: int = 500
    ) -> Dict[str, Any]:
        """
        Test a single endpoint's performance
        
        Args:
            name: Test name
            endpoint: API endpoint path
            params: Query parameters
            threshold_ms: Performance threshold in milliseconds
        
        Returns:
            Test result dictionary
        """
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Warm-up request (not measured)
        requests.get(f"{self.base_url}{endpoint}", params=params, headers=headers)
        
        # Measured requests (run 5 times and take average)
        times = []
        
        for i in range(5):
            start = time.time()
            resp = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            duration = (time.time() - start) * 1000  # Convert to ms
            times.append(duration)
            
            if resp.status_code != 200:
                return {
                    "name": name,
                    "status": "FAIL",
                    "error": f"HTTP {resp.status_code}",
                    "duration_ms": 0
                }
        
        # Calculate statistics
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        status = "PASS" if avg_time < threshold_ms else "FAIL"
        
        result = {
            "name": name,
            "status": status,
            "avg_ms": round(avg_time, 2),
            "min_ms": round(min_time, 2),
            "max_ms": round(max_time, 2),
            "threshold_ms": threshold_ms,
            "all_times": [round(t, 2) for t in times]
        }
        
        self.results.append(result)
        return result
    
    def run_tests(self):
        """Run all performance tests"""
        print("\n" + "="*80)
        print("PERFORMANCE TESTS - LIST ENDPOINTS")
        print("="*80 + "\n")
        
        tests = [
            {
                "name": "List Customers (page_size=10)",
                "endpoint": "/api/v1/customers/",
                "params": {"page": 1, "page_size": 10},
                "threshold": 500
            },
            {
                "name": "List Customers (page_size=50)",
                "endpoint": "/api/v1/customers/",
                "params": {"page": 1, "page_size": 50},
                "threshold": 500
            },
            {
                "name": "List Customers (page_size=100)",
                "endpoint": "/api/v1/customers/",
                "params": {"page": 1, "page_size": 100},
                "threshold": 1000
            },
            {
                "name": "Search Customers",
                "endpoint": "/api/v1/customers/",
                "params": {"search": "Customer", "page": 1, "page_size": 50},
                "threshold": 500
            },
            {
                "name": "List Products",
                "endpoint": "/api/v1/products/",
                "params": {"page": 1, "page_size": 50},
                "threshold": 500
            },
            {
                "name": "List Invoices",
                "endpoint": "/api/v1/invoices/",
                "params": {"page": 1, "page_size": 50},
                "threshold": 500
            },
            {
                "name": "Customer Statistics",
                "endpoint": "/api/v1/customers/stats/overview",
                "params": None,
                "threshold": 500
            }
        ]
        
        for test in tests:
            print(f"Testing: {test['name']}")
            print(f"  Endpoint: {test['endpoint']}")
            print(f"  Threshold: <{test['threshold']}ms")
            print(f"  Running 5 iterations...", end=" ")
            
            result = self.test_endpoint_performance(
                name=test['name'],
                endpoint=test['endpoint'],
                params=test['params'],
                threshold_ms=test['threshold']
            )
            
            if result['status'] == "PASS":
                print(f"\n  ✓ PASS")
                print(f"  Average: {result['avg_ms']}ms")
                print(f"  Range: {result['min_ms']}ms - {result['max_ms']}ms")
            else:
                print(f"\n  ✗ FAIL")
                if 'error' in result:
                    print(f"  Error: {result['error']}")
                else:
                    print(f"  Average: {result['avg_ms']}ms (threshold: {result['threshold_ms']}ms)")
                    print(f"  Times: {result['all_times']}")
            
            print()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80 + "\n")
        
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        total = len(self.results)
        
        print(f"Total Tests: {total}")
        print(f"✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"Pass Rate: {(passed/total*100):.1f}%\n")
        
        if failed > 0:
            print("FAILED TESTS:")
            for result in self.results:
                if result['status'] == 'FAIL':
                    print(f"  ✗ {result['name']}")
                    if 'avg_ms' in result:
                        print(f"    Average: {result['avg_ms']}ms (threshold: {result['threshold_ms']}ms)")
            print()
        
        print("PERFORMANCE BREAKDOWN:")
        for result in self.results:
            if result['status'] == 'PASS':
                print(f"  ✓ {result['name']}: {result['avg_ms']}ms")
        
        print("\n" + "="*80)
        
        if failed == 0:
            print("✅ ALL PERFORMANCE TESTS PASSED!")
            print("Your API is production-ready!")
        else:
            print("⚠️  SOME PERFORMANCE TESTS FAILED")
            print("Review failed tests and optimize queries/indexes.")
        
        print("="*80 + "\n")
        
        # Save results to JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"performance_test_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": round(passed/total*100, 1)
                },
                "results": self.results
            }, f, indent=2)
        
        print(f"Detailed results saved to: {filename}")


def main():
    print("="*80)
    print("PERFORMANCE TEST SUITE")
    print("Nigerian Tax Compliance Platform - List Endpoints")
    print("="*80 + "\n")
    
    tester = PerformanceTest()
    
    # Setup
    if not tester.setup():
        print("❌ Setup failed. Exiting.")
        return 1
    
    if not tester.create_business():
        print("❌ Business setup failed. Exiting.")
        return 1
    
    # Create test data
    tester.create_test_customers(count=10)
    
    # Run performance tests
    tester.run_tests()
    
    # Print summary
    tester.print_summary()
    
    return 0 if all(r['status'] == 'PASS' for r in tester.results) else 1


if __name__ == "__main__":
    exit(main())