# Script to extract and format captured endpoints from traffic monitor
# This script demonstrates how to extract data for integration

param(
    [string]$OutputFile = "captured-endpoints.json",
    [string]$Namespace = "kube-system",
    [switch]$SkipHealthChecks = $true,
    [switch]$NewOnly = $false,
    [switch]$Clear = $false
)

# Common health check paths to filter out
$healthCheckPaths = @("/health", "/healthz", "/ready", "/readiness", "/live", "/liveness", "/ping", "/status")

Write-Host "Extracting captured endpoints from traffic monitor..." -ForegroundColor Cyan
if ($SkipHealthChecks) {
    Write-Host "  (Health checks will be filtered out)" -ForegroundColor Gray
}
if ($NewOnly) {
    Write-Host "  (Showing only new endpoints since last run)" -ForegroundColor Gray
}
Write-Host ""

# Get the traffic monitor pod
$pod = kubectl get pods -l app=traffic-monitor -n $Namespace -o jsonpath='{.items[0].metadata.name}' 2>$null

if (-not $pod) {
    Write-Host "ERROR: traffic-monitor pod not found!" -ForegroundColor Red
    exit 1
}

# State file to track last extraction
$stateFile = ".extract-state.json"

# Get last extraction count if tracking new only
$lastCount = 0
if ($NewOnly -and (Test-Path $stateFile)) {
    try {
        $state = Get-Content $stateFile | ConvertFrom-Json
        $lastCount = $state.lastCount
    } catch {
        $lastCount = 0
    }
}

# Get endpoints from the file (JSON Lines format)
$endpointsJson = kubectl exec $pod -n $Namespace -- cat /tmp/endpoints.json 2>$null

if (-not $endpointsJson -or $endpointsJson.Trim() -eq "") {
    Write-Host "No endpoints captured yet." -ForegroundColor Yellow
    Write-Host "Try generating some HTTP traffic first:" -ForegroundColor Yellow
    Write-Host "  .\manual-calls.ps1" -ForegroundColor White
    Write-Host "  Or use the web UI" -ForegroundColor White
    exit 0
}

# Parse JSON Lines (each line is a separate JSON object)
$endpoints = @()
$lines = $endpointsJson -split "`n" | Where-Object { $_.Trim() -ne "" }
foreach ($line in $lines) {
    try {
        $endpoint = $line.Trim() | ConvertFrom-Json
        $endpoints += $endpoint
    } catch {
        # Skip parse errors
    }
}

$totalCaptured = $endpoints.Count
Write-Host "Total endpoints in capture file: $totalCaptured" -ForegroundColor Gray

# Filter out health checks if requested
if ($SkipHealthChecks) {
    $beforeFilter = $endpoints.Count
    $filteredEndpoints = @()
    $sampleBefore = $endpoints | Where-Object { $_.type -eq "request" -and $_.endpoint } | Select-Object -Property endpoint, method -Unique | Select-Object -First 3
    if ($sampleBefore.Count -gt 0) {
        $sampleStr = ($sampleBefore | ForEach-Object { "$($_.method) $($_.endpoint)" }) -join ', '
        Write-Host "Before filtering - sample endpoints: $sampleStr" -ForegroundColor DarkGray
    }
    
    foreach ($endpoint in $endpoints) {
        $ep = $endpoint.endpoint
        if (-not $ep) {
            continue  # Skip entries without endpoint
        }
        $isHealthCheck = $false
        foreach ($path in $healthCheckPaths) {
            # Build check strings to avoid interpolation issues with special characters
            $pathWithSlash = $path + "/"
            $pathWithQuestion = $path + "?"
            # Exact match or starts with path + / or ?
            if ($ep -eq $path -or $ep.StartsWith($pathWithSlash) -or $ep.StartsWith($pathWithQuestion)) {
                $isHealthCheck = $true
                break
            }
        }
        if (-not $isHealthCheck) {
            $filteredEndpoints += $endpoint
        }
    }
    $endpoints = $filteredEndpoints
    $filteredCount = $beforeFilter - $endpoints.Count
    if ($filteredCount -gt 0) {
        Write-Host "Filtered out $filteredCount health check requests" -ForegroundColor Gray
    }
    
    # Debug: Show sample of what's left after filtering
    $uniqueEndpoints = $endpoints | Where-Object { $_.type -eq "request" } | Select-Object -Property endpoint, method -Unique | Select-Object -First 5
    if ($uniqueEndpoints.Count -gt 0) {
        $sample = $uniqueEndpoints | ForEach-Object { "$($_.method) $($_.endpoint)" }
        Write-Host "After filtering - remaining endpoints: $($sample -join ', ')" -ForegroundColor DarkGray
    } else {
        Write-Host "After filtering - NO endpoints remaining!" -ForegroundColor Yellow
    }
}

# If NewOnly, only show endpoints after the last count
if ($NewOnly -and $lastCount -gt 0) {
    $endpoints = $endpoints[$lastCount..($endpoints.Count - 1)]
    Write-Host "Showing $($endpoints.Count) new endpoints (after position $lastCount)" -ForegroundColor Gray
}

