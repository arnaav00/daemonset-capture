#!/usr/bin/env python3
"""Demo script to test the API Security Analyzer Service"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

def main():
    print("=" * 60)
    print("Testing API Security Analyzer Service")
    print("=" * 60)
    print()

    # 1. Start session
    print("1️⃣  Starting session...")
    response = requests.post(f"{BASE_URL}/sessions/start", json={
        "domain": "example.com",
        "metadata": {"plugin_version": "1.0.0", "test": "demo"}
    })
    session_data = response.json()
    session_id = session_data["session_id"]
    print(f"   ✅ Session created: {session_id}")
    print()

    # 2. Add user-service captures
    print("2️⃣  Adding captures for user-service...")
    user_captures = {
        "captures": [
            {
                "url": "https://api.example.com/v1/users/123",
                "method": "GET",
                "request": {
                    "headers": {"Authorization": "Bearer token123", "Content-Type": "application/json"},
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "user-service",
                        "Server": "nginx/1.21.0",
                        "X-Request-Id": "req-abc-123"
                    },
                    "body": {"id": 123, "name": "John Doe", "email": "john@example.com", "created_at": "2025-01-01"}
                },
                "timestamp": "2025-11-10T10:30:00Z",
                "duration_ms": 150
            },
            {
                "url": "https://api.example.com/v1/users/456",
                "method": "GET",
                "request": {
                    "headers": {"Authorization": "Bearer token123"},
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "user-service",
                        "Server": "nginx/1.21.0"
                    },
                    "body": {"id": 456, "name": "Jane Smith", "email": "jane@example.com"}
                },
                "timestamp": "2025-11-10T10:30:05Z",
                "duration_ms": 145
            },
            {
                "url": "https://api.example.com/v1/users",
                "method": "POST",
                "request": {
                    "headers": {"Authorization": "Bearer token123", "Content-Type": "application/json"},
                    "body": {"name": "New User", "email": "new@example.com"}
                },
                "response": {
                    "status": 201,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "user-service",
                        "Server": "nginx/1.21.0"
                    },
                    "body": {"id": 789, "name": "New User", "email": "new@example.com"}
                },
                "timestamp": "2025-11-10T10:30:10Z",
                "duration_ms": 200
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/captures", json=user_captures)
    print(f"   ✅ Added {response.json()['captures_added']} user-service captures")
    print()

    # 3. Add order-service captures
    print("3️⃣  Adding captures for order-service...")
    order_captures = {
        "captures": [
            {
                "url": "https://api.example.com/v1/orders/ord_abc123",
                "method": "GET",
                "request": {
                    "headers": {"Authorization": "Bearer token123"},
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "order-service",
                        "Server": "Express/4.18.0",
                        "X-Request-Id": "req-order-1"
                    },
                    "body": {"order_id": "ord_abc123", "total": 99.99, "status": "completed"}
                },
                "timestamp": "2025-11-10T10:30:15Z",
                "duration_ms": 180
            },
            {
                "url": "https://api.example.com/v1/orders/ord_xyz789",
                "method": "GET",
                "request": {
                    "headers": {"Authorization": "Bearer token123"},
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "order-service",
                        "Server": "Express/4.18.0"
                    },
                    "body": {"order_id": "ord_xyz789", "total": 149.99, "status": "pending"}
                },
                "timestamp": "2025-11-10T10:30:20Z",
                "duration_ms": 175
            },
            {
                "url": "https://api.example.com/v1/orders",
                "method": "POST",
                "request": {
                    "headers": {"Authorization": "Bearer token123", "Content-Type": "application/json"},
                    "body": {"items": [{"product_id": 1, "quantity": 2}]}
                },
                "response": {
                    "status": 201,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Service-Name": "order-service",
                        "Server": "Express/4.18.0"
                    },
                    "body": {"order_id": "ord_new123", "total": 199.99, "status": "pending"}
                },
                "timestamp": "2025-11-10T10:30:25Z",
                "duration_ms": 220
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/captures", json=order_captures)
    print(f"   ✅ Added {response.json()['captures_added']} order-service captures")
    print()

    # 4. Analyze
    print("4️⃣  Analyzing session...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/analyze")
    result = response.json()
    
    print()
    print("=" * 60)
    print("✨ ANALYSIS RESULTS")
    print("=" * 60)
    print()
    
    print(f"📊 Total captures analyzed: {result['total_captures_analyzed']}")
    print(f"🎯 Microservices identified: {result['microservices_identified']}")
    print()
    
    for i, service in enumerate(result['microservices'], 1):
        print("=" * 60)
        print(f"Microservice #{i}: {service['identified_name']}")
        print("=" * 60)
        print(f"  ID: {service['microservice_id']}")
        print(f"  Confidence: {service['confidence_score']:.0%}")
        print(f"  Base URL: {service['base_url']}")
        print()
        print("  Signature:")
        if service['signature'].get('auth_pattern'):
            print(f"    - Auth: {service['signature']['auth_pattern']}")
        if service['signature'].get('server_signature'):
            print(f"    - Server: {service['signature']['server_signature']}")
        if service['signature'].get('common_headers'):
            print(f"    - Common Headers: {len(service['signature']['common_headers'])} detected")
        print()
        print(f"  Endpoints ({len(service['endpoints'])}):")
        for endpoint in service['endpoints']:
            methods = ', '.join(endpoint['methods'])
            print(f"    • {methods:20} {endpoint['path']}")
            print(f"      └─ {endpoint['sample_count']} samples")
        print()
        print(f"  📄 OpenAPI Spec: {service.get('openapi_spec_url', 'N/A')}")
        print()
    
    print("=" * 60)
    print("✅ Test Complete!")
    print("=" * 60)
    print()
    print("You can now:")
    print("  • View interactive docs: http://localhost:8000/docs")
    print("  • View ReDoc: http://localhost:8000/redoc")
    print("  • Integrate your browser extension with the API")


if __name__ == "__main__":
    main()

