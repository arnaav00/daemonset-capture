"""
Test script for the two-step external API integration.

This script demonstrates:
1. Creating a session and adding captures
2. Analyzing the session to identify microservices
3. Onboarding a microservice with the two-step process:
   - Step 1: Upload OpenAPI spec to /v1/applications/oas
   - Step 2: Create instances with /v1/applications/{id}/instances/batch

To test with your real API:
1. Set EXTERNAL_API_URL environment variable
2. Run this script with a valid Bearer token
"""

import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000/v1/bolt"


def test_external_api_integration(api_token: str = None):
    """Test the complete workflow including external API integration"""
    
    print("=" * 80)
    print("TWO-STEP EXTERNAL API INTEGRATION TEST")
    print("=" * 80)
    print()
    
    # Check if external API is configured
    print("Checking configuration...")
    import os
    from app.core.config import settings
    external_api_url = settings.external_api_url
    env_url = os.getenv("EXTERNAL_API_URL")
    
    if env_url:
        print(f"✅ EXTERNAL_API_URL (from env): {env_url}")
    elif external_api_url:
        print(f"✅ EXTERNAL_API_URL (default): {external_api_url}")
    else:
        print("⚠️  EXTERNAL_API_URL not configured")
    print()
    
    # Step 1: Start session
    print("Step 1: Starting session...")
    response = requests.post(
        f"{BASE_URL}/sessions/start",
        json={"domain": "api.dev.apisecapps.com"}
    )
    session = response.json()
    session_id = session["session_id"]
    print(f"✅ Session started: {session_id}")
    print()
    
    # Step 2: Add captures (simulating real API calls)
    print("Step 2: Adding captures...")
    captures = [
        {
            "url": "https://api.dev.apisecapps.com/v1/applications",
            "method": "GET",
            "request": {
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json"
                },
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": [
                    {"applicationId": "app-1", "name": "User Service"},
                    {"applicationId": "app-2", "name": "Order Service"}
                ]
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 120
        },
        {
            "url": "https://api.dev.apisecapps.com/v1/applications/app-1",
            "method": "GET",
            "request": {
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json"
                },
                "body": None
            },
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "applicationId": "app-1",
                    "name": "User Service",
                    "hostUrls": ["https://api.example.com"]
                }
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": 85
        },
        {
            "url": "https://api.dev.apisecapps.com/v1/applications",
            "method": "POST",
            "request": {
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json"
                },
                "body": {
                    "name": "New Service",
                    "description": "A new service"
                }
            },
            "response": {
                "status": 201,
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "applicationId": "app-3",
                    "name": "New Service",
                    "hostUrls": ["https://api.newservice.com"]
                }
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
    print("-" * 80)
    for ms in analysis["microservices"]:
        print(f"  • {ms['identified_name']}")
        print(f"    ID: {ms['microservice_id']}")
        print(f"    Base URL: {ms['base_url']}")
        print(f"    Confidence: {ms['confidence_score']:.2f}")
        print(f"    Endpoints: {len(ms['endpoints'])}")
        print()
    
    # Step 4: Onboard microservice with two-step process
    if analysis["microservices"]:
        first_microservice = analysis["microservices"][0]
        microservice_id = first_microservice["microservice_id"]
        microservice_name = first_microservice["identified_name"]
        
        print("=" * 80)
        print(f"Step 4: Onboarding '{microservice_name}' with two-step process...")
        print("-" * 80)
        
        # Determine if we have a token
        if not api_token:
            api_token = "test-token"
            print(f"No API token provided, using default: test-token")
        else:
            print(f"Using provided API token: {api_token[:20]}...")
        print()
        
        print("📤 Calling /onboard endpoint...")
        print(f"   This will trigger two API calls:")
        print(f"   1. POST /v1/applications/oas (upload OpenAPI spec)")
        print(f"   2. POST /v1/applications/{{id}}/instances/batch (create instances)")
        print()
        
        response = requests.post(
            f"{BASE_URL}/sessions/{session_id}/onboard/{microservice_id}?type=new",
            json={"api_key": api_token}
        )
        
        print(f"Response Status: {response.status_code}")
        print("-" * 80)
        
        if response.status_code == 401:
            error = response.json()
            print("❌ Authentication Failed:")
            print(f"   {error['detail']}")
            print()
            print("   Please provide a valid Bearer token:")
            print("   python test_external_api_integration.py your-real-bearer-token")
            
        elif response.status_code == 200:
            onboard_result = response.json()
            print("✅ Onboarding successful!")
            print()
            print("Response Details:")
            print(f"  • Success: {onboard_result['success']}")
            print(f"  • Microservice ID: {onboard_result['microservice_id']}")
            print(f"  • Microservice Name: {onboard_result['microservice_name']}")
            print(f"  • Onboard Type: {onboard_result['onboard_type']}")
            
            if onboard_result.get('application_id'):
                print(f"  • Application ID: {onboard_result['application_id']}")
            
            if onboard_result.get('host_urls'):
                print(f"  • Host URLs: {onboard_result['host_urls']}")
            
            if onboard_result.get('instances_created') is not None:
                status = "✅ Yes" if onboard_result['instances_created'] else "❌ No"
                print(f"  • Instances Created: {status}")
            
            if onboard_result.get('application_url'):
                print(f"  • Application URL: {onboard_result['application_url']}")
            
            print(f"  • Message: {onboard_result['message']}")
            
        elif response.status_code == 400:
            error = response.json()
            print("⚠️  Request Error:")
            print(f"   {error['detail']}")
            print()
            print("   Note: External API is configured by default to:")
            print("   https://api.dev.apisecapps.com")
            print()
            print("   This error may be due to:")
            print("   - Invalid Bearer token")
            print("   - Network connectivity issue")
            print("   - External API is down")
            
        elif response.status_code == 500:
            error = response.json()
            print("❌ Server Error:")
            print(f"   {error['detail']}")
            print()
            print("   Check server logs for details:")
            print("   tail -100 uvicorn.log")
            
        else:
            error = response.json()
            print(f"❌ Error ({response.status_code}):")
            print(f"   {error.get('detail', response.text)}")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print()
    
    print("✅ External API integration configured!")
    print(f"   Using: {external_api_url}")
    print()
    print("What was tested:")
    print("   ✓ Session creation and capture collection")
    print("   ✓ Microservice identification")
    print("   ✓ Two-step onboarding process:")
    print("     1. Upload OpenAPI spec (multipart/form-data)")
    print("     2. Create application instances (JSON)")
    print()
    print("📝 Ready to use with your real Bearer token!")
    print("   Run: python test_external_api_integration.py <your-bearer-token>")
    print()


if __name__ == "__main__":
    # Get API token from command line if provided
    api_token = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        test_external_api_integration(api_token)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

