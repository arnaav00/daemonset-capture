#!/usr/bin/env pwsh
# Script to manually create applications and instances for services
# Similar to auto-onboarding functionality

param(
    [string]$ApiKey = "",
    [string]$ApiUrl = "https://api.dev.apisecapps.com",
    [string[]]$Services = @("example-api", "order-service")
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Create Applications and Instances" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get API Key if not provided
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    Write-Host "Enter your API Key (Bearer token):" -ForegroundColor Yellow
    $ApiKey = Read-Host "API Key"
    
    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        Write-Host "ERROR: API Key is required!" -ForegroundColor Red
        exit 1
    }
}

$ApiKey = $ApiKey.Trim()
$ApiUrl = $ApiUrl.TrimEnd('/')

Write-Host "API URL: $ApiUrl" -ForegroundColor Gray
Write-Host "Services to create: $($Services -join ', ')" -ForegroundColor Gray
Write-Host ""

$results = @{}

foreach ($serviceName in $Services) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Processing: $serviceName" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    try {
        # Step 1: Create application
        Write-Host "[1/2] Creating application '$serviceName'..." -ForegroundColor Gray
        
        # Generate empty OpenAPI spec
        $openapiSpec = @{
            openapi = "3.0.0"
            info = @{
                title = $serviceName
                version = "1.0.0"
                description = "Auto-onboarded service: $serviceName"
            }
            servers = @(
                @{
                    url = "/"
                    description = "Default server"
                }
            )
            paths = @{}
        } | ConvertTo-Json -Depth 10 -Compress
        
        # Create temporary file for OpenAPI spec
        $tempFile = [System.IO.Path]::GetTempFileName() + ".json"
        $openapiSpec | Out-File -FilePath $tempFile -Encoding UTF8 -NoNewline
        
        # Upload OpenAPI spec using multipart form data
        $uploadUrl = "$ApiUrl/v1/applications/oas"
        
        try {
            # Build multipart/form-data manually (for Windows PowerShell 5.1 compatibility)
            $boundary = [System.Guid]::NewGuid().ToString()
            $fileContent = [System.IO.File]::ReadAllText($tempFile)
            $fileName = [System.IO.Path]::GetFileName($tempFile)
            
            $bodyLines = @(
                "--$boundary",
                "Content-Disposition: form-data; name=`"fileUpload`"; filename=`"$fileName`"",
                "Content-Type: application/json",
                "",
                $fileContent,
                "--$boundary",
                "Content-Disposition: form-data; name=`"applicationName`"",
                "",
                $serviceName,
                "--$boundary",
                "Content-Disposition: form-data; name=`"origin`"",
                "",
                "K8S_DAEMONSET",
                "--$boundary--"
            )
            
            $body = $bodyLines -join "`r`n"
            $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
            
            $uploadHeaders = @{
                "Authorization" = "Bearer $ApiKey"
                "Content-Type" = "multipart/form-data; boundary=$boundary"
            }
            
            $uploadResponse = Invoke-RestMethod -Uri $uploadUrl -Method Post -Headers $uploadHeaders -Body $bodyBytes -ErrorAction Stop
            $appId = $uploadResponse.applicationId
            
            if (-not $appId) {
                Write-Host "  ERROR: Failed to get applicationId from upload response" -ForegroundColor Red
                Write-Host "  Response: $($uploadResponse | ConvertTo-Json)" -ForegroundColor Red
                Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
                continue
            }
            
            Write-Host "  Application created successfully" -ForegroundColor Green
            Write-Host "  Application ID: $appId" -ForegroundColor Gray
        } catch {
            Write-Host "  ERROR: Failed to create application" -ForegroundColor Red
            Write-Host "  Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
            Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
            if ($_.ErrorDetails.Message) {
                Write-Host "  Details: $($_.ErrorDetails.Message)" -ForegroundColor Red
            }
            Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
            continue
        } finally {
            # Clean up temp file
            if (Test-Path $tempFile) {
                Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
            }
        }
        
        # Step 2: Create instance
        Write-Host "[2/2] Creating instance for application..." -ForegroundColor Gray
        
        $instancesUrl = "$ApiUrl/v1/applications/$appId/instances/batch"
        $instancePayload = @{
            instanceRequestItems = @(
                @{
                    hostUrl = "/"
                    instanceName = "${serviceName}_instance"
                }
            )
        } | ConvertTo-Json -Depth 10
        
        $instanceHeaders = @{
            "Authorization" = "Bearer $ApiKey"
            "Content-Type" = "application/json"
        }
        
        try {
            $instanceResponse = Invoke-RestMethod -Uri $instancesUrl -Method Post -Headers $instanceHeaders -Body $instancePayload -ErrorAction Stop
            
            # Extract instanceId from response (could be in different formats)
            $instanceId = $null
            if ($instanceResponse.instanceIds -and $instanceResponse.instanceIds.Count -gt 0) {
                $instanceId = $instanceResponse.instanceIds[0]
            } elseif ($instanceResponse.instanceId) {
                $instanceId = $instanceResponse.instanceId
            } elseif ($instanceResponse.items -and $instanceResponse.items.Count -gt 0) {
                $instanceId = $instanceResponse.items[0].instanceId
            } elseif ($instanceResponse -is [array] -and $instanceResponse.Count -gt 0) {
                $instanceId = $instanceResponse[0].instanceId
            }
            
            if (-not $instanceId) {
                Write-Host "  WARNING: Could not extract instanceId from response, fetching from application..." -ForegroundColor Yellow
                Write-Host "  Response: $($instanceResponse | ConvertTo-Json -Depth 5)" -ForegroundColor Gray
                
                # Fallback: Fetch from application
                Start-Sleep -Seconds 2
                $appUrl = "$ApiUrl/v1/applications/$appId"
                try {
                    $appResponse = Invoke-RestMethod -Uri $appUrl -Method Get -Headers $instanceHeaders -ErrorAction Stop
                    if ($appResponse.instances -and $appResponse.instances.Count -gt 0) {
                        $instanceId = $appResponse.instances[0].instanceId
                        Write-Host "  Found instanceId from application fetch: $instanceId" -ForegroundColor Green
                    }
                } catch {
                    Write-Host "  ERROR: Failed to fetch application to get instanceId" -ForegroundColor Red
                    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            
            if (-not $instanceId) {
                Write-Host "  ERROR: Failed to get instanceId from response or application" -ForegroundColor Red
                Write-Host "  Response: $($instanceResponse | ConvertTo-Json -Depth 5)" -ForegroundColor Red
                continue
            }
            
            Write-Host "  Instance created successfully" -ForegroundColor Green
            Write-Host "  Instance ID: $instanceId" -ForegroundColor Gray
            Write-Host "  Instance Name: ${serviceName}_instance" -ForegroundColor Gray
            
            $results[$serviceName] = @{
                appId = $appId
                instanceId = $instanceId
            }
        } catch {
            Write-Host "  ERROR: Failed to create instance" -ForegroundColor Red
            Write-Host "  Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
            Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
            if ($_.ErrorDetails.Message) {
                Write-Host "  Details: $($_.ErrorDetails.Message)" -ForegroundColor Red
            }
            continue
        }
        
        Write-Host ""
        
    } catch {
        Write-Host "  ERROR: Unexpected error processing $serviceName" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
    }
}

