"""
Track a specific endpoint through the entire pipeline to see where it gets filtered
"""
import sys
sys.path.insert(0, '/Users/mohsinniyazi/prototype/apiseccaptureanalyzerservice')

# Read the logs and track the endpoint
endpoint_to_track = "/v1/hostedagents"

print("="*80)
print(f"TRACKING ENDPOINT: {endpoint_to_track}")
print("="*80)
print()

# Parse the uvicorn log
with open('uvicorn.log', 'r') as f:
    log_content = f.read()

# Find the most recent session
import re
session_matches = re.findall(r'POST /api/v1/sessions/([a-f0-9-]+)/captures', log_content)
if session_matches:
    session_id = session_matches[-1]
    print(f"📊 Session ID: {session_id}")
    print()
else:
    print("❌ No session found in logs")
    sys.exit(1)

# Check if endpoint appears in logs
if endpoint_to_track in log_content:
    print(f"✅ Endpoint '{endpoint_to_track}' WAS captured by browser extension")
    print()
    
    # Count occurrences
    count = log_content.count(endpoint_to_track)
    print(f"   Appeared {count} time(s) in logs")
    print()
else:
    print(f"❌ Endpoint '{endpoint_to_track}' NOT found in logs")
    print("   It was never sent to the service by the browser extension")
    sys.exit(1)

# Now check the in-memory session data
from app.services.session_manager import get_session_manager

manager = get_session_manager()
sessions = manager.store.sessions if hasattr(manager.store, 'sessions') else {}

if session_id not in sessions:
    print(f"⚠️  Session {session_id} not found in memory (may have expired)")
    print()
    print("However, we can check the logs for what happened...")
    print()
else:
    session = sessions[session_id]
    
    # Check if endpoint is in captures
    matching_captures = [c for c in session.captures if endpoint_to_track in c.url]
    
    if matching_captures:
        print(f"✅ Found {len(matching_captures)} capture(s) with this endpoint in session")
        for cap in matching_captures:
            print(f"   • {cap.method} {cap.url}")
        print()
    else:
        print(f"❌ Endpoint NOT in session captures")
        print(f"   Total captures in session: {len(session.captures)}")
        print()

# Check analysis results from logs
print("="*80)
print("ANALYSIS PIPELINE CHECK")
print("="*80)
print()

# Get the analysis section from logs
analyze_sections = log_content.split('[FeatureExtractor] Processing')
if len(analyze_sections) > 1:
    latest_analysis = analyze_sections[-1]
    
    # Check each stage
    print("Stage 1: Feature Extraction")
    if endpoint_to_track in latest_analysis:
        print(f"   ✅ Endpoint present during feature extraction")
    else:
        print(f"   ❌ Endpoint NOT present during feature extraction")
        print(f"   → Endpoint was filtered BEFORE feature extraction")
    print()
    
    print("Stage 2: Clustering")
    # Check cluster assignments
    cluster_sections = latest_analysis.split('[MicroserviceIdentifier] Cluster')
    
    found_in_cluster = False
    for i, section in enumerate(cluster_sections[1:], 1):
        if endpoint_to_track in section:
            print(f"   ✅ Endpoint found in Cluster {i}")
            found_in_cluster = True
            break
    
    if not found_in_cluster:
        print(f"   ❌ Endpoint NOT in any cluster")
        print(f"   → Likely marked as NOISE by DBSCAN or filtered by validation")
    print()
    
    print("Stage 3: Endpoint Identification")
    # Check final endpoints
    final_endpoints_section = latest_analysis.split('[MicroserviceIdentifier]   • ')
    
    found_in_final = False
    for line in final_endpoints_section[1:]:
        if endpoint_to_track in line:
            print(f"   ✅ Endpoint in final results: {line.split(chr(10))[0]}")
            found_in_final = True
            break
    
    if not found_in_final:
        print(f"   ❌ Endpoint NOT in final results")
    print()

# Summary
print("="*80)
print("DIAGNOSIS")
print("="*80)
print()

# Determine where it was lost
if endpoint_to_track not in log_content:
    print("🔍 ROOT CAUSE: Endpoint was never captured by browser extension")
    print()
    print("Possible reasons:")
    print("  • Browser extension filtering it out")
    print("  • Request was made before extension started capturing")
    print("  • Extension not configured to capture this domain/path")
elif endpoint_to_track not in latest_analysis:
    print("🔍 ROOT CAUSE: Endpoint filtered BEFORE feature extraction")
    print()
    print("Possible reasons:")
    print("  • Session manager rejected it")
    print("  • Capture validation failed")
    print("  • Data format issue")
elif not found_in_cluster:
    print("🔍 ROOT CAUSE: DBSCAN marked endpoint as NOISE")
    print()
    print("Possible reasons:")
    print("  • Endpoint doesn't have enough similar neighbors (min_samples threshold)")
    print("  • Endpoint features too different from any cluster (eps threshold)")
    print("  • Only 1 occurrence of this endpoint (DBSCAN needs ≥2 for cluster)")
    print()
    print("RECOMMENDATION:")
    print("  • Lower min_samples in DBSCAN")
    print("  • Increase eps (distance threshold)")
    print("  • Create a fallback cluster for noise points")
elif not found_in_final:
    print("🔍 ROOT CAUSE: Filtered during endpoint grouping")
    print()
    print("Possible reasons:")
    print("  • Merged with another endpoint during parameterization")
    print("  • Cluster validation filtered it out")
    print("  • Sample count too low")
else:
    print("✅ Endpoint is in the final results!")
    print()
    print("If you're not seeing it, check the API response.")

print()

