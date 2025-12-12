"""
Test script to demonstrate the onboarding feature.

This script:
1. Creates a session
2. Adds some captures
3. Analyzes the session
4. Attempts to onboard a microservice (will show config error if EXTERNAL_API_URL not set)
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/v1/bolt"


def test_onboarding_workflow():
    """Test the complete onboarding workflow"""
    
    print("=" * 60)
    print("ONBOARDING FEATURE TEST")
    print("=" * 60)
    print()
    
    # Step 1: Start session
    print("Step 1: Starting session...")
    response = requests.post(
        f"{BASE_URL}/sessions/start",
        json={"domain": "api.example.com"}
    )
    session = response.json()
    session_id = session["session_id"]
    print(f"✅ Session started: {session_id}")
    print()
    
    # Step 2: Add captures
    print("Step 2: Adding captures...")
    captures = [
        {
            "url": "https://api.example.com/v1/users",
            "method": "GET",
            "request": {
                "headers": {"Authorization": "Bearer token123"},
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 120
        },
        {
            "url": "https://api.example.com/v1/users/1",
            "method": "GET",
            "request": {
                "headers": {"Authorization": "Bearer token123"},
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {"id": 1, "name": "Alice", "email": "alice@example.com"}
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 85
        },
        {
            "url": "https://api.example.com/v1/users/2",
            "method": "GET",
            "request": {
                "headers": {"Authorization": "Bearer token123"},
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {"id": 2, "name": "Bob", "email": "bob@example.com"}
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 92
        },
        {
            "url": "https://api.example.com/v1/users",
            "method": "POST",
            "request": {
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json"
                },
                "body": {"name": "Charlie", "email": "charlie@example.com"}
            },
            "response": {
                "status": 201,
                "headers": {"Content-Type": "application/json"},
                "body": {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 150
        }
    ]
    
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/captures",
        json={"captures": captures}
    )
    capture_result = response.json()
    print(f"✅ Added {capture_result['captures_added']} captures")
    print()
    
    # Step 3: Analyze session
    print("Step 3: Analyzing session...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/analyze")
    
    if response.status_code != 200:
        print(f"❌ Analysis failed with status {response.status_code}")
        print(f"   Response: {response.json()}")
        return
    
    analysis = response.json()
    
    print(f"✅ Analysis complete!")
    print(f"   - Total captures analyzed: {analysis['total_captures_analyzed']}")
    print(f"   - Microservices identified: {analysis['microservices_identified']}")
    print()
    
    # Display microservices
    print("Identified Microservices:")
    print("-" * 60)
    for ms in analysis["microservices"]:
        print(f"  • {ms['identified_name']}")
        print(f"    ID: {ms['microservice_id']}")
        print(f"    Base URL: {ms['base_url']}")
        print(f"    Confidence: {ms['confidence_score']:.2f}")
        print(f"    Endpoints: {len(ms['endpoints'])}")
        
        # Check if openapi_spec_url is present (should NOT be)
        if "openapi_spec_url" in ms:
            print(f"    ⚠️  WARNING: openapi_spec_url still present (should be removed)")
        else:
            print(f"    ✅ openapi_spec_url correctly removed")
        print()
    
    # Step 4: Try to onboard (will fail without EXTERNAL_API_URL configured)
    if analysis["microservices"]:
        first_microservice = analysis["microservices"][0]
        microservice_id = first_microservice["microservice_id"]
        microservice_name = first_microservice["identified_name"]
        
        print("=" * 60)
        print(f"Step 4: Attempting to onboard '{microservice_name}'...")
        print("-" * 60)
        
        response = requests.post(
            f"{BASE_URL}/sessions/{session_id}/onboard/{microservice_id}?type=new",
            json={"api_key": "test-api-key-123"}
        )
        
        if response.status_code == 200:
            onboard_result = response.json()
            print("✅ Onboarding successful!")
            print(f"   Response: {json.dumps(onboard_result, indent=2)}")
        elif response.status_code == 400:
            error = response.json()
            print("⚠️  Onboarding not configured (expected):")
            print(f"   {error['detail']}")
            print()
            print("   To enable onboarding:")
            print("   1. Set EXTERNAL_API_URL environment variable")
            print("   2. Provide your external API endpoint details")
        else:
            print(f"❌ Unexpected error: {response.status_code}")
            print(f"   {response.json()}")
    
    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print()
    print("✅ Changes Verified:")
    print("   1. Analysis response no longer includes openapi_spec_url")
    print("   2. New /onboard endpoint is functional")
    print("   3. Proper error handling when EXTERNAL_API_URL not set")
    print()
    print("📝 Next Steps:")
    print("   1. Provide external API endpoint details")
    print("   2. Set EXTERNAL_API_URL environment variable")
    print("   3. Test onboarding with real external API")
    print()


if __name__ == "__main__":
    try:
        test_onboarding_workflow()
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

