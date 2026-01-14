#!/bin/bash
# Interactive script to configure traffic-monitor ConfigMap

echo "========================================"
echo "  Traffic Monitor ConfigMap Setup"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Get API Key
echo -e "${YELLOW}1. Enter your API Key:${NC}"
read -p "   API Key: " apiKey

if [ -z "$apiKey" ]; then
    echo -e "${RED}ERROR: API Key is required!${NC}"
    exit 1
fi

echo ""

# Auto-onboarding is disabled for production deployments
# Services must be manually mapped to existing APISec applications
autoOnboardNewServices=false
echo -e "${YELLOW}2. Service Mapping Configuration${NC}"
echo ""

declare -A serviceMappings

echo -e "${YELLOW}   Enter service mappings:${NC}"
echo -e "${GRAY}   (You can add multiple services. Enter empty service name to finish)${NC}"
echo ""

serviceIndex=1
while true; do
    echo -e "${CYAN}   Service #$serviceIndex${NC}"
    read -p "   Service name (press Enter to finish): " serviceName
    
    if [ -z "$serviceName" ]; then
        break
    fi
    
    read -p "   Application ID (appId): " appId
    if [ -z "$appId" ]; then
        echo -e "${YELLOW}   WARNING: Skipping service (appId required)${NC}"
        continue
    fi
    
    read -p "   Instance ID (instanceId): " instanceId
    if [ -z "$instanceId" ]; then
        echo -e "${YELLOW}   WARNING: Skipping service (instanceId required)${NC}"
        continue
    fi
    
    serviceMappings["$serviceName"]="$appId|$instanceId"
    
    echo -e "${GREEN}   OK: Added mapping for '$serviceName'${NC}"
    echo ""
    ((serviceIndex++))
done

echo ""
echo "========================================"
echo -e "${CYAN}  Configuration Summary${NC}"
echo "========================================"
echo ""

# Show API key (first 30 chars)
apiKeyPreview="${apiKey:0:30}..."
echo -e "${WHITE}API Key: $apiKeyPreview${NC}"
echo -e "${WHITE}Auto-onboard new services: Disabled (manual mapping only)${NC}"
echo -e "${WHITE}Service mappings: ${#serviceMappings[@]} service(s)${NC}"

if [ ${#serviceMappings[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Mappings:${NC}"
    for service in "${!serviceMappings[@]}"; do
        IFS='|' read -r appId instanceId <<< "${serviceMappings[$service]}"
        echo -e "${GRAY}  - $service : appId=$appId, instanceId=$instanceId${NC}"
    done
fi

echo ""
read -p "Write this configuration to configmap.yaml? (y/n): " confirm

if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && [ "$confirm" != "yes" ] && [ "$confirm" != "YES" ]; then
    echo -e "${RED}ERROR: Cancelled${NC}"
    exit 0
fi

# Build JSON structure
jsonContent="{"
jsonContent+="\"apiKey\": \"$apiKey\","
jsonContent+="\"autoOnboardNewServices\": $autoOnboardNewServices,"
jsonContent+="\"apisecUrl\": \"https://api.apisecapps.com\","
jsonContent+="\"serviceMappings\": {"

first=true
for service in "${!serviceMappings[@]}"; do
    IFS='|' read -r appId instanceId <<< "${serviceMappings[$service]}"
    if [ "$first" = true ]; then
        first=false
    else
        jsonContent+=","
    fi
    jsonContent+="\"$service\": {"
    jsonContent+="\"appId\": \"$appId\","
    jsonContent+="\"instanceId\": \"$instanceId\""
    jsonContent+="}"
done

jsonContent+="}"
jsonContent+="}"

# Format JSON with jq if available, otherwise use Python
if command -v jq &> /dev/null; then
    formattedJson=$(echo "$jsonContent" | jq .)
elif command -v python3 &> /dev/null; then
    formattedJson=$(echo "$jsonContent" | python3 -m json.tool)
else
    # Fallback: use the JSON as-is (not pretty, but valid)
    formattedJson="$jsonContent"
fi

# Indent JSON content by 4 spaces for YAML literal block
indentedJson=$(echo "$formattedJson" | sed 's/^/    /')

# Build the YAML file
yamlContent="apiVersion: v1
kind: ConfigMap
metadata:
  name: traffic-monitor-config
  namespace: kube-system
data:
  service_config.json: |
$indentedJson
"

# Write to file
if echo "$yamlContent" > configmap.yaml; then
    echo ""
    echo -e "${GREEN}Successfully wrote configuration to configmap.yaml${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "${WHITE}  1. kubectl apply -f configmap.yaml${NC}"
    echo -e "${WHITE}  2. kubectl delete pod -n kube-system -l app=traffic-monitor${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}Error writing configmap.yaml${NC}"
    exit 1
fi

