#!/usr/bin/env pwsh
# Interactive script to configure traffic-monitor ConfigMap

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Traffic Monitor ConfigMap Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get API Key
Write-Host "1. Enter your API Key:" -ForegroundColor Yellow
$apiKey = Read-Host "   API Key"

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "ERROR: API Key is required!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Auto-onboarding is disabled for production deployments
# Services must be manually mapped to existing APISec applications
$autoOnboardNewServices = $false
Write-Host "2. Service Mapping Configuration" -ForegroundColor Yellow
Write-Host ""

$serviceMappings = @{}

Write-Host "   Enter service mappings:" -ForegroundColor Yellow
Write-Host "   (You can add multiple services. Enter empty service name to finish)" -ForegroundColor Gray
Write-Host ""

$serviceIndex = 1
while ($true) {
    Write-Host "   Service #$serviceIndex" -ForegroundColor Cyan
    $serviceName = Read-Host "   Service name (press Enter to finish)"
    
    if ([string]::IsNullOrWhiteSpace($serviceName)) {
        break
    }
    
    $appId = Read-Host "   Application ID (appId)"
    if ([string]::IsNullOrWhiteSpace($appId)) {
        Write-Host "   WARNING: Skipping service (appId required)" -ForegroundColor Yellow
        continue
    }
    
    $instanceId = Read-Host "   Instance ID (instanceId)"
    if ([string]::IsNullOrWhiteSpace($instanceId)) {
        Write-Host "   WARNING: Skipping service (instanceId required)" -ForegroundColor Yellow
        continue
    }
    
    $serviceMappings[$serviceName] = @{
        appId = $appId
        instanceId = $instanceId
    }
    
    Write-Host "   OK: Added mapping for '$serviceName'" -ForegroundColor Green
    Write-Host ""
    $serviceIndex++
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Configuration Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "API Key: $($apiKey.Substring(0, [Math]::Min(30, $apiKey.Length)))..." -ForegroundColor White
Write-Host "Auto-onboard new services: Disabled (manual mapping only)" -ForegroundColor White
Write-Host "Service mappings: $($serviceMappings.Count) service(s)" -ForegroundColor White

if ($serviceMappings.Count -gt 0) {
    Write-Host ""
    Write-Host "Mappings:" -ForegroundColor Yellow
    foreach ($service in $serviceMappings.Keys) {
        Write-Host "  - $service : appId=$($serviceMappings[$service].appId), instanceId=$($serviceMappings[$service].instanceId)" -ForegroundColor Gray
    }
}

Write-Host ""
$confirm = Read-Host "Write this configuration to configmap.yaml? (y/n)"

if ($confirm -ne 'y' -and $confirm -ne 'Y' -and $confirm -ne 'yes' -and $confirm -ne 'YES') {
    Write-Host "ERROR: Cancelled" -ForegroundColor Red
    exit 0
}

# Build the JSON structure
$serviceMappingsJson = @{}
foreach ($service in $serviceMappings.Keys) {
    $serviceMappingsJson[$service] = @{
        appId = $serviceMappings[$service].appId
        instanceId = $serviceMappings[$service].instanceId
    }
}

$configJson = @{
    apiKey = $apiKey
    autoOnboardNewServices = $autoOnboardNewServices
    apisecUrl = "https://api.apisecapps.com"
    serviceMappings = $serviceMappingsJson
}

# Convert to JSON with proper formatting
$jsonContent = $configJson | ConvertTo-Json -Depth 10

# Indent JSON content by 4 spaces for YAML literal block
$lines = $jsonContent -split [Environment]::NewLine
$indentedJson = ($lines | ForEach-Object { "    $_" }) -join [Environment]::NewLine

# Build the YAML file using StringBuilder-like approach
$yamlParts = @()
$yamlParts += "apiVersion: v1"
$yamlParts += "kind: ConfigMap"
$yamlParts += "metadata:"
$yamlParts += "  name: traffic-monitor-config"
$yamlParts += "  namespace: kube-system"
$yamlParts += "data:"
# Use single quotes to avoid pipe character being interpreted
$yamlParts += '  service_config.json: |'

$yamlHeader = $yamlParts -join [Environment]::NewLine
$yamlContent = $yamlHeader + [Environment]::NewLine + $indentedJson + [Environment]::NewLine

# Write to file
try {
    $yamlContent | Out-File -FilePath "configmap.yaml" -Encoding utf8
    Write-Host ""
    Write-Host "Successfully wrote configuration to configmap.yaml" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. kubectl apply -f configmap.yaml" -ForegroundColor White
    Write-Host "  2. kubectl delete pod -n kube-system -l app=traffic-monitor" -ForegroundColor White
    Write-Host ""
} catch {
    Write-Host ''
    $errorMsg = $_.Exception.Message
    Write-Host 'Error writing configmap.yaml:' -ForegroundColor Red
    Write-Host $errorMsg -ForegroundColor Red
    exit 1
}