# Update configmap.yaml
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Updating configmap.yaml" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($results.Count -eq 0) {
    Write-Host "No applications/instances were created." -ForegroundColor Yellow
    exit 1
}

$configmapPath = "configmap.yaml"

if (-not (Test-Path $configmapPath)) {
    Write-Host "ERROR: configmap.yaml not found in current directory" -ForegroundColor Red
    exit 1
}

try {
    # Read and parse existing configmap
    $configmapContent = Get-Content $configmapPath -Raw
    
    # Extract JSON from service_config.json section
    if ($configmapContent -match '(?s)service_config\.json:\s*\|\s*\n(\s+)(\{.*?\})(?=\n\s*\n|\n\s*---|\Z)') {
        $jsonIndent = $Matches[1]
        $jsonContent = $Matches[2]
        $config = $jsonContent | ConvertFrom-Json
    } else {
        # If parsing fails, create new config
        $config = @{
            apiKey = $ApiKey
            autoOnboardNewServices = $false
            devApiUrl = "https://api.dev.apisecapps.com"
            serviceMappings = @{}
        } | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    }
    
    # Update API key if provided
    if ($ApiKey) {
        $config.apiKey = $ApiKey
    }
    
    # Update service mappings (merge with existing)
    if (-not $config.serviceMappings) {
        $config.serviceMappings = @{}
    }
    
    foreach ($serviceName in $results.Keys) {
        $result = $results[$serviceName]
        if (-not $config.serviceMappings.PSObject.Properties[$serviceName]) {
            $config.serviceMappings | Add-Member -MemberType NoteProperty -Name $serviceName -Value @{}
        }
        $config.serviceMappings.$serviceName.appId = $result.appId
        $config.serviceMappings.$serviceName.instanceId = $result.instanceId
    }
    
    # Convert to JSON and indent for YAML
    $jsonContent = $config | ConvertTo-Json -Depth 10
    $lines = $jsonContent -split [Environment]::NewLine
    $indentedJson = ($lines | ForEach-Object { "    $_" }) -join [Environment]::NewLine
    
    # Rebuild configmap.yaml (similar to setup-config.ps1)
    $yamlParts = @()
    $yamlParts += "apiVersion: v1"
    $yamlParts += "kind: ConfigMap"
    $yamlParts += "metadata:"
    $yamlParts += "  name: traffic-monitor-config"
    $yamlParts += "  namespace: kube-system"
    $yamlParts += "data:"
    $yamlParts += '  service_config.json: |'
    
    $yamlHeader = $yamlParts -join [Environment]::NewLine
    $yamlContent = $yamlHeader + [Environment]::NewLine + $indentedJson + [Environment]::NewLine
    
    # Write to file
    $yamlContent | Out-File -FilePath $configmapPath -Encoding utf8
    
    Write-Host "Updated configmap.yaml with service mappings:" -ForegroundColor Green
    foreach ($serviceName in $results.Keys) {
        $result = $results[$serviceName]
        Write-Host "  $serviceName -> appId: $($result.appId), instanceId: $($result.instanceId)" -ForegroundColor Gray
    }
    
    if ($ApiKey) {
        Write-Host "Updated API key in configmap.yaml" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "Done! ConfigMap updated." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to update configmap.yaml: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Please update configmap.yaml manually with the following mappings:" -ForegroundColor Yellow
    Write-Host ""
    foreach ($serviceName in $results.Keys) {
        $result = $results[$serviceName]
        Write-Host "  `"$serviceName`": { `"appId`": `"$($result.appId)`", `"instanceId`": `"$($result.instanceId)`" }" -ForegroundColor White
    }
    exit 1
}

