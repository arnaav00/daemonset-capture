# Kubernetes DaemonSet Traffic Monitor

A proof-of-concept DaemonSet that passively captures HTTP/HTTPS API endpoint traffic at the node level in Kubernetes clusters. Similar to Datadog's DaemonSet agent approach, it provides zero-latency network monitoring without modifying application code.

## What It Does

- **Passive Traffic Capture**: Monitors all HTTP/HTTPS traffic on each Kubernetes node
- **Zero Latency**: Non-intrusive packet capture without affecting application performance
- **Endpoint Discovery**: Automatically discovers and captures all API endpoints (GET, POST, PUT, DELETE, etc.)
- **Multi-Service Support**: Captures traffic from multiple services simultaneously and identifies the source service
- **Structured Output**: Exports captured endpoints to JSON format with request/response details and service identification

## Quick Start

### 1. Build Docker Images

```powershell
# Build traffic monitor
docker build -t traffic-monitor:latest .

# Build example API (Service 1)
cd example-app
docker build -t example-api:latest .
cd ..

# Build order service (Service 2)
cd example-app-2
docker build -t order-service:latest .
cd ..
```

### 2. Deploy to Kubernetes

```powershell
# Deploy traffic monitor DaemonSet
kubectl apply -f daemonset.yaml

# Deploy example API (Service 1)
kubectl apply -f example-app/deployment.yaml

# Deploy order service (Service 2)
kubectl apply -f example-app-2/deployment.yaml
```

### 3. Generate Traffic

The traffic monitor will automatically capture traffic from all services. Use the manual calls script to generate traffic for both services:

```powershell
.\manual-calls.ps1
```

This will make API calls to both `example-api` and `order-service`, and the traffic monitor will capture all requests/responses with service identification.

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
- `service` - Service identifier (e.g., "example-api", "order-service")
- `method` - HTTP method (GET, POST, PUT, DELETE, etc.)
- `endpoint` - API endpoint path
- `full_url` - Complete request URL
- `type` - "request" or "response"
- `headers` - Request/response headers

The `service` field allows you to identify which service each endpoint belongs to, making it easy to filter and analyze traffic by service.

