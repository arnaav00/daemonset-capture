# Manual API Calls Script
# This script makes direct calls to the example API endpoints
# All traffic will be passively captured by the traffic monitor DaemonSet

param(
    [string]$ApiService = "example-api",
    [string]$Namespace = "default"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Manual API Calls" -ForegroundColor Cyan
Write-Host "  All requests will be captured by DaemonSet" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the service IP
$serviceIP = kubectl get svc $ApiService -n $Namespace -o jsonpath='{.spec.clusterIP}' 2>$null
if (-not $serviceIP) {
    Write-Host "ERROR: Service $ApiService not found in namespace $Namespace" -ForegroundColor Red
    exit 1
}

Write-Host "Service IP: $serviceIP" -ForegroundColor Green
Write-Host ""

# Helper function to make API calls
function Invoke-ApiCall {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Body = $null
    )
    
    Write-Host "[$Method] $Path" -ForegroundColor Cyan
    
    $podName = "curl-manual-$(Get-Random)"
    $url = "http://$ApiService$Path"
    
    if ($Body) {
        kubectl run $podName --image=curlimages/curl --restart=Never --rm -i -- curl -s -X $Method $url -H "Content-Type: application/json" -d $Body 2>&1 | Out-Null
    } else {
        kubectl run $podName --image=curlimages/curl --restart=Never --rm -i -- curl -s -X $Method $url 2>&1 | Out-Null
    }
    
    Start-Sleep -Seconds 1
}

Write-Host "=== Making API Calls ===" -ForegroundColor Yellow
Write-Host ""

# Health check
Invoke-ApiCall -Method "GET" -Path "/"

# Users
Invoke-ApiCall -Method "GET" -Path "/api/v1/users"
Invoke-ApiCall -Method "GET" -Path "/api/v1/users/1"
Invoke-ApiCall -Method "GET" -Path "/api/v1/users/2"

# Create user
Invoke-ApiCall -Method "POST" -Path "/api/v1/users" -Body '{\"name\":\"Test User\",\"email\":\"test@example.com\"}'

# Update user
Invoke-ApiCall -Method "PUT" -Path "/api/v1/users/1" -Body '{\"name\":\"Updated Name\"}'

# Products
Invoke-ApiCall -Method "GET" -Path "/api/v1/products"
Invoke-ApiCall -Method "GET" -Path "/api/v1/products/1"

# Create product
Invoke-ApiCall -Method "POST" -Path "/api/v1/products" -Body '{\"name\":\"New Product\",\"price\":49.99,\"stock\":20}'

# Search
Invoke-ApiCall -Method "GET" -Path "/api/v1/search?q=Alice"

# Delete user
Invoke-ApiCall -Method "DELETE" -Path "/api/v1/users/3"

Write-Host ""
Write-Host "=== All API calls completed ===" -ForegroundColor Green
Write-Host ""
Write-Host "To view captured endpoints:" -ForegroundColor Yellow
Write-Host "  .\extract-endpoints.ps1" -ForegroundColor White
Write-Host ""

