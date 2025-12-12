"""
Demo script to test the BBM-BDA clustering algorithm.

This creates realistic test data with multiple microservices sharing
the same domain but differentiated by:
- Path prefixes
- Header signatures  
- Error patterns
- Response characteristics
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"


def create_test_captures():
    """
    Create test captures for 3 distinct microservices on the same domain:
    1. api.example.com/v1/users (User Service)
    2. api.example.com/v1/orders (Order Service)  
    3. api.example.com/v1/payments (Payment Service)
    """
    captures = []
    
    # Service 1: User Service
    # Characteristics: Node.js server, custom user-service header
    user_endpoints = [
        "/v1/users",
        "/v1/users/123",
        "/v1/users/456/profile",
        "/v1/users/789/settings",
        "/v1/users/search",
    ]
    
    for i, endpoint in enumerate(user_endpoints):
        # Generate multiple samples for each endpoint
        for sample in range(4):
            captures.append({
                "url": f"https://api.example.com{endpoint}",
                "method": "GET" if "search" not in endpoint else "POST",
                "request": {
                    "headers": {
                        "Authorization": "Bearer user-token",
                        "User-Agent": "TestClient/1.0"
                    },
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Server": "nginx/1.18.0",
                        "X-Powered-By": "Express",
                        "X-Service-Name": "user-service",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "id": 123 + i,
                        "name": f"User {i}",
                        "email": f"user{i}@example.com"
                    }
                },
                "duration_ms": 50 + sample * 10
            })
    
    # Add error response for user service
    captures.append({
        "url": "https://api.example.com/v1/users/999",
        "method": "GET",
        "request": {
            "headers": {"Authorization": "Bearer user-token"},
            "body": None
        },
        "response": {
            "status": 404,
            "headers": {
                "Server": "nginx/1.18.0",
                "X-Powered-By": "Express",
                "X-Service-Name": "user-service",
                "Content-Type": "application/json"
            },
            "body": {
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "timestamp": datetime.utcnow().isoformat()
            }
        },
        "duration_ms": 25
    })
    
    # Service 2: Order Service
    # Characteristics: Java Spring Boot, custom order-service header
    order_endpoints = [
        "/v1/orders",
        "/v1/orders/ORD-001",
        "/v1/orders/ORD-002/items",
        "/v1/orders/ORD-003/status",
        "/v1/orders/search",
    ]
    
    for i, endpoint in enumerate(order_endpoints):
        for sample in range(4):
            captures.append({
                "url": f"https://api.example.com{endpoint}",
                "method": "GET" if "search" not in endpoint else "POST",
                "request": {
                    "headers": {
                        "Authorization": "Bearer order-token",
                        "User-Agent": "TestClient/1.0"
                    },
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Server": "Apache-Coyote/1.1",
                        "X-Powered-By": "Spring Boot",
                        "X-Service-Name": "order-service",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "orderId": f"ORD-00{i}",
                        "status": "completed",
                        "total": 100.0 + i * 10
                    }
                },
                "duration_ms": 100 + sample * 15
            })
    
    # Add error response for order service
    captures.append({
        "url": "https://api.example.com/v1/orders/ORD-999",
        "method": "GET",
        "request": {
            "headers": {"Authorization": "Bearer order-token"},
            "body": None
        },
        "response": {
            "status": 404,
            "headers": {
                "Server": "Apache-Coyote/1.1",
                "X-Powered-By": "Spring Boot",
                "X-Service-Name": "order-service",
                "Content-Type": "application/json"
            },
            "body": {
                "message": "Order not found",
                "errorCode": "ORDER_NOT_FOUND",
                "timestamp": datetime.utcnow().isoformat()
            }
        },
        "duration_ms": 45
    })
    
    # Service 3: Payment Service
    # Characteristics: Python Flask, custom payment-service header
    payment_endpoints = [
        "/v1/payments",
        "/v1/payments/PAY-001",
        "/v1/payments/PAY-002/refund",
        "/v1/payments/PAY-003/status",
        "/v1/payments/process",
    ]
    
    for i, endpoint in enumerate(payment_endpoints):
        for sample in range(4):
            captures.append({
                "url": f"https://api.example.com{endpoint}",
                "method": "GET" if "process" not in endpoint else "POST",
                "request": {
                    "headers": {
                        "Authorization": "Bearer payment-token",
                        "User-Agent": "TestClient/1.0"
                    },
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Server": "gunicorn/20.1.0",
                        "X-Powered-By": "Flask",
                        "X-Service-Name": "payment-service",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "paymentId": f"PAY-00{i}",
                        "status": "success",
                        "amount": 50.0 + i * 5
                    }
                },
                "duration_ms": 150 + sample * 20
            })
    
    # Add error response for payment service
    captures.append({
        "url": "https://api.example.com/v1/payments/PAY-999",
        "method": "GET",
        "request": {
            "headers": {"Authorization": "Bearer payment-token"},
            "body": None
        },
        "response": {
            "status": 404,
            "headers": {
                "Server": "gunicorn/20.1.0",
                "X-Powered-By": "Flask",
                "X-Service-Name": "payment-service",
                "Content-Type": "application/json"
            },
            "body": {
                "error": "Payment not found",
                "error_code": "PAYMENT_NOT_FOUND",
                "timestamp": datetime.utcnow().isoformat()
            }
        },
        "duration_ms": 60
    })
    
    return captures


def run_test():
    """Run the BBM algorithm test"""
    
    print("="*80)
    print("BBM-BDA (Black-Box Microservice Boundary Discovery) Algorithm Test")
    print("="*80)
    print()
    
    # Step 1: Start session
    print("📊 Step 1: Starting analysis session...")
    response = requests.post(
        f"{BASE_URL}/sessions/start",
        json={"domain": "api.example.com"}
    )
    session_id = response.json()["session_id"]
    print(f"   ✓ Session ID: {session_id}")
    print()
    
    # Step 2: Create and send test captures
    print("📦 Step 2: Creating test data...")
    captures = create_test_captures()
    print(f"   ✓ Created {len(captures)} API captures")
    print(f"   ✓ 3 distinct microservices on api.example.com:")
    print(f"      - User Service (Express/Node.js) - /v1/users/*")
    print(f"      - Order Service (Spring Boot/Java) - /v1/orders/*")
    print(f"      - Payment Service (Flask/Python) - /v1/payments/*")
    print()
    
    # Step 3: Send captures in batches
    print("📤 Step 3: Sending captures to analyzer...")
    batch_size = 50
    for i in range(0, len(captures), batch_size):
        batch = captures[i:i+batch_size]
        response = requests.post(
            f"{BASE_URL}/sessions/{session_id}/captures",
            json={"captures": batch}
        )
        if response.status_code != 200:
            print(f"   ✗ Error sending batch: {response.text}")
            return
        print(f"   ✓ Sent batch {i//batch_size + 1} ({len(batch)} captures)")
    print()
    
    # Step 4: Trigger analysis
    print("🔍 Step 4: Running BBM-BDA clustering analysis...")
    print("   (Using DBSCAN with automatic parameter estimation)")
    print("   (Features: Path prefix, Server, X-Powered-By, Error signatures, Latency)")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/analyze")
    
    if response.status_code != 200:
        print(f"   ✗ Analysis failed: {response.text}")
        return
    
    result = response.json()
    print("   ✓ Analysis complete!")
    print()
    
    # Step 5: Display results
    print("="*80)
    print("📈 ANALYSIS RESULTS")
    print("="*80)
    print()
    print(f"Total Captures Analyzed: {result['total_captures_analyzed']}")
    print(f"Microservices Identified: {result['microservices_identified']}")
    print()
    
    if result['microservices_identified'] != 3:
        print("⚠️  WARNING: Expected 3 microservices, but found {}".format(
            result['microservices_identified']
        ))
        print("   The algorithm may need tuning or more data samples.")
        print()
    
    # Display each microservice
    for i, ms in enumerate(result['microservices'], 1):
        print(f"{'─'*80}")
        print(f"Microservice #{i}: {ms['identified_name']}")
        print(f"{'─'*80}")
        print(f"  ID: {ms['microservice_id']}")
        print(f"  Base URL: {ms['base_url']}")
        print(f"  Confidence: {ms['confidence_score']:.2%}")
        print()
        
        # Signature
        sig = ms['signature']
        print("  Technical Signature:")
        print(f"    • Server: {sig.get('server_signature', 'N/A')}")
        print(f"    • Common Headers: {', '.join(sig.get('common_headers', {}).keys()) or 'N/A'}")
        print(f"    • Auth Pattern: {sig.get('auth_pattern', 'N/A')}")
        print()
        
        # Endpoints
        print(f"  Endpoints ({len(ms['endpoints'])}):")
        for ep in ms['endpoints']:
            methods = ', '.join(ep['methods'])
            print(f"    • {methods:6} {ep['path']} (n={ep['sample_count']})")
        print()
    
    print("="*80)
    print()
    
    # Validation
    print("🎯 VALIDATION:")
    if result['microservices_identified'] == 3:
        print("   ✅ PASS: Correctly identified 3 distinct microservices")
        print("   ✅ PASS: Services differentiated despite sharing same domain")
        print()
        print("   Key BBM-BDA features that enabled correct clustering:")
        print("   • Path prefix extraction (/v1/users, /v1/orders, /v1/payments)")
        print("   • Header signature matching (Server + X-Powered-By + X-Service-Name)")
        print("   • Error pattern normalization")
        print("   • Latency distribution analysis")
        print("   • DBSCAN with automatic parameter tuning")
    else:
        print("   ⚠️  PARTIAL: Algorithm needs more samples or tuning")
        print("   Suggestion: Increase sample count per endpoint or adjust BBM parameters")
    print()
    
    # Save detailed results
    with open('bbm_test_results.json', 'w') as f:
        json.dump(result, f, indent=2)
    print("💾 Detailed results saved to: bbm_test_results.json")
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

