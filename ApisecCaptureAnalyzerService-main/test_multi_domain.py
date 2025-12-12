"""
Test BBM algorithm with microservices on DIFFERENT domains.

This verifies that the algorithm correctly separates services when they
don't share the same base domain (which should be easier than same-domain).
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"


def create_multi_domain_captures():
    """
    Create test captures for 3 microservices on DIFFERENT domains:
    1. api.users.com (User Service)
    2. api.orders.com (Order Service)  
    3. api.payments.com (Payment Service)
    """
    captures = []
    
    # Service 1: User Service on api.users.com
    for i in range(10):
        captures.append({
            "url": f"https://api.users.com/v1/users/{100+i}",
            "method": "GET",
            "request": {
                "headers": {"Authorization": "Bearer token"},
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {
                    "Server": "nginx",
                    "Content-Type": "application/json"
                },
                "body": {"id": 100+i, "name": f"User {i}"}
            },
            "duration_ms": 50
        })
    
    # Service 2: Order Service on api.orders.com (different domain!)
    for i in range(10):
        captures.append({
            "url": f"https://api.orders.com/v1/orders/ORD-{i}",
            "method": "GET",
            "request": {
                "headers": {"Authorization": "Bearer token"},
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {
                    "Server": "Apache",
                    "Content-Type": "application/json"
                },
                "body": {"orderId": f"ORD-{i}", "total": 100.0}
            },
            "duration_ms": 100
        })
    
    # Service 3: Payment Service on api.payments.com (different domain!)
    for i in range(10):
        captures.append({
            "url": f"https://api.payments.com/v1/payments/PAY-{i}",
            "method": "POST",
            "request": {
                "headers": {"Authorization": "Bearer token"},
                "body": {"amount": 50.0}
            },
            "response": {
                "status": 201,
                "headers": {
                    "Server": "gunicorn",
                    "Content-Type": "application/json"
                },
                "body": {"paymentId": f"PAY-{i}", "status": "success"}
            },
            "duration_ms": 150
        })
    
    return captures


def run_test():
    """Run multi-domain test"""
    
    print("="*80)
    print("BBM-BDA Multi-Domain Test")
    print("="*80)
    print()
    print("Testing: Microservices on DIFFERENT domains")
    print("  • api.users.com")
    print("  • api.orders.com")
    print("  • api.payments.com")
    print()
    
    # Start session
    print("📊 Starting session...")
    response = requests.post(
        f"{BASE_URL}/sessions/start",
        json={"domain": "multiple-domains"}
    )
    session_id = response.json()["session_id"]
    print(f"   ✓ Session ID: {session_id}")
    print()
    
    # Create and send captures
    print("📦 Creating 30 captures (10 per domain)...")
    captures = create_multi_domain_captures()
    
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/captures",
        json={"captures": captures}
    )
    if response.status_code != 200:
        print(f"   ✗ Error: {response.text}")
        return
    print(f"   ✓ Sent {len(captures)} captures")
    print()
    
    # Analyze
    print("🔍 Running BBM-BDA analysis...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/analyze")
    
    if response.status_code != 200:
        print(f"   ✗ Analysis failed: {response.text}")
        return
    
    result = response.json()
    print("   ✓ Analysis complete!")
    print()
    
    # Display results
    print("="*80)
    print("📈 RESULTS")
    print("="*80)
    print()
    print(f"Total Captures: {result['total_captures_analyzed']}")
    print(f"Microservices Identified: {result['microservices_identified']}")
    print()
    
    if result['microservices_identified'] != 3:
        print(f"❌ FAIL: Expected 3 microservices, found {result['microservices_identified']}")
        print()
    
    # Show each service
    domains_found = set()
    for i, ms in enumerate(result['microservices'], 1):
        print(f"{'─'*80}")
        print(f"Service #{i}: {ms['identified_name']}")
        print(f"{'─'*80}")
        print(f"  Base URL: {ms['base_url']}")
        print(f"  Confidence: {ms['confidence_score']:.2%}")
        print(f"  Endpoints: {len(ms['endpoints'])}")
        print()
        
        # Extract domain from base_url
        if 'api.users.com' in ms['base_url']:
            domains_found.add('api.users.com')
        elif 'api.orders.com' in ms['base_url']:
            domains_found.add('api.orders.com')
        elif 'api.payments.com' in ms['base_url']:
            domains_found.add('api.payments.com')
    
    print("="*80)
    print()
    
    # Validation
    print("🎯 VALIDATION:")
    all_domains_found = len(domains_found) == 3
    correct_count = result['microservices_identified'] == 3
    
    if all_domains_found and correct_count:
        print("   ✅ PASS: All 3 domains correctly identified as separate services")
        print("   ✅ PASS: Different domains properly differentiated")
        print()
        print("   Found domains:")
        for domain in sorted(domains_found):
            print(f"      • {domain}")
    else:
        print("   ❌ FAIL: Domain differentiation not working correctly")
        print(f"      Expected 3 services, found {result['microservices_identified']}")
        print(f"      Expected 3 domains, found {len(domains_found)}")
    print()
    
    # Save results
    with open('multi_domain_test_results.json', 'w') as f:
        json.dump(result, f, indent=2)
    print("💾 Results saved to: multi_domain_test_results.json")
    print()


if __name__ == "__main__":
    try:
        run_test()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to API service at http://localhost:8000")
        print("   Make sure the service is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

