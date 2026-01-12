# Inter-Service Communication Testing Guide

This guide explains how to test and verify that inter-service traffic is being captured by the traffic monitor.

## Changes Made

### 1. Added Cross-Service Endpoints

**example-api** (calls order-service):
- `GET /api/v1/orders/<order_id>` - Fetches order details from order-service
- `GET /api/v1/inventory/summary` - Fetches inventory summary from order-service

**order-service** (calls example-api):
- `GET /api/v2/orders/<order_id>/user-details` - Fetches user details from example-api
- `GET /api/v2/orders/<order_id>/product-info` - Fetches product information from example-api

### 2. Updated Dependencies

Both services now include `requests==2.31.0` in their `requirements.txt` to enable HTTP calls between services.

### 3. Enhanced Logging

Added better logging in `traffic_monitor.py` to identify inter-service traffic:
- Detects service DNS names (e.g., `order-service.default.svc.cluster.local`)
- Logs when inter-service traffic is detected
- Provides clearer service identification messages

## How Inter-Service Communication Works

In Kubernetes:
1. Services communicate using Kubernetes service DNS names
2. `example-api` calls `http://order-service/...` (resolves to ClusterIP)
3. `order-service` calls `http://example-api/...` (resolves to ClusterIP)
4. The traffic monitor captures this traffic on veth interfaces

## Testing Steps

### 1. Rebuild Services

```powershell
# Rebuild example-api with new dependencies
cd example-app
docker build -t example-api:latest .
cd ..

# Rebuild order-service with new dependencies
cd example-app-2
docker build -t order-service:latest .
cd ..
```

### 2. Redeploy Services

```powershell
# Delete and recreate deployments to pick up new images
kubectl delete deployment example-api
kubectl delete deployment order-service

# Wait a moment
Start-Sleep 5

# Deploy updated services
kubectl apply -f example-app/deployment.yaml
kubectl apply -f example-app-2/deployment.yaml

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app=example-api --timeout=60s
kubectl wait --for=condition=ready pod -l app=order-service --timeout=60s
```

### 3. Generate Inter-Service Traffic

```powershell
# Run the manual calls script (includes inter-service calls)
.\manual-calls.ps1
```

This will:
- Make direct calls to both services (normal traffic)
- Make calls that trigger inter-service communication:
  - `example-api` → `order-service`: `/api/v1/orders/1`, `/api/v1/inventory/summary`
  - `order-service` → `example-api`: `/api/v2/orders/1/user-details`, `/api/v2/orders/1/product-info`

### 4. Verify Capture

Check the traffic monitor logs:

```powershell
kubectl logs -n kube-system -l app=traffic-monitor -f
```

Look for:
- `🌐 INTER-SERVICE TRAFFIC detected` messages
- Service identification: `✓ Service identified: 'order-service'` or `✓ Service identified: 'example-api'`
- Host header logs showing service DNS names

### 5. Extract and Verify Endpoints

```powershell
.\extract-endpoints.ps1
```

Check `captured-endpoints.json` for:
- Endpoints with `service: "example-api"` and paths like `/api/v1/orders/1`
- Endpoints with `service: "order-service"` and paths like `/api/v2/orders/1/user-details`

## Expected Behavior

### Inter-Service Calls Should Be Captured

When `example-api` calls `http://order-service/api/v2/orders/1`:
1. The request is captured on veth interfaces
2. Host header shows `order-service` (or `order-service.default.svc.cluster.local`)
3. Service is identified as `order-service`
4. Endpoint is pushed to the APISec platform with `service: "order-service"`

### Service Identification

The traffic monitor identifies services using:
1. **Host Header** (primary): Extracts service name from the `Host` header
   - `order-service` → `order-service`
   - `order-service.default.svc.cluster.local` → `order-service`
2. **IP Resolution** (fallback): If Host header is missing or is an IP, queries Kubernetes API

## Troubleshooting

### Inter-Service Traffic Not Captured

1. **Check if services can communicate**:
   ```powershell
   # Test from example-api pod
   kubectl exec -it deployment/example-api -- curl -s http://order-service/
   
   # Test from order-service pod
   kubectl exec -it deployment/order-service -- curl -s http://example-api/
   ```

2. **Verify traffic monitor is capturing on correct interfaces**:
   ```powershell
   kubectl logs -n kube-system -l app=traffic-monitor | grep "candidate interfaces"
   ```
   Should see veth interfaces listed.

3. **Check for Host header in logs**:
   ```powershell
   kubectl logs -n kube-system -l app=traffic-monitor | grep "Host header"
   ```
   Should see service names in Host headers.

### Service Name Shows as "unknown"

1. **Check Host header**: The service name is extracted from the Host header. If missing, it falls back to IP resolution.

2. **Verify service DNS resolution**:
   - Services should use service DNS names (e.g., `http://order-service/`)
   - Not IP addresses or external URLs

3. **Check kubectl availability**: IP-based resolution requires `kubectl` to be available in the container (which it should be with proper RBAC).

### Endpoints Not Pushed to Platform

1. **Verify service mappings**: Check `configmap.yaml` includes both services:
   ```yaml
   serviceMappings:
     "example-api": { "appId": "...", "instanceId": "..." }
     "order-service": { "appId": "...", "instanceId": "..." }
   ```

2. **Check API key**: Ensure API key is valid in `configmap.yaml`

3. **Check logs for errors**: Look for error messages in traffic monitor logs

## Verification Checklist

- [ ] Services rebuilt with new dependencies
- [ ] Services redeployed and running
- [ ] Inter-service calls work (curl test passes)
- [ ] Traffic monitor logs show "INTER-SERVICE TRAFFIC detected"
- [ ] Service names are correctly identified (not "unknown")
- [ ] Endpoints appear in captured-endpoints.json
- [ ] Endpoints are pushed to APISec platform with correct service names

## Example Test Flow

1. **Direct call** to `example-api`: `GET /api/v1/users/1`
   - Captured with `service: "example-api"`

2. **Inter-service call** from `example-api` to `order-service`: `GET /api/v1/orders/1`
   - This triggers `example-api` to call `http://order-service/api/v2/orders/1`
   - Both requests are captured:
     - Request from client → `example-api` (service: "example-api")
     - Request from `example-api` → `order-service` (service: "order-service")

3. **Inter-service call** from `order-service` to `example-api`: `GET /api/v2/orders/1/user-details`
   - This triggers `order-service` to call `http://example-api/api/v1/search?q=...`
   - Both requests are captured:
     - Request from client → `order-service` (service: "order-service")
     - Request from `order-service` → `example-api` (service: "example-api")

