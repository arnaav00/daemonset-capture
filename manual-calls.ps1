# Manual API Calls Script
# This script makes direct calls to both example API services
# All traffic will be passively captured by the traffic monitor DaemonSet

param(
    [string]$Namespace = "default"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Manual API Calls" -ForegroundColor Cyan
Write-Host "  All requests will be captured by DaemonSet" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Helper function to make API calls
function Invoke-ApiCall {
    param(
        [string]$Service,
        [string]$Method,
        [string]$Path,
        [string]$Body = $null
    )
    
    Write-Host "[$Service] [$Method] $Path" -ForegroundColor Cyan
    
    $podName = "curl-manual-$(Get-Random)"
    $url = "http://$Service$Path"
    
    # Explicitly set Host header to service name so traffic monitor can identify the service
    if ($Body) {
        # Use single quotes around $Body to prevent PowerShell from splitting on spaces
        kubectl run $podName --image=curlimages/curl --restart=Never --rm -i -- sh -c "curl -s -X $Method '$url' -H 'Host: $Service' -H 'Content-Type: application/json' -d '$Body'" 2>&1 | Out-Null
    } else {
        kubectl run $podName --image=curlimages/curl --restart=Never --rm -i -- curl -s -X $Method $url -H "Host: $Service" 2>&1 | Out-Null
    }
    
    Start-Sleep -Seconds 1
}

Write-Host "=== Making API Calls to example-api ===" -ForegroundColor Yellow
Write-Host ""

# Health check
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/"

# Users
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/users"
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/users/1"
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/users/2"

# Create user
Invoke-ApiCall -Service "example-api" -Method "POST" -Path "/api/v1/users" -Body '{\"name\":\"Test User\",\"email\":\"test@example.com\"}'

# Update user
Invoke-ApiCall -Service "example-api" -Method "PUT" -Path "/api/v1/users/1" -Body '{\"name\":\"Updated Name\"}'

# Products
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/products"
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/products/1"

# Create product
Invoke-ApiCall -Service "example-api" -Method "POST" -Path "/api/v1/products" -Body '{\"name\":\"New Product\",\"price\":49.99,\"stock\":20}'

# Search
Invoke-ApiCall -Service "example-api" -Method "GET" -Path "/api/v1/search?q=Alice"

# Delete user
Invoke-ApiCall -Service "example-api" -Method "DELETE" -Path "/api/v1/users/3"

Write-Host ""
Write-Host "=== Making API Calls to order-service ===" -ForegroundColor Yellow
Write-Host ""

# Health check
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/"

# Orders
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/orders"
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/orders/1"
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/orders/2"

# Create order
Invoke-ApiCall -Service "order-service" -Method "POST" -Path "/api/v2/orders" -Body '{\"customer\":\"Jane Doe\",\"total\":125.75,\"status\":\"pending\"}'

# Update order
Invoke-ApiCall -Service "order-service" -Method "PUT" -Path "/api/v2/orders/1" -Body '{\"status\":\"completed\"}'

# Inventory
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/inventory"
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/inventory/1"

# Create inventory item
Invoke-ApiCall -Service "order-service" -Method "POST" -Path "/api/v2/inventory" -Body '{\"item\":\"Widget X\",\"quantity\":75,\"location\":\"Warehouse 3\"}'

# Sales report
Invoke-ApiCall -Service "order-service" -Method "GET" -Path "/api/v2/reports/sales"

# Delete order
Invoke-ApiCall -Service "order-service" -Method "DELETE" -Path "/api/v2/orders/3"

Write-Host ""
Write-Host "=== All API calls completed ===" -ForegroundColor Green
Write-Host ""
Write-Host "To view captured endpoints:" -ForegroundColor Yellow
Write-Host "  .\extract-endpoints.ps1" -ForegroundColor White
Write-Host ""

