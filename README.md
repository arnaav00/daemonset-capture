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

### Pre-Step: Configure Service Mappings

Before deploying, configure your services using the interactive setup script:

```powershell
.\setup-config.ps1
```

This script will:
1. Ask for your API key (bearer token from the dev website)
2. Ask if you want auto-onboard enabled
   - **Yes**: Services will be automatically created on the platform when detected
   - **No**: You'll manually provide appId/instanceId mappings for each service
3. If manual mode, collect service mappings interactively:
   - Service name
   - Application ID (appId)
   - Instance ID (instanceId)
   - (Repeat for each service)

The script generates a properly formatted `configmap.yaml` file.

### 1. Build Docker Images

#### For the Traffic Monitor:

```powershell
docker build --no-cache -t traffic-monitor:latest .
```

#### For Your Services:

Build and deploy your service Docker images. For the example services provided:

```powershell
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

# Wait for ConfigMap to be ready
Start-Sleep 10

# Restart pod to pick up configuration
kubectl delete pod -n kube-system -l app=traffic-monitor

```

### 3. Generate Traffic

The traffic monitor will automatically capture traffic from all services. 

#### For Example Services:

Use the provided script to generate test traffic:

```powershell
.\manual-calls.ps1
```

This makes API calls to both `example-api` and `order-service`, and the traffic monitor captures all requests/responses.

#### For Your Services:

Make HTTP requests to your services (via `kubectl port-forward`, LoadBalancer, or Ingress). The traffic monitor will automatically capture:
- All HTTP methods (GET, POST, PUT, DELETE, etc.)
- Request/response headers
- Request/response bodies
- Status codes

### 4. View Captured Endpoints

```powershell
.\extract-endpoints.ps1
```

This extracts and filters captured endpoints from the DaemonSet, saving them to `captured-endpoints.json`.


Check the DaemonSet logs in another terminal while the DaemonSet is running:

```powershell
kubectl logs -n kube-system -l app=traffic-monitor
```

## Configuration

### ConfigMap Structure

The `configmap.yaml` contains:

```json
{
  "apiKey": "YOUR_API_KEY",
  "autoOnboardNewServices": true/false,
  "devApiUrl": "https://api.dev.apisecapps.com",
  "serviceMappings": {
    "service-name": {
      "appId": "application-id",
      "instanceId": "instance-id"
    }
  }
}
```


### Updating Configuration

1. Edit `configmap.yaml` (or run `.\setup-config.ps1` again)
2. Apply changes:
   ```powershell
   kubectl apply -f configmap.yaml
   ```
3. Restart DaemonSet pods:
   ```powershell
   kubectl delete pod -n kube-system -l app=traffic-monitor
   ```

## Troubleshooting

- **No traffic captured**: Ensure services are making HTTP requests (not HTTPS), and the DaemonSet pod is running
- **Endpoints not pushed to platform**: Check that `ENABLE_DEV_WEBSITE_INTEGRATION=true` and API key is valid

Then redeploy:
```powershell
kubectl apply -f daemonset.yaml
```

## Features

- **Endpoint Tracking**: Automatically checks if endpoints exist before creating/updating
- **Auto-Onboarding**: Creates applications and instances for new services automatically
- **De-duplication**: Prevents duplicate endpoint pushes
- **Service Mapping**: Maps Kubernetes services to APISec platform applications

