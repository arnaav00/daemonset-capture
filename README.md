# Kubernetes DaemonSet Traffic Monitor

A DaemonSet that passively captures HTTP/HTTPS API endpoint traffic at the node level in Kubernetes clusters and automatically pushes endpoints to the APISec platform. Provides zero-latency network monitoring without modifying application code.

## What It Does

- **Passive Traffic Capture**: Monitors all HTTP/HTTPS traffic on each Kubernetes node
- **Zero Latency**: Non-intrusive packet capture without affecting application performance
- **Endpoint Discovery**: Automatically discovers and captures all API endpoints (GET, POST, PUT, DELETE, etc.)
- **Multi-Service Support**: Captures traffic from multiple services simultaneously and identifies the source service
- **Automatic Push to APISec Platform**: Pushes captured endpoints directly to the dev website
- **Auto-Onboarding**: Automatically creates applications for new services (optional)
- **Smart Endpoint Management**: Checks if endpoints exist and updates or creates accordingly

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
kubectl apply -f configmap.yaml

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

### 4. Configure Service Mappings

Edit `configmap.yaml` to map your services to APISec platform applications:

```yaml
data:
  service_config.json: |
    {
      "apiKey": "YOUR_API_KEY_HERE",
      "autoOnboardNewServices": false,
      "devApiUrl": "https://api.dev.apisecapps.com",
      "serviceMappings": {
        "example-api": {
          "appId": "your-application-id",
          "instanceId": "your-instance-id"
        },
        "order-service": {
          "appId": "your-application-id",
          "instanceId": "your-instance-id"
        }
      }
    }
```

**Important**:
- Set `apiKey` (top-level, shared across all services)
- For each service, provide `appId` and `instanceId` from the APISec platform
- Set `autoOnboardNewServices: true` to automatically create applications for unmapped services

### 5. Deploy Configuration

```powershell
kubectl apply -f configmap.yaml
kubectl delete pod -n kube-system -l app=traffic-monitor  # Restart to pick up config
```

### 6. Enable Integration

Edit `daemonset.yaml` and set:
```yaml
- name: ENABLE_DEV_WEBSITE_INTEGRATION
  value: "true"
```

Then redeploy:
```powershell
kubectl apply -f daemonset.yaml
```

## Features

- **Endpoint Tracking**: Automatically checks if endpoints exist before creating/updating
- **Auto-Onboarding**: Creates applications and instances for new services automatically
- **De-duplication**: Prevents duplicate endpoint pushes
- **Service Mapping**: Maps Kubernetes services to APISec platform applications

