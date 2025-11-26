# Script to clear captured endpoints from traffic monitor
# Use this to reset the capture file

param(
    [string]$Namespace = "kube-system",
    [switch]$Confirm = $false
)

Write-Host "Clear Captured Endpoints" -ForegroundColor Cyan
Write-Host ""

# Get the traffic monitor pod
$pod = kubectl get pods -l app=traffic-monitor -n $Namespace -o jsonpath='{.items[0].metadata.name}' 2>$null

if (-not $pod) {
    Write-Host "ERROR: traffic-monitor pod not found!" -ForegroundColor Red
    exit 1
}

# Get current count
$endpointsJson = kubectl exec $pod -n $Namespace -- cat /tmp/endpoints.json 2>$null
$currentCount = 0
if ($endpointsJson -and $endpointsJson.Trim() -ne "") {
    $lines = ($endpointsJson -split "`n" | Where-Object { $_.Trim() -ne "" })
    $currentCount = $lines.Count
}

Write-Host "Current captures in file: $currentCount" -ForegroundColor Yellow
Write-Host ""

if (-not $Confirm) {
    $response = Read-Host "Are you sure you want to clear all captured endpoints? (yes/no)"
    if ($response -ne "yes") {
        Write-Host "Cancelled." -ForegroundColor Gray
        exit 0
    }
}

# Clear the file by truncating it
Write-Host "Clearing capture file..." -ForegroundColor Yellow
kubectl exec $pod -n $Namespace -- sh -c "echo '' > /tmp/endpoints.json" 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "Capture file cleared successfully!" -ForegroundColor Green
    
    # Also clear the state file if it exists
    if (Test-Path ".extract-state.json") {
        Remove-Item ".extract-state.json"
        Write-Host "Extraction state file cleared." -ForegroundColor Green
    }
} else {
    Write-Host "ERROR: Failed to clear capture file!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  - Generate new traffic: .\manual-calls.ps1" -ForegroundColor White
Write-Host "  - Or use the web UI" -ForegroundColor White
Write-Host "  - Extract endpoints: .\extract-endpoints.ps1" -ForegroundColor White