if ($endpoints.Count -eq 0) {
    Write-Host "No valid endpoints found" -ForegroundColor Yellow
    if ($SkipHealthChecks) {
        Write-Host "" -ForegroundColor Yellow
        Write-Host "NOTE: Only health check endpoints were found and filtered out." -ForegroundColor Yellow
        Write-Host "To see all endpoints including health checks, run:" -ForegroundColor White
        Write-Host "  .\extract-endpoints.ps1 -SkipHealthChecks:`$false" -ForegroundColor Cyan
        Write-Host "" -ForegroundColor Yellow
        Write-Host "If you expected API calls to be captured, verify:" -ForegroundColor Yellow
        Write-Host "  1. API calls are actually being made (check UI or run manual-calls.ps1)" -ForegroundColor White
        Write-Host "  2. Traffic monitor is running and capturing on the right interfaces" -ForegroundColor White
    }
    if ($NewOnly -and $lastCount -gt 0) {
        Write-Host "  (All endpoints were already extracted)" -ForegroundColor Gray
    }
    exit 0
}

Write-Host "Found $($endpoints.Count) endpoint captures" -ForegroundColor Green
Write-Host ""

# Save state for next run
if ($NewOnly) {
    $state = @{
        lastCount = $totalCaptured
        lastExtracted = (Get-Date -Format "o")
    }
    $state | ConvertTo-Json | Out-File -FilePath $stateFile -Encoding UTF8
}

# Filter endpoints to only include requested fields in the specified order
$filteredEndpoints = @()
foreach ($endpoint in $endpoints) {
    # Create ordered object with fields in the specified order
    $filtered = [ordered]@{
        "id" = $endpoint.id
        "timestamp" = $endpoint.timestamp
    }
    
    # Add status_code and status_text for responses (only if present)
    if ($endpoint.type -eq "response" -and $endpoint.status_code) {
        $filtered["status_code"] = $endpoint.status_code
    }
    if ($endpoint.type -eq "response" -and $endpoint.status_text) {
        $filtered["status_text"] = $endpoint.status_text
    }
    
    # Add service, method, endpoint, full_url, type (request/response)
    if ($endpoint.service) {
        $filtered["service"] = $endpoint.service
    }
    $filtered["method"] = $endpoint.method
    $filtered["endpoint"] = $endpoint.endpoint
    $filtered["full_url"] = $endpoint.full_url
    $filtered["type"] = $endpoint.type  # "request" or "response"
    
    # Add headers (request_headers or response_headers)
    if ($endpoint.request_headers) {
        $filtered["headers"] = $endpoint.request_headers
    } elseif ($endpoint.response_headers) {
        $filtered["headers"] = $endpoint.response_headers
    }
    
    $filteredEndpoints += $filtered
}

# Convert to array and save to file
$output = @{
    "metadata" = @{
        "extracted_at" = (Get-Date -Format "o")
        "total_endpoints" = $filteredEndpoints.Count
        "total_in_file" = $totalCaptured
        "filtered_health_checks" = $SkipHealthChecks
        "new_only" = $NewOnly
        "node" = if ($endpoints[0]) { $endpoints[0].node } else { "unknown" }
    }
    "endpoints" = $filteredEndpoints
}

$output | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "Saved $($endpoints.Count) endpoints to: $OutputFile" -ForegroundColor Green
Write-Host ""

# Show summary statistics
Write-Host "=== Summary Statistics ===" -ForegroundColor Cyan
$byType = $endpoints | Group-Object -Property type
$byMethod = $endpoints | Where-Object { $_.type -eq "request" } | Group-Object -Property method
$byStatus = $endpoints | Where-Object { $_.type -eq "response" } | Group-Object -Property status_code
$uniqueEndpoints = $endpoints | Where-Object { $_.type -eq "request" } | Select-Object -Unique -Property endpoint, method

Write-Host "By Type:" -ForegroundColor Yellow
$byType | ForEach-Object { Write-Host "  $($_.Name): $($_.Count)" }
Write-Host ""
Write-Host "By HTTP Method:" -ForegroundColor Yellow
$byMethod | ForEach-Object { Write-Host "  $($_.Name): $($_.Count)" }
Write-Host ""
Write-Host "By Status Code:" -ForegroundColor Yellow
$byStatus | ForEach-Object { Write-Host "  $($_.Name): $($_.Count)" }
Write-Host ""
Write-Host "Unique Endpoints Discovered: $($uniqueEndpoints.Count)" -ForegroundColor Yellow
$uniqueEndpoints | ForEach-Object { Write-Host "  - $($_.method) $($_.endpoint)" }

Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  .\extract-endpoints.ps1              # Extract all (filters health checks by default)" -ForegroundColor White
Write-Host "  .\extract-endpoints.ps1 -NewOnly     # Extract only new endpoints since last run" -ForegroundColor White
Write-Host "  .\extract-endpoints.ps1 -SkipHealthChecks:`$false  # Include health checks" -ForegroundColor White

