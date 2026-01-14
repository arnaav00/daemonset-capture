# Kubernetes DaemonSet Traffic Monitor

A DaemonSet that passively captures HTTP/HTTPS API endpoint traffic at the node level in Kubernetes clusters and automatically pushes endpoints to the APISec platform. Provides zero-latency network monitoring without modifying application code.

## What It Does

- **Passive Traffic Capture**: Monitors all HTTP/HTTPS traffic on each Kubernetes node
- **Zero Latency**: Non-intrusive packet capture without affecting application performance
- **Endpoint Discovery**: Automatically discovers and captures all API endpoints (GET, POST, PUT, DELETE, etc.)
- **Multi-Service Support**: Captures traffic from multiple services simultaneously and identifies the source service
- **Automatic Push to APISec Platform**: Pushes captured endpoints directly 
- **Server-Side Deduplication**: Uses APISec Bolt API for matching and deduplication


## Quick Start

### Pre-Step 1: Create Applications in APISec Platform (for New Services)

If you're onboarding a new service that doesn't have an application yet in the APISec platform:

1. Log in to the APISec platform
2. Create a new application (or use an existing one)
3. Upload the `EmptySpec.yaml` file provided in this repository:
   - Navigate to your application in the platform
   - Upload `EmptySpec.yaml` as the OpenAPI specification
   - This creates an empty application ready to receive endpoints
4. Note the `applicationId` and `instanceId` from the URL:
   - URL format: `https://apisec.ai/application/<applicationId>/instance/<instanceId>`

**Note**: If your services already have applications in the platform, skip this step.

### Pre-Step 2: Configure Service Mappings

Before deploying, configure your services using the interactive setup script:

**On Windows (PowerShell):**
```powershell
.\setup-config.ps1
```

**On Linux/macOS (Bash):**
```bash
chmod +x setup-config.sh
./setup-config.sh
```

This script will:
1. Ask for your API key (bearer token from the APISec platform)
2. Collect service mappings interactively for each service:
   - Service name (must match Kubernetes service name)
   - Application ID (appId) from APISec platform
   - Instance ID (instanceId) from APISec platform
   - (Repeat for each service you want to monitor)

The script generates a properly formatted `configmap.yaml` file.

**Note**: Auto-onboarding is disabled. You must manually map each Kubernetes service to its corresponding APISec application/instance.

### 1. Build Docker Images

#### For the Traffic Monitor:

**On Windows (PowerShell):**
```powershell
docker build --no-cache -t traffic-monitor:latest .
```

**On Linux/macOS (Bash):**
```bash
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

**Deploy the example services to Kubernetes:**

```bash
# Deploy example-api
kubectl apply -f example-app/deployment.yaml

# Deploy order-service
kubectl apply -f example-app-2/deployment.yaml

# Verify they're running
kubectl get deployments
kubectl get services
```

### 2. Deploy to Kubernetes

```bash
# Deploy traffic monitor DaemonSet
kubectl apply -f daemonset.yaml
kubectl apply -f configmap.yaml

# Wait for ConfigMap to be ready
sleep 10

# Restart pod to pick up configuration
kubectl delete pod -n kube-system -l app=traffic-monitor
```

**Note**: The DaemonSet runs in the `kube-system` namespace. In Docker Desktop, switch to the `kube-system` namespace to view the pods.

### 3. Generate Traffic

The traffic monitor will automatically capture traffic from all services configured in the service mappings.

#### For Example Services:

Use the provided script to generate test traffic:

```powershell
.\manual-calls.ps1
```

This makes API calls to both `example-api` and `order-service`, and the traffic monitor captures all requests/responses.

#### For Your Services:

Make HTTP requests to your services (via `kubectl port-forward`, LoadBalancer, or Ingress). The traffic monitor will automatically capture:
- All HTTP methods (GET, POST, PUT, DELETE, PATCH, etc.)
- Request/response headers
- Request/response bodies
- Status codes

### 4. View Captured Endpoints

Check the DaemonSet logs to see endpoint capture and push status:

```powershell
kubectl logs -n kube-system -l app=traffic-monitor -f
```

You should see logs indicating:
- Endpoint captures
- Bolt Preview API calls
- Endpoint matches/creates
- Path parameterization for new endpoints

Extract captured endpoints to a file:

```powershell
.\extract-endpoints.ps1
```

This extracts and filters captured endpoints from the DaemonSet, saving them to `captured-endpoints.json`.

### 5. Verify on APISec Platform

1. Log in to the APISec platform
2. Navigate to your applications
3. Check that endpoints are appearing:
   - Existing endpoints will be updated with new parameters/headers
   - New endpoints will be created with parameterized paths (e.g., `/api/v1/users/{id}`)

## Configuration

### ConfigMap Structure

The `configmap.yaml` contains:

```json
{
  "apiKey": "YOUR_API_KEY",
  "autoOnboardNewServices": false,
  "apisecUrl": "https://api.apisecapps.com",
  "serviceMappings": {
    "service-name": {
      "appId": "application-id",
      "instanceId": "instance-id"
    }
  }
}
```


### Updating Configuration

1. Edit `configmap.yaml` (or run the setup script again):
   - **Windows**: `.\setup-config.ps1`
   - **Linux/macOS**: `./setup-config.sh`
2. Apply changes:
   ```bash
   kubectl apply -f configmap.yaml
   ```
3. Restart DaemonSet pods:
   ```bash
   kubectl delete pod -n kube-system -l app=traffic-monitor
   ```

## Troubleshooting

### No traffic captured
- Ensure services are making HTTP requests (HTTPS is captured but may need TLS inspection)
- Verify the DaemonSet pod is running: `kubectl get pods -n kube-system -l app=traffic-monitor`
- Check logs: `kubectl logs -n kube-system -l app=traffic-monitor`

### Endpoints not pushed to platform
- Verify `ENABLE_APISEC_INTEGRATION=true` in `daemonset.yaml` (already set)
- Check that API key is valid and not expired
- Ensure service mappings are correct (service name matches Kubernetes service name)
- Check logs for error messages: `kubectl logs -n kube-system -l app=traffic-monitor`

### Service not found in mappings
- Verify the service name in `configmap.yaml` exactly matches the Kubernetes service name
- Ensure the service is making HTTP traffic that can be captured
- Check logs for "service not found" or "no mapping" messages

### Endpoints showing as raw paths instead of parameterized
- This is expected for new endpoints: they are parameterized when created
- Bolt Preview matches concrete paths (e.g., `/api/v1/users/1`) against parameterized templates (e.g., `/api/v1/users/{id}`)
- If you see raw paths on the platform, they are likely new endpoints that haven't been parameterized yet

### Rebuilding after code changes

If you modify the Python code, rebuild the image:

```powershell
docker build --no-cache -t traffic-monitor:latest .
kubectl apply -f daemonset.yaml
kubectl delete pod -n kube-system -l app=traffic-monitor
```

