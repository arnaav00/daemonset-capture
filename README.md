# Kubernetes DaemonSet Traffic Monitor

A proof-of-concept DaemonSet that passively captures HTTP/HTTPS API endpoint traffic at the node level in Kubernetes clusters. Similar to Datadog's DaemonSet agent approach, it provides zero-latency network monitoring without modifying application code.

## What It Does

- **Passive Traffic Capture**: Monitors all HTTP/HTTPS traffic on each Kubernetes node
- **Zero Latency**: Non-intrusive packet capture without affecting application performance
- **Endpoint Discovery**: Automatically discovers and captures all API endpoints (GET, POST, PUT, DELETE, etc.)
- **Structured Output**: Exports captured endpoints to JSON format with request/response details

## Quick Start

### 1. Build Docker Images

```powershell
# Build traffic monitor
docker build -t traffic-monitor:latest .

# Build example API
cd example-app
docker build -t example-api:latest .
cd ..

# Build UI
cd ui
docker build -t api-ui:latest .
cd ..
```

### 2. Deploy to Kubernetes

```powershell
# Deploy traffic monitor DaemonSet
kubectl apply -f daemonset.yaml

# Deploy example API
kubectl apply -f example-app/deployment.yaml

# Deploy UI (optional)
kubectl apply -f ui/deployment.yaml
```

### 3. Generate Traffic

**Option A: Manual API Calls**
```powershell
.\manual-calls.ps1
```

**Option B: Web UI**
```powershell
# Get UI service URL
kubectl get svc api-ui

# Port forward to access UI
kubectl port-forward svc/api-ui 8080:80
```
Then open http://localhost:8080

### 4. Extract Captured Endpoints

```powershell
# Extract endpoints (filters health checks by default)
.\extract-endpoints.ps1

# Include health checks
.\extract-endpoints.ps1 -SkipHealthChecks:$false

# Clear captured data
.\clear-captures.ps1
```

## Output Format

Captured endpoints are saved to `captured-endpoints.json` with the following fields:
- `id` - Unique identifier
- `timestamp` - Request/response timestamp
- `status_code` - HTTP status code (responses only)
- `status_text` - HTTP status text (responses only)
- `method` - HTTP method (GET, POST, PUT, DELETE, etc.)
- `endpoint` - API endpoint path
- `full_url` - Complete request URL
- `type` - "request" or "response"
- `headers` - Request/response headers

