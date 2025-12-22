# Rebuild script that forces Docker to use latest code
Write-Host "Rebuilding traffic-monitor image..." -ForegroundColor Cyan

# Step 1: Build with no cache (explicitly enable BuildKit)
Write-Host "Step 1: Building image with --no-cache..." -ForegroundColor Yellow
$env:DOCKER_BUILDKIT = "1"
docker build --no-cache -t traffic-monitor:latest .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Build successful!" -ForegroundColor Green

# Step 2: Apply DaemonSet and ConfigMap
Write-Host "Step 2: Applying DaemonSet and ConfigMap..." -ForegroundColor Yellow
kubectl apply -f daemonset.yaml
kubectl apply -f configmap.yaml
Start-Sleep 10

# Step 3: Restart pod
Write-Host "Step 3: Restarting pod..." -ForegroundColor Yellow
kubectl delete pod -n kube-system -l app=traffic-monitor

Write-Host ""
Write-Host "Rebuild complete! Wait a few seconds for pod to start, then check logs:" -ForegroundColor Green
Write-Host "  kubectl logs -n kube-system -l app=traffic-monitor --tail=50" -ForegroundColor White
