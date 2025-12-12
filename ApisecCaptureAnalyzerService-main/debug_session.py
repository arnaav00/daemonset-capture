"""
Debug script to analyze the most recent session data
"""
import sys
sys.path.insert(0, '/Users/mohsinniyazi/prototype/apiseccaptureanalyzerservice')

from app.services.session_manager import get_session_manager
from collections import Counter, defaultdict
import json

print("="*80)
print("SESSION DEBUG ANALYZER")
print("="*80)
print()

manager = get_session_manager()

# Get all sessions from the store
try:
    # Access the underlying store
    sessions = manager.store.sessions if hasattr(manager.store, 'sessions') else {}
    
    if not sessions:
        print("❌ No sessions found in memory")
        print("   The session may have expired or been cleared.")
        print("   Try running your browser extension again.")
        sys.exit(1)

    # Get most recent session
    session_id = list(sessions.keys())[-1]
    session = sessions[session_id]
except Exception as e:
    print(f"❌ Could not access sessions: {e}")
    sys.exit(1)

print(f"📊 Session ID: {session_id}")
print(f"   Status: {session.status}")
print(f"   Domain: {session.domain}")
print(f"   Total Captures: {len(session.captures)}")
print()

if not session.captures:
    print("❌ No captures in session")
    sys.exit(1)

# Analyze captures
print("="*80)
print("CAPTURE ANALYSIS")
print("="*80)
print()

# 1. Group by domain
print("🌐 Domains:")
domains = Counter()
for capture in session.captures:
    if '://' in capture.url:
        domain = capture.url.split('/')[2]
        domains[domain] += 1
    
for domain, count in domains.most_common():
    print(f"   • {domain}: {count} captures")
print()

# 2. Group by method
print("📡 HTTP Methods:")
methods = Counter(c.method for c in session.captures)
for method, count in methods.most_common():
    print(f"   • {method}: {count} captures")
print()

# 3. Analyze endpoints
print("🎯 Endpoints (first 30):")
endpoints = []
for capture in session.captures:
    if '://' in capture.url:
        parts = capture.url.split('/', 3)
        path = '/' + parts[3] if len(parts) > 3 else '/'
    else:
        path = capture.url
    
    endpoints.append({
        'method': capture.method,
        'path': path,
        'domain': capture.url.split('/')[2] if '://' in capture.url else 'unknown',
        'status': capture.response.status
    })

# Group endpoints
endpoint_groups = defaultdict(list)
for ep in endpoints:
    key = f"{ep['domain']} {ep['method']} {ep['path']}"
    endpoint_groups[key].append(ep)

sorted_endpoints = sorted(endpoint_groups.items(), key=lambda x: len(x[1]), reverse=True)

for i, (key, captures_list) in enumerate(sorted_endpoints[:30]):
    print(f"   {i+1:2}. {key} (n={len(captures_list)})")

if len(sorted_endpoints) > 30:
    print(f"   ... and {len(sorted_endpoints) - 30} more unique endpoints")
print()

print(f"📊 Total unique endpoints: {len(endpoint_groups)}")
print()

# 4. Check for status codes
print("📈 Status Codes:")
status_codes = Counter(c.response.status for c in session.captures)
for code, count in sorted(status_codes.items()):
    print(f"   • {code}: {count} captures")
print()

# 5. Check if analysis has been done
if hasattr(session, 'analysis_result') and session.analysis_result:
    print("="*80)
    print("ANALYSIS RESULTS")
    print("="*80)
    print()
    
    result = session.analysis_result
    print(f"✅ Analysis completed")
    print(f"   Microservices identified: {len(result.get('microservices', []))}")
    print()
    
    for i, ms in enumerate(result.get('microservices', []), 1):
        print(f"   Service #{i}: {ms.get('identified_name', 'unknown')}")
        print(f"      Base URL: {ms.get('base_url', 'unknown')}")
        print(f"      Confidence: {ms.get('confidence_score', 0):.2%}")
        print(f"      Endpoints: {len(ms.get('endpoints', []))}")
        
        # Show first few endpoints
        for j, ep in enumerate(ms.get('endpoints', [])[:5], 1):
            methods = ', '.join(ep.get('methods', []))
            print(f"         {j}. {methods:6} {ep.get('path', 'unknown')} (n={ep.get('sample_count', 0)})")
        
        if len(ms.get('endpoints', [])) > 5:
            print(f"         ... and {len(ms.get('endpoints', [])) - 5} more")
        print()
    
    # Compare: What was captured vs what was identified
    print("🔍 COMPARISON:")
    print(f"   Captured unique endpoints: {len(endpoint_groups)}")
    
    total_identified = sum(len(ms.get('endpoints', [])) for ms in result.get('microservices', []))
    print(f"   Identified endpoints: {total_identified}")
    
    if len(endpoint_groups) > total_identified:
        missing = len(endpoint_groups) - total_identified
        print(f"   ⚠️  Missing: {missing} endpoints")
        print()
        print("   Possible reasons:")
        print("   • Endpoint parameterization merged similar URLs")
        print("   • Low sample count (endpoints with <2 samples filtered)")
        print("   • Clustering grouped similar endpoints together")
    elif len(endpoint_groups) < total_identified:
        print(f"   ℹ️  Note: Some captured URLs were parameterized")
        print(f"      (e.g., /users/123, /users/456 → /users/{{id}})")
    else:
        print("   ✅ All endpoints accounted for")
    print()
else:
    print("⚠️  Analysis not yet performed or results not cached")
    print()

# Save detailed report
report = {
    'session_id': session_id,
    'total_captures': len(session.captures),
    'unique_endpoints': len(endpoint_groups),
    'domains': dict(domains),
    'methods': dict(methods),
    'status_codes': dict(status_codes),
    'endpoints': [
        {
            'endpoint': key,
            'sample_count': len(captures_list)
        }
        for key, captures_list in sorted_endpoints
    ]
}

with open('session_debug_report.json', 'w') as f:
    json.dump(report, f, indent=2)

print("💾 Detailed report saved to: session_debug_report.json")
print()

