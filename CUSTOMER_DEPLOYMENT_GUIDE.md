# APISec Kubernetes DaemonSet Traffic Monitor - Customer Deployment Guide

This guide provides comprehensive instructions for deploying and configuring the APISec Traffic Monitor DaemonSet in your Kubernetes cluster to automatically capture and push API endpoints to the APISec platform.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
4. [Deployment Steps](#deployment-steps)
5. [Configuration](#configuration)
6. [Service Mapping](#service-mapping)
7. [Verification](#verification)
8. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
9. [Updating Configuration](#updating-configuration)
10. [FAQ](#faq)

---

## Overview

The APISec Traffic Monitor is a Kubernetes DaemonSet that passively captures HTTP/HTTPS API traffic at the node level and automatically pushes discovered endpoints to the APISec platform. It provides:

- **Zero-latency monitoring**: Non-intrusive packet capture without affecting application performance
- **Automatic endpoint discovery**: Captures all API endpoints (GET, POST, PUT, DELETE, etc.)
- **Multi-service support**: Monitors multiple services simultaneously
- **Automatic push to APISec platform**: Endpoints are automatically uploaded and deduplicated

### How It Works

1. The DaemonSet runs on every node in your cluster
2. It captures HTTP/HTTPS traffic at the network layer
3. Extracts endpoint information (method, path, headers, body)
4. Maps Kubernetes services to APISec applications using your configuration
5. Pushes endpoints to the APISec platform using the Bolt API for intelligent matching and deduplication

---

## Prerequisites

Before deploying, ensure you have:

1. **Kubernetes Cluster**: Version 1.20+ (tested on Docker Desktop, minikube, and standard K8s clusters)
2. **kubectl**: Configured to access your cluster
3. **Docker**: For building container images
4. **APISec Platform Access**:
   - API Key (Bearer token) from your APISec account
   - Applications created in APISec platform with known `applicationId` and `instanceId`
5. **Service Information**: 
   - Kubernetes service names in your cluster
   - Corresponding APISec `applicationId` and `instanceId` for each service

### Getting Your APISec API Key

1. Log in to the APISec platform
2. Copy your API key/Bearer token from the Network tab (Not API Token) 

### Getting Application and Instance IDs

1. In the APISec platform, navigate to the application you want to monitor
2. Copy the `applicationId` and `instanceId` from the URL bar, which is in the format `https://apisec.ai/application/<applicationId>/instance/<instanceId>`

---


### Key Components

- **DaemonSet**: Ensures one pod runs on each node for comprehensive coverage
- **ConfigMap**: Stores API key and service mappings
- **Traffic Monitor Pod**: Captures network traffic using packet capture
- **APISec Platform**: Receives and processes endpoint data via Bolt API

---

## Deployment Steps

### Step 1: Build the Traffic Monitor Image

Build the DaemonSet container image:

```powershell
# Navigate to the daemonset directory
cd k8s_daemonset

# Build the traffic monitor image
docker build --no-cache -t traffic-monitor:latest .
```

**Note**: If you're using a private registry, tag and push the image:

```bash
docker tag traffic-monitor:latest your-registry.io/traffic-monitor:latest
docker push your-registry.io/traffic-monitor:latest
```

### Step 2: Create Applications in APISec Platform (for New Services)

If you're onboarding a new service that doesn't have an application yet in the APISec platform:

1. Log in to the APISec platform
2. Create a new application (or use an existing one)
3. Upload the `EmptySpec.yaml` file provided in the directory:
   - Click on 'Add Application' in your Applications tab
   - Upload `EmptySpec.yaml` as the OpenAPI specification with your application name
   - This creates an empty application ready to receive endpoints
4. Note the `applicationId` and `instanceId` from the URL:
   - URL format: `https://apisec.ai/application/<applicationId>/instance/<instanceId>`

**Note**: If your service already has an application in the platform, skip this step and proceed to Step 3.

### Step 3: Configure Service Mappings

Run the interactive configuration script:

**On Windows (PowerShell):**
```powershell
.\setup-config.ps1
```

**On Linux/macOS (Bash):**
```bash
chmod +x setup-config.sh
./setup-config.sh
```

Please input your:

1. **API Key**: Enter your APISec platform token
2. **Service mappings**: For each service you want to monitor:
   - Service name (as it appears in Kubernetes)
   - Application ID (from APISec platform)
   - Instance ID (from APISec platform)

**Important**: The service name must match exactly (case-sensitive) with your Kubernetes Service name. You can verify service names with:

```bash
kubectl get services --all-namespaces
```

The script generates a `configmap.yaml` file with your configuration.

### Step 4: Deploy to Kubernetes

Deploy the ConfigMap and DaemonSet:

```powershell
# Apply the ConfigMap (contains your API key and service mappings)
kubectl apply -f configmap.yaml

# Apply the DaemonSet
kubectl apply -f daemonset.yaml

# Wait for pods to be ready
kubectl get pods -n kube-system -l app=traffic-monitor -w
```

### Step 5: Verify Deployment

Check that the DaemonSet is running:

```bash
# Check DaemonSet status
kubectl get daemonset -n kube-system traffic-monitor

# Check pod status (should show one pod per node)
kubectl get pods -n kube-system -l app=traffic-monitor

# View logs to ensure it's working
kubectl logs -n kube-system -l app=traffic-monitor --tail=50
```

---

## Configuration

### ConfigMap Structure

The `configmap.yaml` contains your configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: traffic-monitor-config
  namespace: kube-system
data:
  service_config.json: |
    {
      "apiKey": "your-api-key-here",
      "autoOnboardNewServices": false,
      "apisecUrl": "https://api.apisecapps.com",
      "serviceMappings": {
        "service-name-1": {
          "appId": "application-id-1",
          "instanceId": "instance-id-1"
        },
        "service-name-2": {
          "appId": "application-id-2",
          "instanceId": "instance-id-2"
        }
      }
    }
```

---

## Verification

### Verify Traffic Capture

1. **Generate test traffic** to your services (make HTTP requests)
2. **Check DaemonSet logs**:

```powershell
kubectl logs -n kube-system -l app=traffic-monitor -f
```

Look for messages like:

```
✓ Successfully parsed HTTP REQUEST: GET /api/v1/users (service=payment-service)
✓ Done! Pushed endpoint to APISec platform: GET /api/v1/users
```

### Verify Endpoints in APISec Platform

1. Log in to the APISec platform
2. Navigate to your application
3. Check the instance - you should see endpoints appearing or being updated in real-time

### Test with Sample Request

Make a test request to one of your mapped services:

```bash
# If your service is exposed via port-forward
kubectl port-forward svc/your-service-name 8080:80

# In another terminal, make a request
curl http://localhost:8080/api/test
```

Then check the logs to see if it was captured.

---

## Monitoring and Troubleshooting

### Viewing Logs

```bash
# View all logs
kubectl logs -n kube-system -l app=traffic-monitor

# Follow logs in real-time
kubectl logs -n kube-system -l app=traffic-monitor -f

# View last 100 lines
kubectl logs -n kube-system -l app=traffic-monitor --tail=100
```

### Common Issues

#### 1. No Traffic Being Captured

**Symptoms**: Logs show no endpoint captures

**Possible Causes**:
- Services aren't making HTTP/HTTPS requests
- Services are using HTTPS with encrypted traffic (monitor only sees HTTP)
- Services are in a different namespace and not accessible
- Pod network configuration issues

**Solutions**:
- Verify services are making HTTP requests: `kubectl logs -n your-namespace <service-pod>`
- Check if traffic is HTTP (not HTTPS) - HTTPS requires additional setup
- Verify service names match exactly in ConfigMap

#### 2. Endpoints Not Pushed to Platform

**Symptoms**: Traffic captured but not appearing in APISec platform

**Possible Causes**:
- Invalid API key
- Service not mapped correctly
- Network connectivity issues to APISec platform
- Invalid applicationId or instanceId

**Solutions**:
```bash
# Check logs for errors
kubectl logs -n kube-system -l app=traffic-monitor | grep "ERROR"
```

- Verify API key is correct in ConfigMap
- Verify service mappings


#### 3. Service Not Found in Mappings

**Symptoms**: Logs show "Skipping unknown service" or "No mapping found"

**Possible Causes**:
- Service name in ConfigMap doesn't match Kubernetes service name
- Service name case mismatch
- Service mapping not applied

**Solutions**:
- Verify service name: `kubectl get services`
- Check ConfigMap: `kubectl describe configmap -n kube-system traffic-monitor-config`
- Ensure service name matches exactly (case-sensitive)

#### 4. Pod Not Starting

**Symptoms**: Pod status is `Error` or `CrashLoopBackOff`

**Possible Causes**:
- Missing or invalid ConfigMap
- Image pull errors
- Insufficient permissions

**Solutions**:
```bash
# Check pod status
kubectl describe pod -n kube-system -l app=traffic-monitor

# Check events
kubectl get events -n kube-system --sort-by='.lastTimestamp' | grep "traffic-monitor"

# Verify ConfigMap exists
kubectl get configmap -n kube-system traffic-monitor-config
```

### Health Checks

The DaemonSet performs automatic health checks. Check pod health:

```bash
# Check pod status
kubectl get pods -n kube-system -l app=traffic-monitor

# Describe pod for detailed status
kubectl describe pod -n kube-system -l app=traffic-monitor
```

---

## Updating Configuration

### Update API Key

1. Edit `configmap.yaml` and update the `apiKey` field
2. Apply changes: `kubectl apply -f configmap.yaml`
3. Restart pods: `kubectl delete pod -n kube-system -l app=traffic-monitor`

### Add/Remove Service Mappings

**Option 1: Use Setup Script (Recommended)**

**On Windows (PowerShell):**
```powershell
.\setup-config.ps1
# Add or remove services as prompted
kubectl apply -f configmap.yaml
kubectl delete pod -n kube-system -l app=traffic-monitor
```

**On Linux/macOS (Bash):**
```bash
./setup-config.sh
# Add or remove services as prompted
kubectl apply -f configmap.yaml
kubectl delete pod -n kube-system -l app=traffic-monitor
```

**Option 2: Manual Edit**

1. Edit `configmap.yaml` directly
2. Add/remove entries from `serviceMappings`
3. Apply changes: `kubectl apply -f configmap.yaml`
4. Restart pods: `kubectl delete pod -n kube-system -l app=traffic-monitor`

### Change API URL

1. Edit `configmap.yaml` and update `apisecUrl`
2. Apply changes: `kubectl apply -f configmap.yaml`
3. Restart pods: `kubectl delete pod -n kube-system -l app=traffic-monitor`


**Document Version**: 1.0  
**Last Updated**: 01/06/2026

